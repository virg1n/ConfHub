# vector_search_service.py

import os
import pickle
import sqlite3
from flask import Flask, request, jsonify
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configuration
DATABASE_PATH = os.path.join(os.path.dirname(__file__), 'database.db')  # Adjust path as needed
MODEL_NAME = "sentence-transformers/distilbert-base-nli-stsb-mean-tokens"  # CPU-compatible model
EMBEDDING_DIMENSION = 768  # Adjust based on your model

# Initialize SentenceTransformer model
model = SentenceTransformer(MODEL_NAME)

# Initialize FAISS index
index = None
repository_ids = []

def load_vectors_into_faiss():
    global index, repository_ids
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT repository_id, vector FROM repositories WHERE vector IS NOT NULL")
    data = cursor.fetchall()
    
    vectors = []
    repository_ids = []
    
    for repo_id, vector_blob in data:
        if vector_blob:
            try:
                vector = pickle.loads(vector_blob)
                vectors.append(vector)
                repository_ids.append(repo_id)
            except Exception as e:
                print(f"Error loading vector for repo {repo_id}: {e}")
    
    conn.close()
    
    if vectors:
        vectors = np.array(vectors).astype('float32')
        dimension = vectors.shape[1]
        if dimension != EMBEDDING_DIMENSION:
            print(f"Dimension mismatch: Expected {EMBEDDING_DIMENSION}, but got {dimension}.")
            return
        index = faiss.IndexFlatL2(dimension)
        index.add(vectors)
        print(f"FAISS index initialized with {len(repository_ids)} vectors.")
    else:
        print("No vectors found in the database to initialize FAISS index.")

@app.route('/vector_search', methods=['POST'])
def vector_search_repos():
    """
    Endpoint to perform vector search.
    Expects JSON:
    {
        "query": "search terms",
        "k": 5
    }
    Returns JSON:
    {
        "similar_repo_ids": [1, 2, 3, 4, 5]
    }
    """
    global index, repository_ids
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "Invalid JSON data."}), 400
    
    query = data.get('query', '').strip()
    k = data.get('k', 5)
    
    if not query:
        return jsonify({"error": "Query cannot be empty."}), 400
    
    if not isinstance(k, int) or k <= 0:
        return jsonify({"error": "Parameter 'k' must be a positive integer."}), 400
    
    if index is None or len(repository_ids) == 0:
        return jsonify({"error": "Vector index is not initialized."}), 500
    
    try:
        query_vector = model.encode([query])[0].astype('float32')
        query_vector = np.expand_dims(query_vector, axis=0)
        distances, indices = index.search(query_vector, k)
        similar_repo_ids = [repository_ids[idx] for idx in indices[0] if idx < len(repository_ids)]
        return jsonify({"similar_repo_ids": similar_repo_ids}), 200
    except Exception as e:
        print(f"Error during vector search: {e}")
        return jsonify({"error": "An error occurred during vector search."}), 500

@app.route('/description_to_embedding', methods=['POST'])
def description_to_embedding():
    """
    Endpoint to convert a description to its embedding.
    Expects JSON:
    {
        "description": "Repository description text."
    }
    Returns JSON:
    {
        "embedding": [0.1, 0.2, ..., 0.384]
    }
    """
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "Invalid JSON data."}), 400
    
    description = data.get('description', '').strip()
    
    if not description:
        return jsonify({"error": "Description cannot be empty."}), 400
    
    try:
        embedding = model.encode([description])[0].tolist()
        return jsonify({"embedding": embedding}), 200
    except Exception as e:
        print(f"Error generating embedding: {e}")
        return jsonify({"error": "An error occurred while generating the embedding."}), 500

@app.route('/update_recommendations', methods=['POST'])
def update_recommendations():
    """
    Endpoint to update user recommendations based on their liked repositories.
    Expects JSON:
    {
        "user_id": 1,
        "k": 10  # Optional, default to 10
    }
    Returns JSON:
    {
        "recommended_repo_ids": [5, 8, 12, ...]
    }
    """
    global index, repository_ids
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "Invalid JSON data."}), 400
    
    user_id = data.get('user_id')
    k = data.get('k', 10)
    
    if not isinstance(user_id, int):
        return jsonify({"error": "Parameter 'user_id' must be an integer."}), 400
    
    if not isinstance(k, int) or k <= 0:
        return jsonify({"error": "Parameter 'k' must be a positive integer."}), 400
    
    if index is None or len(repository_ids) == 0:
        return jsonify({"error": "Vector index is not initialized."}), 500
    
    try:
        # Connect to the database
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Fetch all liked repositories for the user
        cursor.execute("""
            SELECT r.vector, r.repository_id
            FROM likes l
            JOIN repositories r ON l.repository_id = r.repository_id
            WHERE l.user_id = ? AND r.vector IS NOT NULL
        """, (user_id,))
        liked_repos = cursor.fetchall()

        print("LIKED REPOS:")
        print(liked_repos)
        
        if not liked_repos:
            return jsonify({"recommended_repo_ids": []}), 200  # No likes to base recommendations on
        
        # Load embeddings and compute the average embedding
        embeddings = []
        liked_repo_ids = set()
        for row in liked_repos:
            if row['vector']:
                try:
                    vector = pickle.loads(row['vector'])
                    embeddings.append(vector)
                    liked_repo_ids.add(row['repository_id'])
                except Exception as e:
                    print(f"Error loading embedding for repo {row['repository_id']}: {e}")
        
        if not embeddings:
            return jsonify({"recommended_repo_ids": []}), 200  # No valid embeddings
        
        print("LIKED ARE EMBEDDED")
        user_preference_vector = np.mean(embeddings, axis=0).astype('float32')
        print("user_preference_vector")

        # Perform FAISS search
        user_preference_vector = np.expand_dims(user_preference_vector, axis=0)
        distances, indices = index.search(user_preference_vector, k * 2)  # Fetch more to account for filtering
        
        # Gather similar repository IDs
        similar_repo_ids = []
        for idx in indices[0]:
            if idx < len(repository_ids):
                repo_id = repository_ids[idx]
                if repo_id not in liked_repo_ids and repo_id not in similar_repo_ids:
                    similar_repo_ids.append(repo_id)
                if len(similar_repo_ids) >= k:
                    break
        
        # Close the database connection
        conn.close()
        
        return jsonify({"recommended_repo_ids": similar_repo_ids}), 200
    
    except Exception as e:
        print(f"Error updating recommendations: {e}")
        return jsonify({"error": "An error occurred while updating recommendations."}), 500


@app.route('/reload_vectors', methods=['POST'])
def reload_vectors():
    """
    Endpoint to reload vectors from the database into the FAISS index.
    Useful if the main database has been updated with new repositories.
    """
    load_vectors_into_faiss()
    return jsonify({"message": "FAISS index reloaded."}), 200

if __name__ == '__main__':
    print("Loading vectors into FAISS index...")
    load_vectors_into_faiss()
    app.run(host='0.0.0.0', port=5001, debug=True)
