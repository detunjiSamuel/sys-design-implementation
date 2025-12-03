import numpy as np


class VectorDB:
    def __init__(self):
        self.vectors = []
        self.matrix = None

    def insert_vector(self, vector):
        # Ensure vector is a numpy array
        vector = np.array(vector)
        self.vectors.append(vector)

        if self.matrix is None:
            self.matrix = np.array([vector])
        else:
            self.matrix = np.vstack([self.matrix, vector])

    def insert_document(self, id, doc):
        pass

    def encode_single_document(self, doc):
        # I am leaving this blank as it is a placeholder for the actual implementation
        pass

    def encode_multiple_documents(self, docs):
        # I am leaving this blank as it is a placeholder for the actual implementation
        pass

    def search(self, query, k=5, filter=None):
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

        # Normalize matrix
        matrix_norm = np.linalg.norm(self.matrix, axis=1, keepdims=True)
        # Avoid division by zero
        matrix_norm[matrix_norm == 0] = 1
        matrix_normalized = self.matrix / matrix_norm

        # Calculate cosine similarity
        scores = np.dot(matrix_normalized, query_normalized)

        # Get top k indices
        top_k_indices = np.argsort(scores)[-k:][::-1]

        results = []
        for idx in top_k_indices:
            results.append(
                {
                    "id": idx,  # Using index as ID for now since we don't have explicit IDs for vectors
                    "vector": self.vectors[idx],
                    "score": float(scores[idx]),
                }
            )

        return results
