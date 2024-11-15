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
    user_id INTEGER,
    name TEXT,
    description TEXT DEFAULT '',
    created_time TIMESTAMP,
    is_open BOOLEAN DEFAULT 1, -- 1 for open, 0 for closed
    diagram TEXT, -- Path to the diagram image
    UNIQUE(user_id, name),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
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
