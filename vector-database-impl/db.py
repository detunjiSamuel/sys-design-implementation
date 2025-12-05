import numpy as np
import json
import base64
from uuid import uuid4
from typing import List, Optional, Dict, Any, Callable, Union
import threading
from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    id: str
    score: float
    metadata: Optional[Dict[str, Any]] = None
    vector: Optional[List[float]] = None


class VectorDB:
    def __init__(self, embedding_function: Optional[Callable] = None):
        self.vectors: List[np.ndarray] = []
        self.matrix: Optional[np.ndarray] = None
        self.embedding_function = embedding_function
        self.data: Dict[str, Dict[str, Any]] = {}  # Map ID -> Metadata/Document
        self.index_to_id: List[str] = []  # Map Matrix Index -> ID
        self.lock = threading.RLock()

    def insert_vector(
        self,
        vector: Union[List[float], np.ndarray],
        id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Insert vector with optional ID and metadata"""

        if id is None:
            id = str(uuid4())
        with self.lock:
            # Ensure vector is a numpy array
            vector = np.array(vector)

            self.vectors.append(vector)
            self.index_to_id.append(id)
            self.data[id] = metadata if metadata is not None else {}

            if self.matrix is None:
                self.matrix = np.array([vector])
            else:
                self.matrix = np.vstack([self.matrix, vector])

        return id

    def insert_document(
        self, doc: str, metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Insert document with optional metadata - uses embedding function"""
        if self.embedding_function is None:
            raise ValueError("Embedding function is not defined")

        vector = self.embedding_function(doc)
        if metadata is None:
            metadata = {}
        metadata["content"] = doc

        return self.insert_vector(vector, metadata=metadata)

    def get(self, id: str) -> Optional[Dict[str, Any]]:
        """Get document by ID"""
        with self.lock:
            return self.data.get(id)

    def delete(self, id: str) -> bool:
        """Delete document by ID"""
        with self.lock:
            if id not in self.data:
                return False

            # Find index
            try:
                idx = self.index_to_id.index(id)
            except ValueError:
                return False

            # Remove from data
            del self.data[id]

            # Remove from index_to_id
            del self.index_to_id[idx]

            # Remove from vectors
            del self.vectors[idx]

            # Remove from matrix
            if self.matrix is not None:
                self.matrix = np.delete(self.matrix, idx, axis=0)

        return True

    def search(
        self,
        query: Union[str, List[float], np.ndarray],
        k: int = 5,
        filter_function: Optional[Callable[[Dict[str, Any]], bool]] = None,
        filter: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        """Search for documents similar to query"""
        # If query is a string and we have an embedding function, encode it
        if isinstance(query, str):
            if self.embedding_function is not None:
                query = self.embedding_function(query)
            else:
                raise ValueError("Embedding function is needed for string queries")

        with self.lock:
            return self._cosine_similarity_search(query, k, filter_function, filter)

    def _cosine_similarity_search(
        self,
        query: Union[List[float], np.ndarray],
        k: int = 5,
        filter_function: Optional[Callable[[Dict[str, Any]], bool]] = None,
        filter: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        """Search for documents similar to query : Always called with lock held"""
        if self.matrix is None or len(self.matrix) == 0:
            return []

        # Ensure query is a numpy array
        query = np.array(query)

        # Normalize query
        query_norm = np.linalg.norm(query)
        if query_norm == 0:
            return []
        query_normalized = query / query_norm

        # Apply filter if provided
        if filter_function is not None or filter is not None:
            # Find indices that match the filter
            filtered_indices = []
            for i, id in enumerate(self.index_to_id):
                metadata = self.data.get(id, {})
                matches = True

                # Check filter_function
                if filter_function is not None:
                    if not filter_function(metadata):
                        matches = False

                # Check structured filter
                if matches and filter is not None:
                    if not self._matches_filter(metadata, filter):
                        matches = False

                if matches:
                    filtered_indices.append(i)

            if not filtered_indices:
                return []

            filtered_indices = np.array(filtered_indices)
            # Slice the matrix
            matrix_to_search = self.matrix[filtered_indices]
        else:
            matrix_to_search = self.matrix
            filtered_indices = np.arange(len(self.matrix))

        # Normalize matrix
        matrix_norm = np.linalg.norm(matrix_to_search, axis=1, keepdims=True)
        # Avoid division by zero
        matrix_norm[matrix_norm == 0] = 1
        matrix_normalized = matrix_to_search / matrix_norm

        # Calculate cosine similarity
        scores = np.dot(matrix_normalized, query_normalized)

        # Get top k indices
        # Note: indices here are relative to matrix_to_search
        top_k_relative_indices = np.argsort(scores)[-k:][::-1]

        results = []
        for rel_idx in top_k_relative_indices:
            # Map back to original index
            original_idx = filtered_indices[rel_idx]
            id = self.index_to_id[original_idx]
            results.append(
                SearchResult(
                    id=id,
                    vector=self.vectors[original_idx].tolist(),
                    score=float(scores[rel_idx]),
                    metadata=self.data.get(id),
                )
            )

        return results

    @staticmethod
    def _matches_filter(metadata: Dict[str, Any], filter_dict: Dict[str, Any]) -> bool:
        for key, value in filter_dict.items():
            # If key is not in metadata, it doesn't match
            # Exception: maybe we want to support checking for non-existence?
            # For now, assume we only filter on existing fields.
            if key not in metadata:
                return False

            metadata_value = metadata[key]

            if isinstance(value, dict):
                # Handle operators
                for op, op_value in value.items():
                    if op == "$gt":
                        if not (metadata_value > op_value):
                            return False
                    elif op == "$gte":
                        if not (metadata_value >= op_value):
                            return False
                    elif op == "$lt":
                        if not (metadata_value < op_value):
                            return False
                    elif op == "$lte":
                        if not (metadata_value <= op_value):
                            return False
                    elif op == "$eq":
                        if not (metadata_value == op_value):
                            return False
                    elif op == "$ne":
                        if not (metadata_value != op_value):
                            return False
                    elif op == "$in":
                        if not (metadata_value in op_value):
                            return False
                    elif op == "$nin":
                        if not (metadata_value not in op_value):
                            return False
                    else:
                        # Unknown operator, will just ignore unknown operators or return False
                        pass
            else:
                # Exact match
                if metadata_value != value:
                    return False

        return True

    def save(self, file_path: str):
        """Save the database to a JSON file."""
        data = {
            "matrix": (
                base64.b64encode(self.matrix.tobytes()).decode()
                if self.matrix is not None
                else ""
            ),
            "shape": self.matrix.shape if self.matrix is not None else (0, 0),
            "dtype": str(self.matrix.dtype) if self.matrix is not None else "float64",
            "data": self.data,
            "index_to_id": self.index_to_id,
        }
        with self.lock:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f)

    @classmethod
    def load(
        cls, file_path: str, embedding_function: Optional[Callable] = None
    ) -> "VectorDB":
        """Load the database from a JSON file."""
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        db = cls(embedding_function=embedding_function)
        if data["matrix"]:
            matrix_bytes = base64.b64decode(data["matrix"])
            dtype = data.get("dtype", "float64")
            db.matrix = np.frombuffer(matrix_bytes, dtype=dtype).reshape(data["shape"])
            # Reconstruct vectors list from matrix
            db.vectors = list(db.matrix)

        db.data = data.get("data", {})
        db.index_to_id = data.get("index_to_id", [])

        return db
