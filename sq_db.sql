CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    username TEXT NOT NULL UNIQUE,
    organization TEXT,
    country TEXT,
    city TEXT,
    address TEXT,
    phone_number TEXT,
    email TEXT NOT NULL UNIQUE,
    psw TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    is_verified INTEGER DEFAULT 0,  -- 0 = Not Verified, 1 = Verified
    recomended_repo_ids TEXT DEFAULT '[]'
);


-- Create repositories table with 'description' and 'diagram'
CREATE TABLE IF NOT EXISTS repositories (
    repository_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    created_time INTEGER NOT NULL,
    is_open INTEGER NOT NULL,
    diagram TEXT,
    is_description_ai_generated INTEGER DEFAULT 0,
    vector BLOB,  -- Column for storing vector embeddings
    FOREIGN KEY(user_id) REFERENCES users(id)
);


-- Create uploads table
CREATE TABLE IF NOT EXISTS uploads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    repository_id INTEGER,
    filename TEXT,
    filepath TEXT,
    upload_time TIMESTAMP,
    description TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(repository_id) REFERENCES repositories(repository_id) ON DELETE CASCADE
);


-- Create likes table to track user likes on repositories
CREATE TABLE IF NOT EXISTS likes (
    user_id INTEGER NOT NULL,
    repository_id INTEGER NOT NULL,
    liked_at INTEGER NOT NULL,
    PRIMARY KEY (user_id, repository_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (repository_id) REFERENCES repositories(repository_id) ON DELETE CASCADE
);
