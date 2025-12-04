import numpy as np
import json
import base64
from uuid import uuid4


class VectorDB:
    def __init__(self, embedding_function=None):
        self.vectors = []
        self.matrix = None
        self.embedding_function = embedding_function
        self.data = {}  # Map ID -> Metadata/Document
        self.index_to_id = []  # Map Matrix Index -> ID

    def insert_vector(self, vector, id=None, metadata=None):
        """Insert vector with optional ID and metadata"""
        # Ensure vector is a numpy array
        vector = np.array(vector)

        if id is None:
            id = str(uuid4())

        self.vectors.append(vector)
        self.index_to_id.append(id)
        self.data[id] = metadata if metadata is not None else {}

        if self.matrix is None:
            self.matrix = np.array([vector])
        else:
            self.matrix = np.vstack([self.matrix, vector])

        return id

    def insert_document(self, doc, metadata=None):
        """Insert document with optional metadata - uses embedding function"""
        if self.embedding_function is None:
            raise ValueError("Embedding function is not defined")

        vector = self.embedding_function(doc)
        if metadata is None:
            metadata = {}
        metadata["content"] = doc
        return self.insert_vector(vector, metadata=metadata)

    def get(self, id):
        """Get document by ID"""
        return self.data.get(id)

    def delete(self, id):
        """Delete document by ID"""
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

    def search(self, query, k=5, filter=None):
        """Search for documents similar to query"""
        # If query is a string and we have an embedding function, encode it
        if isinstance(query, str) and self.embedding_function is not None:
            query = self.embedding_function(query)

        return self._cosine_similarity_search(query, k, filter)

    def _cosine_similarity_search(self, query, k=5, filter=None):
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
        if filter is not None:
            # Find indices that match the filter
            filtered_indices = []
            for i, id in enumerate(self.index_to_id):
                metadata = self.data.get(id, {})
                if filter(metadata):
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
                {
                    "id": id,
                    "vector": self.vectors[original_idx],
                    "score": float(scores[rel_idx]),
                    "metadata": self.data.get(id),
                }
            )

        return results

    def save(self, file_path):
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
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    @classmethod
    def load(cls, file_path, embedding_function=None):
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
