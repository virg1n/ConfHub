import sqlite3
import os
from flask import Flask, render_template, request, g, flash, redirect, url_for
from flask import send_file
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename
from UserLogin import UserLogin
import time
from datetime import datetime



app = Flask(__name__)
app.config['DATABASE'] = os.path.join(app.root_path, 'flsite.db')
app.config['CONFIGS_DATABASE'] = os.path.join(app.root_path, 'configs.db')
app.config['SECRET_KEY'] = 'SECRET'
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "info"

def create_db():
    """Helper function to create main and configs database tables."""
    db = connect_db(app.config['DATABASE'])
    try:
        with app.open_resource('sq_db.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()
        db.close()
    finally:
        try:
            # Set up configs database for storing uploaded files and repositories
            configs_db = connect_db(app.config['CONFIGS_DATABASE'])
            configs_db.execute("""
            CREATE TABLE IF NOT EXISTS uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                repository_id INTEGER,
                filename TEXT,
                filepath TEXT,
                upload_time TIMESTAMP,
                description TEXT
            )
            """)
        # configs_db.commit()
        # configs_db.close()

        finally:
            configs_db.execute("""
            CREATE TABLE IF NOT EXISTS repositories (
                repository_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name TEXT,
                description_file TEXT,
                created_time TIMESTAMP,
                UNIQUE(user_id, name)
            )
            """)
            configs_db.commit()
            configs_db.close()
# user_id, repository_id, filename, filepath, upload_time


def connect_db(db_path):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def get_db():
    if not hasattr(g, 'link_db'):
        g.link_db = connect_db(app.config['DATABASE'])
    return g.link_db

def get_configs_db():
    if not hasattr(g, 'configs_db'):
        g.configs_db = connect_db(app.config['CONFIGS_DATABASE'])
    return g.configs_db

class FDataBase:
    def __init__(self, db):
        self.__db = db
        self.__cur = db.cursor()

    def getUserByEmail(self, email):
        try:
            self.__cur.execute("SELECT * FROM users WHERE email = ? LIMIT 1", (email,))
            return self.__cur.fetchone()
        except sqlite3.Error as e:
            print("Error retrieving user from DB: " + str(e))
            return False

    def getUserByID(self, id):
        try:
            self.__cur.execute("SELECT * FROM users WHERE id = ? LIMIT 1", (id,))
            return self.__cur.fetchone()
        except sqlite3.Error as e:
            print("Error retrieving user by ID from DB: " + str(e))
            return False

    def getUserByName(self, name):
        try:
            self.__cur.execute("SELECT * FROM users WHERE name = ? LIMIT 1", (name,))
            user = self.__cur.fetchone()
            if user:
                print(f"User found: {user['name']} (ID: {user['id']})")
            else:
                print(f"No user found with name: {name}")
            return user
        except sqlite3.Error as e:
            print("Error retrieving user by name from DB: " + str(e))
            return False

    def addUser(self, name, email, hpsw):
        try:
            self.__cur.execute("SELECT COUNT() as `count` FROM users WHERE email = ?", (email,))
            if self.__cur.fetchone()['count'] > 0:
                return False

            self.__cur.execute("INSERT INTO users (name, email, psw, created_at) VALUES (?, ?, ?, ?)", 
                               (name, email, hpsw, int(time.time())))
            self.__db.commit()
            return True
        except sqlite3.Error as e:
            print("Error adding user to DB: " + str(e))
            return False
    

@login_manager.user_loader
def load_user(user_id):
    db = get_db()
    dbase = FDataBase(db)
    return UserLogin().fromDB(user_id, dbase)

@app.before_request
def before_request():
    g.db = get_db()
    g.configs_db = get_configs_db()

    
@app.template_filter('datetimeformat')
def datetimeformat(value, format='%Y-%m-%d %H:%M'):
    return datetime.fromtimestamp(value).strftime(format)

def repo_name_from_file(file):
    configs_db = get_configs_db()
    repo = configs_db.execute("""
        SELECT r.name, u.name as author
        FROM repositories r
        JOIN users u ON r.user_id = u.id
        WHERE r.repository_id = ?
    """, (file['repository_id'],)).fetchone()
    if repo:
        return repo['name'], repo['author']
    return None, None


@app.route("/login", methods=["POST", "GET"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('profile'))

    if request.method == "POST":
        db = get_db()
        dbase = FDataBase(db)
        user = dbase.getUserByEmail(request.form['email'])
        if user and check_password_hash(user['psw'], request.form['password']):
            userlogin = UserLogin().create(user)
            login_user(userlogin, remember=True if request.form.get('remember') else False)
            return redirect(request.args.get("next") or url_for("profile"))

        flash("Invalid email or password", "error")

    return render_template("login.html")

@app.route("/register", methods=["POST", "GET"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('profile'))

    if request.method == "POST":
        db = get_db()
        dbase = FDataBase(db)
        if len(request.form['name']) > 4 and len(request.form['email']) > 4 and len(request.form['password']) > 4:
            hash = generate_password_hash(request.form['password'])
            if dbase.addUser(request.form['name'], request.form['email'], hash):
                user = dbase.getUserByEmail(request.form['email'])
                userlogin = UserLogin().create(user)
                login_user(userlogin, remember=False)
                return redirect(url_for("profile"))
            else:
                flash("This email is already in use", "error")
        else:
            flash("Incorrect input fields", "error")

    return render_template("register.html")

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("You have been logged out", "success")
    return redirect(url_for('login'))

@app.route('/profile', methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        file = request.files.get('file')
        if file:
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            configs_db = get_configs_db()
            configs_db.execute("""
            INSERT INTO uploads (user_id, filename, filepath, upload_time)
            VALUES (?, ?, ?, ?)
            """, (current_user.get_id(), filename, filepath, int(time.time())))
            configs_db.commit()
            flash("File uploaded successfully", "success")
        else:
            flash("No file selected", "error")

    return render_template("profile.html")
    
@app.route('/create_repo', methods=["GET", "POST"])
@login_required
def create_repo():
    if request.method == "POST":
        repo_name = request.form.get('repo_name').strip()
        description = request.form.get('description').strip()

        if not repo_name:
            flash("Repository name is required.", "error")
            return redirect(url_for('create_repo'))

        # Check if repository name already exists for the user
        configs_db = get_configs_db()
        existing_repo = configs_db.execute("""
            SELECT * FROM repositories WHERE user_id = ? AND name = ?
        """, (current_user.get_id(), repo_name)).fetchone()

        if existing_repo:
            flash("You already have a repository with this name.", "error")
            return redirect(url_for('create_repo'))

        # Create directory for the new repository
        repo_dir = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(repo_name))
        os.makedirs(repo_dir, exist_ok=True)

        # Save description as a text file
        description_file_path = os.path.join(repo_dir, "description.txt")
        with open(description_file_path, 'w') as desc_file:
            desc_file.write(description or "")

        # Save repository information to the database
        configs_db.execute("""
            INSERT INTO repositories (user_id, name, description_file, created_time)
            VALUES (?, ?, ?, ?)
        """, (current_user.get_id(), repo_name, description_file_path, int(time.time())))
        configs_db.commit()

        # Get repository ID
        repo_id = configs_db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Handle uploaded files
        files = request.files.getlist('files')
        for file in files:
            if file and file.filename:
                filename = secure_filename(file.filename)
                filepath = os.path.join(repo_dir, filename)
                file.save(filepath)

                # Insert file info into uploads table
                configs_db.execute("""
                    INSERT INTO uploads (user_id, repository_id, filename, filepath, upload_time)
                    VALUES (?, ?, ?, ?, ?)
                """, (current_user.get_id(), repo_id, filename, filepath, int(time.time())))
        configs_db.commit()

        flash("Repository created successfully with uploaded files and description.", "success")
        return redirect(url_for('view_repositories'))

    return render_template("create_repo.html")

@app.route('/debug_current_user')
@login_required
def debug_current_user():
    return f"Current user name: {current_user.name}"

@app.route('/repo/<string:author>/<string:repo_name>', methods=["GET", "POST"])
@login_required
def view_repository(author, repo_name):

    # Fetch the user by author name
    db = get_db()
    dbase = FDataBase(db)
    user = dbase.getUserByName(author)

    # Check if user was found
    if not user:
        flash("Author not found.", "error")
        return redirect(url_for('view_repositories'))

    # Fetch the repository for this user
    configs_db = get_configs_db()
    repo = configs_db.execute("""
        SELECT * FROM repositories WHERE user_id = ? AND name = ?
    """, (user['id'], repo_name)).fetchone()

    # Check if repository exists
    if not repo:
        flash("Repository not found.", "error")
        return redirect(url_for('view_repositories'))

    # **Permission Check**: Ensure current user is the owner
    # if repo['user_id'] != current_user.get_id():
    #     flash("You do not have permission to access this repository.", "error")
    #     return redirect(url_for('view_repositories'))

    # Handle updates (adding files or updating description)
    if request.method == "POST":
        action = request.form.get('action')

        if action == "add_files":
            files = request.files.getlist('files')
            repo_dir = os.path.dirname(repo['description_file'])
            for file in files:
                if file and file.filename:
                    filename = secure_filename(file.filename)
                    filepath = os.path.join(repo_dir, filename)
                    if True:
                        file.save(filepath)
                        # Insert file info into uploads table
                        configs_db.execute("""
                            INSERT INTO uploads (user_id, repository_id, filename, filepath, upload_time)
                            VALUES (?, ?, ?, ?, ?)
                        """, (current_user.get_id(), repo['repository_id'], filename, filepath, int(time.time())))
                        print(f"File uploaded: {filename}")
                    else:
                        flash(f"File {filename} has an invalid extension and was not uploaded.", "error")
            configs_db.commit()
            flash("Files added successfully.", "success")

        elif action == "update_description":
            new_description = request.form.get('description').strip()
            description_file_path = repo['description_file']
            with open(description_file_path, 'w') as desc_file:
                desc_file.write(new_description or "")
            flash("Description updated successfully.", "success")

        # Ensure redirect includes both `author` and `repo_name`
        return redirect(url_for('view_repository', author=author, repo_name=repo_name))

    # Fetch all files in the repository
    files = configs_db.execute("""
        SELECT * FROM uploads WHERE repository_id = ?
    """, (repo['repository_id'],)).fetchall()

    # Read the description
    if os.path.exists(repo['description_file']):
        with open(repo['description_file'], 'r') as desc_file:
            description = desc_file.read()
    else:
        description = ""

    return render_template("view_repository.html", repo=repo, files=files, description=description, author=author)





@app.route('/delete_file/<int:file_id>', methods=["POST", "GET"])
@login_required
def delete_file(file_id):
    configs_db = get_configs_db()
    cur = configs_db.cursor()
    cur.execute("SELECT * FROM uploads WHERE id = ? AND user_id = ?", (file_id, current_user.get_id()))
    file = cur.fetchone()

    if not file:
        flash("File not found or you don't have permission to delete it.", "error")
        return redirect(url_for('view_uploads'))

    # Get repository details for redirection
    repo = configs_db.execute("""
        SELECT r.name, u.name as author
        FROM repositories r
        JOIN users u ON r.user_id = u.id
        WHERE r.repository_id = ?
    """, (file['repository_id'],)).fetchone()

    if not repo:
        flash("Repository not found.", "error")
        return redirect(url_for('view_uploads'))

    # Delete the file from the filesystem
    if os.path.exists(file['filepath']):
        os.remove(file['filepath'])

    # Delete the record from the database
    configs_db.execute("DELETE FROM uploads WHERE id = ?", (file_id,))
    configs_db.commit()

    flash("File deleted successfully.", "success")
    return redirect(url_for('view_repository', author=repo['author'], repo_name=repo['name']))


@app.route('/view_repositories')
@login_required
def view_repositories():
    configs_db = get_configs_db()
    cur = configs_db.cursor()

    # Fetch all repositories for the current user
    cur.execute("SELECT * FROM repositories WHERE user_id = ?", (current_user.get_id(),))
    repositories = cur.fetchall()

    # Extract repository IDs
    repo_ids = [repo['repository_id'] for repo in repositories]

    files = []
    if repo_ids:
        # Dynamically create placeholders based on the number of repo_ids
        placeholders = ','.join(['?'] * len(repo_ids))
        query = f"SELECT * FROM uploads WHERE repository_id IN ({placeholders})"
        cur.execute(query, repo_ids)
        files = cur.fetchall()

    # Group files by repository_id
    files_by_repo = {}
    for file in files:
        repo_id = file['repository_id']
        if repo_id not in files_by_repo:
            files_by_repo[repo_id] = []
        files_by_repo[repo_id].append(file)

    # Pass repositories and their corresponding files to the template
    return render_template("view_repositories.html", repositories=repositories, files_by_repo=files_by_repo)




@app.route('/uploads')
@login_required
def view_uploads():
    configs_db = get_configs_db()
    cur = configs_db.cursor()
    cur.execute("SELECT id, user_id, filename, filepath, upload_time FROM uploads")
    files = cur.fetchall()

    return render_template("uploads.html", files=files)

@app.route('/download/<int:file_id>')
@login_required
def download_file(file_id):
    configs_db = get_configs_db()
    cur = configs_db.cursor()
    cur.execute("SELECT filename, filepath, repository_id FROM uploads WHERE id = ?", (file_id,))
    file = cur.fetchone()

    if file and file['filepath']:
        # Verify that the current user owns the repository containing the file
        repo = configs_db.execute("""
            SELECT user_id FROM repositories WHERE repository_id = ?
        """, (file['repository_id'],)).fetchone()

        if repo and repo['user_id'] == current_user.get_id():
            if os.path.exists(file['filepath']):
                return send_file(file['filepath'], as_attachment=True, download_name=file['filename'])
            else:
                flash("File not found on the server.", "error")
        else:
            flash("You do not have permission to download this file.", "error")
    else:
        flash("File not found in the database.", "error")

    return redirect(url_for('view_repositories'))



@app.route('/download_description/<int:repo_id>')
@login_required
def download_description(repo_id):
    configs_db = get_configs_db()
    cur = configs_db.cursor()
    cur.execute("SELECT description_file FROM repositories WHERE repository_id = ?", (repo_id,))
    repo = cur.fetchone()

    if repo and repo['description_file']:
        if os.path.exists(repo['description_file']):
            return send_file(repo['description_file'], as_attachment=True, download_name="description.txt")
        else:
            flash("Description file not found on the server.", "error")
    else:
        flash("Description file not found in the database.", "error")
    
    return redirect(url_for('view_repositories'))



if __name__ == "__main__":
    try:
        create_db()
    finally:
        app.run(host='0.0.0.0', debug=True)