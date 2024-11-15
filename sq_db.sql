-- CREATE TABLE users (
--     id INTEGER PRIMARY KEY AUTOINCREMENT,
--     name TEXT NOT NULL,
--     email TEXT NOT NULL UNIQUE,
--     psw TEXT NOT NULL,
--     created_at INTEGER NOT NULL
-- );
-- Create users table
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    psw TEXT NOT NULL,
    created_at INTEGER NOT NULL
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
