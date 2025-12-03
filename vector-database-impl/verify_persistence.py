import numpy as np
import os
from db import VectorDB


def verify_persistence():
    file_path = "test_db.json"

    # Clean up previous run
    if os.path.exists(file_path):
        os.remove(file_path)

    print("Initializing VectorDB 1...")
    db1 = VectorDB()

    # Define some vectors
    v1 = np.array([1.0, 0.0])
    v2 = np.array([0.0, 1.0])

    print("Inserting vectors into DB 1...")
    db1.insert_vector(v1)
    db1.insert_vector(v2)

    print("Saving DB 1...")
    db1.save(file_path)

    print("Initializing VectorDB 2 from file...")
    db2 = VectorDB.load(file_path)

    print(f"DB 2 size: {len(db2.vectors)}")
    assert len(db2.vectors) == 2

    # Verify content
    print("Verifying content...")
    assert np.allclose(db2.vectors[0], v1)
    assert np.allclose(db2.vectors[1], v2)

    # Verify search on loaded DB
    print("Testing search on loaded DB...")
    query = np.array([0.9, 0.1])
    results = db2.search(query, k=1)
    print(f"Top result: {results[0]}")
    assert results[0]["id"] == 0

    print("Persistence verification passed!")

    # Cleanup
    if os.path.exists(file_path):
        os.remove(file_path)


if __name__ == "__main__":
    verify_persistence()
