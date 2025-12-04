import numpy as np
import os
from db import VectorDB


def mock_embedding_function(text):
    # Deterministic mock embedding
    # Use different dimensions based on characters to ensure different angles
    val1 = len(text)
    val2 = sum(ord(c) for c in text) % 10
    return np.array([val1, val2])


def verify_features():
    file_path = "test_features_db.json"
    if os.path.exists(file_path):
        os.remove(file_path)

    print("Initializing VectorDB with mock embedding...")
    db = VectorDB(embedding_function=mock_embedding_function)

    # Test insert_document
    print("Inserting documents...")
    id1 = db.insert_document("Hello world", metadata={"source": "greeting"})
    id2 = db.insert_document("Python is great", metadata={"source": "tech"})

    print(f"Inserted IDs: {id1}, {id2}")

    # Test get
    print("Testing get()...")
    doc1 = db.get(id1)
    print(f"Doc 1: {doc1}")
    assert doc1["content"] == "Hello world"
    assert doc1["source"] == "greeting"

    # Test search with text query
    print("Testing search with text query...")
    results = db.search("Hello", k=1)
    print(f"Search results: {results}")
    assert results[0]["id"] == id1
    assert results[0]["metadata"]["content"] == "Hello world"

    # Test persistence with metadata
    print("Testing persistence...")
    db.save(file_path)

    # Load with embedding function
    db_loaded = VectorDB.load(file_path, embedding_function=mock_embedding_function)
    doc2 = db_loaded.get(id2)
    print(f"Loaded Doc 2: {doc2}")
    assert doc2["content"] == "Python is great"

    # Test delete
    print("Testing delete()...")
    assert db_loaded.delete(id1) is True
    assert db_loaded.get(id1) is None
    assert len(db_loaded.vectors) == 1

    # Verify search after delete
    results_after = db_loaded.search("Hello", k=1)
    print(f"Search results after delete: {results_after}")
    assert results_after[0]["id"] == id2  # Should match the only remaining doc

    print("Features verification passed!")

    if os.path.exists(file_path):
        os.remove(file_path)


if __name__ == "__main__":
    verify_features()
