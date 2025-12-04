**This is for me to learn**

# Vector Database Implementation

This is a simple, in-memory vector database implementation in Python designed for learning purposes. It allows you to store vectors (or documents converted to vectors), associate them with metadata, and perform semantic searches using cosine similarity. It also supports metadata filtering and persistence to disk.

## Features

- **In-Memory Storage**: Fast lookups using NumPy for vector operations.
- **Document Support**: Can insert raw text if an embedding function is provided.
- **Metadata Filtering**: Supports both simple lambda-based filtering and structured dictionary filters (e.g., `{"year": {"$gt": 2020}}`).
- **Persistence**: Save and load the database state to/from a JSON file.

## Installation

You will need Python 3.11+:

```bash
pip install uv

uv sync
```

## Usage Examples

### 1. Basic Vector Operations

You can insert raw vectors and search for them.

```python
import numpy as np
from db import VectorDB

# Initialize the database
db = VectorDB()

# Insert some vectors
v1 = np.array([1.0, 0.0])
v2 = np.array([0.0, 1.0])

id1 = db.insert_vector(v1, metadata={"name": "vector_a"})
id2 = db.insert_vector(v2, metadata={"name": "vector_b"})

# Search
query = np.array([0.9, 0.1])
results = db.search(query, k=1)

print(f"Found: {results[0].metadata['name']} with score {results[0].score}")
```

### 2. Document Storage with Embeddings

If you provide an embedding function, you can store text directly.

```python
from db import VectorDB

# Mock embedding function (replace with OpenAI, HuggingFace, etc.)
def my_embedding_fn(text):
    # This is just a dummy example returning random vectors
    import numpy as np
    np.random.seed(len(text))
    return np.random.rand(128)

db = VectorDB(embedding_function=my_embedding_fn)

# Insert documents
db.insert_document("Hello world", metadata={"category": "greeting"})
db.insert_document("Python is awesome", metadata={"category": "tech"})

# Search by text
results = db.search("Hello", k=1)
print(f"Top match: {results[0].metadata['content']}")
```

### 3. Metadata Filtering

You can filter results based on metadata tags.

```python
# Insert data with metadata
db.insert_document("Doc A", metadata={"year": 2021, "tag": "A"})
db.insert_document("Doc B", metadata={"year": 2023, "tag": "B"})

# Search with structured filter
# Find documents where year is greater than 2022
results = db.search("Doc", k=5, filter={"year": {"$gt": 2022}})
```

### 4. Persistence

Save your database to disk and load it back later.

```python
# Save
db.save("my_vector_db.json")

# Load
new_db = VectorDB.load("my_vector_db.json", embedding_function=my_embedding_fn)
```

## Todo Checklist

- [ ] Binary persistence (Storing vectors as Base64 strings in a JSON file is inefficient for storage size and loading speed)
- [ ] Include create a simple db server so it can be accessed over a network
- [ ] Implement a multi tenant capability (right now all data is basically clustered in the same data structured)
