import unittest
import numpy as np
import os
from db import VectorDB


class TestVectorDB(unittest.TestCase):
    def setUp(self):
        self.test_db_path = "test_db.json"
        self.test_features_path = "test_features_db.json"
        # Ensure clean state
        if os.path.exists(self.test_db_path):
            os.remove(self.test_db_path)
        if os.path.exists(self.test_features_path):
            os.remove(self.test_features_path)

    def tearDown(self):
        # Cleanup
        if os.path.exists(self.test_db_path):
            os.remove(self.test_db_path)
        if os.path.exists(self.test_features_path):
            os.remove(self.test_features_path)

    def mock_embedding_function(self, text):
        # Deterministic mock embedding
        val1 = len(text)
        val2 = sum(ord(c) for c in text) % 10
        return np.array([val1, val2])

    def test_basic_vector_operations(self):
        """Test basic vector insertion and search (formerly verify_db.py)"""
        db = VectorDB()

        # Define some vectors
        v1 = np.array([1.0, 0.0])
        v2 = np.array([0.0, 1.0])
        v3 = np.array([1.0, 1.0])

        # Insert vectors and capture IDs
        id1 = db.insert_vector(v1)
        id2 = db.insert_vector(v2)
        id3 = db.insert_vector(v3)

        self.assertEqual(len(db.vectors), 3)

        # Test 1: Query close to v1
        query1 = np.array([0.9, 0.1])
        results1 = db.search(query1, k=1)
        self.assertEqual(results1[0]["id"], id1)

        # Test 2: Query close to v2
        query2 = np.array([0.1, 0.9])
        results2 = db.search(query2, k=1)
        self.assertEqual(results2[0]["id"], id2)

        # Test 3: Query close to v3
        query3 = np.array([0.5, 0.5])
        results3 = db.search(query3, k=1)
        self.assertEqual(results3[0]["id"], id3)

    def test_features_and_embedding(self):
        """Test document insertion, retrieval, and deletion (formerly verify_features.py)"""
        db = VectorDB(embedding_function=self.mock_embedding_function)

        # Test insert_document
        id1 = db.insert_document("Hello world", metadata={"source": "greeting"})
        id2 = db.insert_document("Python is great", metadata={"source": "tech"})

        # Test get
        doc1 = db.get(id1)
        self.assertEqual(doc1["content"], "Hello world")
        self.assertEqual(doc1["source"], "greeting")

        # Test search with text query
        results = db.search("Hello", k=1)
        self.assertEqual(results[0]["id"], id1)
        self.assertEqual(results[0]["metadata"]["content"], "Hello world")

        # Test persistence with metadata
        db.save(self.test_features_path)

        # Load with embedding function
        db_loaded = VectorDB.load(
            self.test_features_path, embedding_function=self.mock_embedding_function
        )
        doc2 = db_loaded.get(id2)
        self.assertEqual(doc2["content"], "Python is great")

        # Test delete
        self.assertTrue(db_loaded.delete(id1))
        self.assertIsNone(db_loaded.get(id1))
        self.assertEqual(len(db_loaded.vectors), 1)

        # Verify search after delete
        results_after = db_loaded.search("Hello", k=1)
        self.assertEqual(
            results_after[0]["id"], id2
        )  # Should match the only remaining doc

    def test_filtering(self):
        """Test metadata filtering (formerly verify_filtering.py)"""
        db = VectorDB(embedding_function=self.mock_embedding_function)

        # Insert documents with different categories
        id1 = db.insert_document(
            "Football match", metadata={"category": "sports", "year": 2023}
        )
        id2 = db.insert_document(
            "Guitar solo", metadata={"category": "music", "year": 2023}
        )
        id3 = db.insert_document(
            "Tennis final", metadata={"category": "sports", "year": 2022}
        )

        # Search without filter
        results = db.search("match", k=3)
        self.assertEqual(len(results), 3)

        # Search with category filter
        results_sports = db.search(
            "match", k=3, filter=lambda m: m["category"] == "sports"
        )
        self.assertEqual(len(results_sports), 2)
        for r in results_sports:
            self.assertEqual(r["metadata"]["category"], "sports")

        # Search with year filter
        results_2023 = db.search("match", k=3, filter=lambda m: m["year"] == 2023)
        self.assertEqual(len(results_2023), 2)
        for r in results_2023:
            self.assertEqual(r["metadata"]["year"], 2023)

        # Search with combined filter
        results_combined = db.search(
            "match",
            k=3,
            filter=lambda m: m["category"] == "sports" and m["year"] == 2023,
        )
        self.assertEqual(len(results_combined), 1)
        self.assertEqual(results_combined[0]["id"], id1)

    def test_persistence(self):
        """Test save and load functionality (formerly verify_persistence.py)"""
        db1 = VectorDB()

        # Define some vectors
        v1 = np.array([1.0, 0.0])
        v2 = np.array([0.0, 1.0])

        # Insert vectors
        id1 = db1.insert_vector(v1)
        id2 = db1.insert_vector(v2)

        db1.save(self.test_db_path)

        # Initialize VectorDB 2 from file
        db2 = VectorDB.load(self.test_db_path)

        self.assertEqual(len(db2.vectors), 2)

        # Verify content
        # Note: We can't guarantee order unless we sort or check by ID,
        # but since we inserted in order and implementation appends, index 0 should be v1.
        # However, to be robust, let's check by ID if possible, but load() restores index_to_id.

        # Check if IDs exist
        self.assertIsNotNone(db2.get(id1))
        self.assertIsNotNone(db2.get(id2))

        # Verify search on loaded DB
        query = np.array([0.9, 0.1])
        results = db2.search(query, k=1)
        self.assertEqual(results[0]["id"], id1)


if __name__ == "__main__":
    unittest.main()
