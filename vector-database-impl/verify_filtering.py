import numpy as np
import os
from db import VectorDB


def mock_embedding_function(text):
    # Deterministic mock embedding
    val1 = len(text)
    val2 = sum(ord(c) for c in text) % 10
    return np.array([val1, val2])


def verify_filtering():
    print("Initializing VectorDB with mock embedding...")
    db = VectorDB(embedding_function=mock_embedding_function)

    # Insert documents with different categories
    print("Inserting documents...")
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
    print("\nSearching 'match' without filter...")
    results = db.search("match", k=3)
    print(f"Found {len(results)} results")
    assert len(results) == 3

    # Search with category filter
    print("\nSearching 'match' with category='sports' filter...")
    results_sports = db.search("match", k=3, filter=lambda m: m["category"] == "sports")
    print(f"Found {len(results_sports)} results")
    for r in results_sports:
        print(f"- {r['metadata']}")
        assert r["metadata"]["category"] == "sports"
    assert len(results_sports) == 2

    # Search with year filter
    print("\nSearching 'match' with year=2023 filter...")
    results_2023 = db.search("match", k=3, filter=lambda m: m["year"] == 2023)
    print(f"Found {len(results_2023)} results")
    for r in results_2023:
        print(f"- {r['metadata']}")
        assert r["metadata"]["year"] == 2023
    assert len(results_2023) == 2

    # Search with combined filter
    print("\nSearching 'match' with category='sports' AND year=2023 filter...")
    results_combined = db.search(
        "match", k=3, filter=lambda m: m["category"] == "sports" and m["year"] == 2023
    )
    print(f"Found {len(results_combined)} results")
    assert len(results_combined) == 1
    assert results_combined[0]["id"] == id1

    print("\nFiltering verification passed!")


if __name__ == "__main__":
    verify_filtering()
