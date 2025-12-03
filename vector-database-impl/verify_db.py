import numpy as np
from db import VectorDB


def verify():
    print("Initializing VectorDB...")
    db = VectorDB()

    # Define some vectors
    v1 = np.array([1.0, 0.0])
    v2 = np.array([0.0, 1.0])
    v3 = np.array([1.0, 1.0])

    print("Inserting vectors...")
    db.insert_vector(v1)
    db.insert_vector(v2)
    db.insert_vector(v3)

    print(f"DB size: {len(db.vectors)}")
    assert len(db.vectors) == 3

    # Test 1: Query close to v1
    query1 = np.array([0.9, 0.1])
    print(f"\nQuerying with {query1} (should be closest to v1=[1, 0])")
    results1 = db.search(query1, k=1)
    print(f"Top result: {results1[0]}")

    # Check if index 0 (v1) is returned
    assert results1[0]["id"] == 0
    print("Test 1 Passed!")

    # Test 2: Query close to v2
    query2 = np.array([0.1, 0.9])
    print(f"\nQuerying with {query2} (should be closest to v2=[0, 1])")
    results2 = db.search(query2, k=1)
    print(f"Top result: {results2[0]}")

    assert results2[0]["id"] == 1
    print("Test 2 Passed!")

    # Test 3: Query close to v3
    query3 = np.array([0.5, 0.5])
    print(f"\nQuerying with {query3} (should be closest to v3=[1, 1])")
    results3 = db.search(query3, k=1)
    print(f"Top result: {results3[0]}")

    assert results3[0]["id"] == 2
    print("Test 3 Passed!")

    print("\nAll tests passed!")


if __name__ == "__main__":
    verify()
