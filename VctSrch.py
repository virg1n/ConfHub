# VctSrch.py
import pickle
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

# Initialize the model once to avoid reloading it multiple times
model = SentenceTransformer("dunzhang/stella_en_400M_v5", trust_remote_code=True)

def vector_search_repos(db, query, k=5):
    repository_ids = []
    vectors = []

    # Fetch repository IDs and their vectors from the database
    cursor = db.execute("SELECT repository_id, vector FROM repositories WHERE vector IS NOT NULL")
    data = cursor.fetchall()

    for row in data:
        repo_id = row['repository_id']
        vector_blob = row['vector']
        if vector_blob:
            repository_ids.append(repo_id)
            vectors.append(pickle.loads(vector_blob))

    if not vectors:
        return []

    vectors = np.array(vectors, dtype='float32')
    dimension = vectors.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(vectors)

    query_vector = model.encode([query])[0].astype('float32')

    distances, indices = index.search(np.array([query_vector]), k)

    similar_repositories = []
    for idx in indices[0]:
        if idx < len(repository_ids):
            similar_repositories.append(repository_ids[idx])

    return similar_repositories

def description_to_embedding(description):
    description_vector = model.encode([description])[0]
    return description_vector
