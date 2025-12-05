import unittest
import numpy as np
import os
from db import VectorDB
import threading
import time


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
        self.assertEqual(results1[0].id, id1)

        # Test 2: Query close to v2
        query2 = np.array([0.1, 0.9])
        results2 = db.search(query2, k=1)
        self.assertEqual(results2[0].id, id2)

        # Test 3: Query close to v3
        query3 = np.array([0.5, 0.5])
        results3 = db.search(query3, k=1)
        self.assertEqual(results3[0].id, id3)

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
        self.assertEqual(results[0].id, id1)
        self.assertEqual(results[0].metadata["content"], "Hello world")

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
            results_after[0].id, id2
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
            "match", k=3, filter_function=lambda m: m["category"] == "sports"
        )
        self.assertEqual(len(results_sports), 2)
        for r in results_sports:
            self.assertEqual(r.metadata["category"], "sports")

        # Search with year filter
        results_2023 = db.search(
            "match", k=3, filter_function=lambda m: m["year"] == 2023
        )
        self.assertEqual(len(results_2023), 2)
        for r in results_2023:
            self.assertEqual(r.metadata["year"], 2023)

        # Search with combined filter
        results_combined = db.search(
            "match",
            k=3,
            filter_function=lambda m: m["category"] == "sports" and m["year"] == 2023,
        )
        self.assertEqual(len(results_combined), 1)
        self.assertEqual(results_combined[0].id, id1)

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
        self.assertEqual(results[0].id, id1)

    def test_structured_filtering(self):
        """Test structured metadata filtering"""
        db = VectorDB(embedding_function=self.mock_embedding_function)

        # Insert documents
        id1 = db.insert_document(
            "Doc 1", metadata={"category": "A", "value": 10, "tags": ["x", "y"]}
        )
        id2 = db.insert_document(
            "Doc 2", metadata={"category": "B", "value": 20, "tags": ["y", "z"]}
        )
        id3 = db.insert_document(
            "Doc 3", metadata={"category": "A", "value": 30, "tags": ["x", "z"]}
        )

        # Test exact match
        results = db.search("Doc", k=3, filter={"category": "A"})
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r.metadata["category"], "A")

        # Test $gt operator
        results = db.search("Doc", k=3, filter={"value": {"$gt": 15}})
        self.assertEqual(len(results), 2)  # Doc 2 and 3
        for r in results:
            self.assertTrue(r.metadata["value"] > 15)

        # Test $in operator
        results = db.search("Doc", k=3, filter={"category": {"$in": ["A", "C"]}})
        self.assertEqual(len(results), 2)  # Doc 1 and 3

        # Test combined structured filter and filter_function
        # Filter: category="A" AND value > 20 (Doc 3)
        results = db.search(
            "Doc",
            k=3,
            filter={"category": "A"},
            filter_function=lambda m: m["value"] > 20,
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, id3)

        # Test multiple conditions in structured filter
        results = db.search("Doc", k=3, filter={"category": "B", "value": {"$lt": 25}})
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, id2)

    def test_concurrency(self):
        """Test concurrent access to the database"""
        db = VectorDB(embedding_function=self.mock_embedding_function)

        num_threads = 10
        docs_per_thread = 20

        def worker(thread_id):
            for i in range(docs_per_thread):
                doc_content = f"Thread-{thread_id} Doc-{i}"
                db.insert_document(
                    doc_content, metadata={"thread": thread_id, "idx": i}
                )
                # Random small sleep to encourage interleaving
                if i % 5 == 0:
                    time.sleep(0.001)

                # Occasional search
                if i % 10 == 0:
                    db.search("test", k=1)

        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Verify total documents
        expected_docs = num_threads * docs_per_thread
        self.assertEqual(len(db.vectors), expected_docs)
        self.assertEqual(len(db.index_to_id), expected_docs)
        self.assertEqual(len(db.data), expected_docs)
        if db.matrix is not None:
            self.assertEqual(db.matrix.shape[0], expected_docs)


if __name__ == "__main__":
    unittest.main()
