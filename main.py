import sqlite3
from dotenv import load_dotenv
import os
from flask import Flask, render_template, request, g, flash, redirect, url_for
from flask import send_file
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename
from UserLogin import UserLogin
import time
from datetime import datetime
from flask import jsonify
from openai import OpenAI
import pickle
import faiss
import numpy as np
from pygments import highlight
from pygments.lexers import get_lexer_for_filename, TextLexer
from pygments.formatters import HtmlFormatter
import io
import zipfile
import requests


# from VctSrch import vector_search_repos, description_to_embedding

load_dotenv()

client = OpenAI(
    api_key=os.environ.get("API_KEY")
)

VECTOR_SEARCH_URL = "http://127.0.0.1:5001/vector_search"
DESCRIPTION_TO_EMBEDDING_URL = "http://127.0.0.1:5001/description_to_embedding"

ALLOWED_EXTENSIONS = {'.py', '.java', '.cpp', '.js', '.html', '.css', '.doc', '.cfg', '.txt'}

app = Flask(__name__)
app.config['DATABASE'] = os.path.join(app.root_path, 'database.db')
# app.config['CONFIGS_DATABASE'] = os.path.join(app.root_path, 'configs.db')
app.config['SECRET_KEY'] = 'SECRET'
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'uploads')
app.config['DIAGRAM_FOLDER'] = os.path.join(app.root_path, 'diagrams')
os.makedirs(app.config['DIAGRAM_FOLDER'], exist_ok=True)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
app.app_context()

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "info"

def create_db():
    """Helper function to create main database tables."""
    db = connect_db(app.config['DATABASE'])
    try:
        with app.open_resource('sq_db.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()
    except sqlite3.Error as e:
        print(f"Error creating main database tables: {e}")
    finally:
        db.close()

# user_id, repository_id, filename, filepath, upload_time
def get_db():
    if not hasattr(g, 'link_db'):
        g.link_db = connect_db(app.config['DATABASE'])
    return g.link_db

# db = get_db()

def connect_db(db_path):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def get_db():
    if not hasattr(g, 'link_db'):
        g.link_db = connect_db(app.config['DATABASE'])
    return g.link_db

# def get_db():
#     if not hasattr(g, 'db'):
#         g.db = connect_db(app.config['CONFIGS_DATABASE'])
#     return g.db

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
            self.__cur.execute("SELECT * FROM users WHERE username = ? LIMIT 1", (name,))
            user = self.__cur.fetchone()
            if user:
                print(f"User found: {user['username']} (ID: {user['id']})")
            else:
                print(f"No user found with username: {name}")
            return user
        except sqlite3.Error as e:
            print("Error retrieving user by username from DB: " + str(e))
            return False

    def addUser(self, first_name, last_name, username, email, hpsw, organization=None, country=None, city=None, address=None, phone_number=None):
        try:
            # Check if email or username already exists
            self.__cur.execute("SELECT COUNT() as `count` FROM users WHERE email = ? OR username = ?", (email, username))
            if self.__cur.fetchone()['count'] > 0:
                return False

            self.__cur.execute("""
                INSERT INTO users 
                (first_name, last_name, username, email, psw, organization, country, city, address, phone_number, created_at) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                first_name,
                last_name,
                username,
                email,
                hpsw,
                organization,
                country,
                city,
                address,
                phone_number,
                int(time.time())
            ))
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
    g.db = get_db()

    
@app.template_filter('datetimeformat')
def datetimeformat(value, format='%Y-%m-%d %H:%M'):
    return datetime.fromtimestamp(value).strftime(format)

def repo_name_from_file(file):
    db = get_db()
    repo = db.execute("""
        SELECT r.name, u.name as author
        FROM repositories r
        JOIN users u ON r.user_id = u.id
        WHERE r.repository_id = ?
    """, (file['repository_id'],)).fetchone()
    if repo:
        return repo['name'], repo['author']
    return None, None

def allowed_file(filename):
    return '.' in filename and os.path.splitext(filename)[1].lower() in ALLOWED_EXTENSIONS

def read_repository_files(repo_dir):
    file_contents = ""
    for root, dirs, files in os.walk(repo_dir):
        for file in files:
            file_path = os.path.join(root, file)
            # Only process text-based files
            if allowed_file(file):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        # Limit content to avoid exceeding token limits
                        content = content[:2000]  # Read first 1000 characters
                        file_contents += f"\n### File: {file}\n{content}\n"
                except Exception as e:
                    print(f"Error reading file {file_path}: {e}")
    return file_contents


def generate_description(file_contents, current_description):
    prompt = f"""
    Here is the current description of the repository:

    {current_description}

    Here are the contents of the repository files:

    {file_contents}

    Based on the above, please provide a concise and informative description for this repository.
    """

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",  # Replace with "gpt-3.5-turbo" if needed
            messages=[
                {"role": "system", "content": "You are a helpful assistant that writes repository descriptions."},
                {"role": "user", "content": prompt}
            ]
        )
        description = response.choices[0].message.content
        return description
    except Exception as e:
        print(f"Error generating description: {e}")
        return None


def description_to_embedding(description):
    """
    Send a description to the vector search service to generate an embedding.
    """
    try:
        response = requests.post(
            DESCRIPTION_TO_EMBEDDING_URL,
            json={"description": description}
        )
        if response.status_code == 200:
            data = response.json()
            return np.array(data["embedding"], dtype='float32')
        else:
            print(f"Error generating embedding: {response.json()}")
            return None
    except Exception as e:
        print(f"Error connecting to embedding service: {e}")
        return None
    
def vector_search_repos(db, query, k=5):
    """
    Send a search query to the vector search microservice and retrieve similar repository IDs.
    """
    try:
        response = requests.post(
            VECTOR_SEARCH_URL,
            json={"query": query, "k": k}
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("similar_repo_ids", [])
        else:
            print(f"Error in vector search: {response.json()}")
            return []
    except Exception as e:
        print(f"Error connecting to vector search service: {e}")
        return []




@app.route("/", methods=["POST", "GET"])
def lol():
    return redirect(url_for('profile'))


@app.route("/login", methods=["POST", "GET"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('profile'))

    if request.method == "POST":
        db = get_db()
        dbase = FDataBase(db)
        identifier = request.form['identifier'].strip()  # Can be email or username
        password = request.form['password']

        # Determine if the identifier is an email or username
        if "@" in identifier:
            user = dbase.getUserByEmail(identifier)
        else:
            user = dbase.getUserByName(identifier)

        if user and check_password_hash(user['psw'], password):
            userlogin = UserLogin().create(user)
            login_user(userlogin, remember=True if request.form.get('remember') else False)
            return redirect(request.args.get("next") or url_for("profile"))

        flash("Invalid credentials.", "error")

    return render_template("login.html")



@app.route("/register", methods=["POST", "GET"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('profile'))

    if request.method == "POST":
        db = get_db()
        dbase = FDataBase(db)

        # Retrieve form data
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()

        # Optional fields
        organization = request.form.get('organization', '').strip() or None
        country = request.form.get('country', '').strip() or None
        city = request.form.get('city', '').strip() or None
        address = request.form.get('address', '').strip() or None
        phone_number = request.form.get('phone_number', '').strip() or None

        # Validate required fields
        if not first_name or not last_name or not username or not email or not password:
            flash("Please fill out all required fields.", "error")
            return render_template("register.html")

        if len(username) < 4:
            flash("Username must be at least 4 characters long.", "error")
            return render_template("register.html")

        # Hash the password
        hashed_password = generate_password_hash(password)

        # Attempt to add the user
        if dbase.addUser(first_name, last_name, username, email, hashed_password, organization, country, city, address, phone_number):
            user = dbase.getUserByEmail(email)
            userlogin = UserLogin().create(user)
            login_user(userlogin, remember=False)
            flash("Registration successful!", "success")
            return redirect(url_for("profile"))
        else:
            flash("Registration failed. Email or username may already be in use.", "error")

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
    db = get_db()
    dbase = FDataBase(db)

    # Fetch the current user's data
    user = dbase.getUserByID(current_user.get_id())

    if not user:
        flash("User not found.", "error")
        return redirect(url_for('logout'))

    if request.method == "POST":
        # Handle profile update form
        if 'update_profile' in request.form:
            # Get updated form data
            first_name = request.form.get('first_name', '').strip()
            last_name = request.form.get('last_name', '').strip()
            username = request.form.get('username', '').strip()
            organization = request.form.get('organization', '').strip() or None
            country = request.form.get('country', '').strip() or None
            city = request.form.get('city', '').strip() or None
            address = request.form.get('address', '').strip() or None
            phone_number = request.form.get('phone_number', '').strip() or None

            # Validation
            if not first_name or not last_name or not username:
                flash("First name, last name, and username are required.", "error")
                return render_template("profile.html", user=user)

            if len(username) < 4:
                flash("Username must be at least 4 characters long.", "error")
                return render_template("profile.html", user=user)

            # Check if the username is already taken by another user
            existing_user = db.execute("""
                SELECT id FROM users WHERE username = ? AND id != ?
            """, (username, current_user.get_id())).fetchone()
            if existing_user:
                flash("Username is already taken by another user.", "error")
                return render_template("profile.html", user=user)

            # Update the user's data in the database
            try:
                db.execute("""
                    UPDATE users
                    SET first_name = ?, last_name = ?, username = ?, organization = ?, country = ?, city = ?, address = ?, phone_number = ?
                    WHERE id = ?
                """, (
                    first_name, last_name, username, organization, country, city, address, phone_number, current_user.get_id()
                ))
                db.commit()
                flash("Profile updated successfully!", "success")
            except sqlite3.Error as e:
                flash(f"Error updating profile: {e}", "error")

            # Fetch updated user data for display
            user = dbase.getUserByID(current_user.get_id())

        # Handle vector search form
        elif 'vector_search' in request.form:
            search_query = request.form.get('search_query', '').strip()
            if search_query:
                return redirect(url_for('vector_search', query=search_query))

    return render_template("profile.html", user=user)


 
@app.route('/create_repo', methods=["GET", "POST"])
@login_required
def create_repo():
    if request.method == "POST":
        repo_name = request.form.get('repo_name').strip()
        description = request.form.get('description', '').strip()
        is_open = request.form.get('is_open') == 'on'  # Checkbox for open/closed
        use_ai = request.form.get('use_ai') == 'on'    # Checkbox for AI description
        diagram = request.files.get('diagram')        # Diagram upload

        if not repo_name:
            flash("Repository name is required.", "error")
            return redirect(url_for('create_repo'))

        # Check if repository name already exists for the user
        db = get_db()
        existing_repo = db.execute("""
            SELECT * FROM repositories WHERE user_id = ? AND LOWER(name) = LOWER(?)
        """, (current_user.get_id(), repo_name)).fetchone()

        if existing_repo:
            flash("You already have a repository with this name.", "error")
            return redirect(url_for('create_repo'))

        # Create directory for the new repository
        repo_dir = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(repo_name))
        os.makedirs(repo_dir, exist_ok=True)

        # Handle diagram upload
        diagram_path = None
        if diagram and diagram.filename:
            diagram_filename = secure_filename(diagram.filename)
            diagram_path = os.path.join(app.config['DIAGRAM_FOLDER'], diagram_filename)
            diagram.save(diagram_path)

        # Placeholder for description; will be updated if AI is used
        final_description = description
        is_description_ai_generated = 0
        if use_ai:
            # Temporarily insert the repository without description to get repo_id
            db.execute("""
                INSERT INTO repositories (user_id, name, description, created_time, is_open, diagram, is_description_ai_generated)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                current_user.get_id(),
                repo_name,
                "",  # Temporary description
                int(time.time()),
                int(is_open),
                diagram_path,
                1  # Indicate that description will be AI-generated
            ))
            db.commit()

            # Get repository ID
            repo_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

            # Handle uploaded files
            files = request.files.getlist('files')
            for file in files:
                if file and file.filename:
                    if not allowed_file(file.filename):
                        flash(f"File '{file.filename}' is not an allowed file type.", "error")
                        continue
                    filename = secure_filename(file.filename)
                    filepath = os.path.join(repo_dir, filename)
                    file.save(filepath)

                    # Insert file info into uploads table
                    db.execute("""
                        INSERT INTO uploads (user_id, repository_id, filename, filepath, upload_time)
                        VALUES (?, ?, ?, ?, ?)
                    """, (current_user.get_id(), repo_id, filename, filepath, int(time.time())))
            db.commit()

            # Read repository files and generate new description
            file_contents = read_repository_files(repo_dir)
            if file_contents:
                new_description = generate_description(file_contents, description)
                if new_description:
                    # Update the repository's description in the database
                    db.execute("""
                        UPDATE repositories SET description = ? WHERE repository_id = ?
                    """, (new_description, repo_id))
                    db.commit()
                    final_description = new_description
                    flash("Repository created and description generated successfully.", "success")
                else:
                    flash("Repository created but failed to generate description.", "warning")
            else:
                flash("Repository created but no files to generate description.", "warning")

            if final_description:
                embedding = description_to_embedding(final_description)
                embedding_blob = pickle.dumps(embedding)
                db.execute("""
                    UPDATE repositories SET vector = ? WHERE repository_id = ?
                """, (embedding_blob, repo_id))
                db.commit()
        else:
            # Insert repository with user-provided description
            db.execute("""
                INSERT INTO repositories (user_id, name, description, created_time, is_open, diagram, is_description_ai_generated)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                current_user.get_id(),
                repo_name,
                description,
                int(time.time()),
                int(is_open),
                diagram_path,
                0  # Indicate that description is user-provided
            ))
            db.commit()

            # Get repository ID
            repo_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

            # Handle uploaded files
            files = request.files.getlist('files')
            for file in files:
                if file and file.filename:
                    if not allowed_file(file.filename):
                        flash(f"File '{file.filename}' is not an allowed file type.", "error")
                        continue
                    filename = secure_filename(file.filename)
                    filepath = os.path.join(repo_dir, filename)
                    file.save(filepath)

                    # Insert file info into uploads table
                    db.execute("""
                        INSERT INTO uploads (user_id, repository_id, filename, filepath, upload_time)
                        VALUES (?, ?, ?, ?, ?)
                    """, (current_user.get_id(), repo_id, filename, filepath, int(time.time())))
            db.commit()


            if description:
                embedding = description_to_embedding(description)
                embedding_blob = pickle.dumps(embedding)
                db.execute("""
                    UPDATE repositories SET vector = ? WHERE repository_id = ?
                """, (embedding_blob, repo_id))
                db.commit()
            flash("Repository created successfully.", "success")
            
        try:
            response = requests.post("http://127.0.0.1:5001/reload_vectors")
            if response.status_code == 200:
                print("Vector search index reloaded successfully.")
            else:
                print("Failed to reload vector search index.")
        except Exception as e:
            print(f"Error reloading vector search index: {e}")
        return redirect(url_for('view_repositories'))

    return render_template("create_repo.html")


# If diagrams are stored outside the static folder, consider serving them securely
@app.route('/diagram/<int:repo_id>')
@login_required
def get_diagram(repo_id):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT diagram, is_open, user_id FROM repositories WHERE repository_id = ?", (repo_id,))
    repo = cur.fetchone()

    if repo and repo['diagram']:
        # Check access permissions
        if repo['is_open'] or repo['user_id'] == current_user.get_id():
            if os.path.exists(repo['diagram']):
                return send_file(repo['diagram'], mimetype='image/*')
            else:
                flash("Diagram not found on the server.", "error")
        else:
            flash("You do not have permission to view this diagram.", "error")
    else:
        flash("Diagram not found in the database.", "error")

    return redirect(url_for('view_repositories'))


@app.route('/repo/<string:author>/<string:repo_name>', methods=["GET", "POST"])
@login_required
def view_repository(author, repo_name):
    db = get_db()
    dbase = FDataBase(db)
    user = dbase.getUserByName(author)

    if not user:
        flash("Author not found.", "error")
        return redirect(url_for('view_repositories'))

    repo = db.execute("""
        SELECT * FROM repositories WHERE user_id = ? AND name = ?
    """, (user['id'], repo_name)).fetchone()

    if not repo:
        flash("Repository not found.", "error")
        return redirect(url_for('view_repositories'))

    # **Access Control**:
    # - If the repo is closed, only the owner can access.
    # - If the repo is open, any authenticated user can view.
    if not repo['is_open'] and int(repo['user_id']) != int(current_user.get_id()):
        flash("You do not have permission to access this repository.", "error")
        return redirect(url_for('view_repositories'))

    # Handle updates (only the author can make changes)
    if request.method == "POST" and int(repo['user_id']) == int(current_user.get_id()):
        action = request.form.get('action')

        if action == "add_files":
            files = request.files.getlist('files')
            repo_dir = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(repo['name']))
            for file in files:
                if not allowed_file(file.filename):
                    flash(f"File '{file.filename}' is not an allowed file type.", "error")
                    continue
                if file and file.filename:
                    filename = secure_filename(file.filename)
                    filepath = os.path.join(repo_dir, filename)
                    file.save(filepath)
                    db.execute("""
                        INSERT INTO uploads (user_id, repository_id, filename, filepath, upload_time)
                        VALUES (?, ?, ?, ?, ?)
                    """, (current_user.get_id(), repo['repository_id'], filename, filepath, int(time.time())))
            db.commit()

            # Regenerate description if AI was previously used or if user opts to
            regenerate = request.form.get('regenerate_description') == 'on'
            use_ai = request.form.get('use_ai') == 'on'

            if regenerate or use_ai:
                file_contents = read_repository_files(repo_dir)
                current_description = repo['description'] if repo['description'] else ""
                if file_contents:
                    new_description = generate_description(file_contents, current_description)
                    if new_description:
                        # Update the repository's description in the database
                        db.execute("""
                            UPDATE repositories 
                            SET description = ?, is_description_ai_generated = ?
                            WHERE repository_id = ?
                        """, (new_description, 1 if use_ai else repo['is_description_ai_generated'], repo['repository_id']))
                        db.commit()
                        flash("Files added and description updated successfully.", "success")
                    else:
                        flash("Files added but failed to update description.", "warning")
                else:
                    flash("Files added but no files to generate description.", "warning")

            else:
                flash("Files added successfully.", "success")

        elif action == "update_description":
            new_description = request.form.get('description', '').strip()
            use_ai = request.form.get('use_ai') == 'on'  # Checkbox for AI description

            if use_ai:
                repo_dir = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(repo['name']))
                file_contents = read_repository_files(repo_dir)
                if file_contents:
                    generated_description = generate_description(file_contents, new_description)
                    if generated_description:

                        embedding = description_to_embedding(generated_description)
                        embedding_blob = pickle.dumps(embedding)
                        # Update the repository's description in the database
                        db.execute("""
                            UPDATE repositories 
                            SET description = ?, is_description_ai_generated = ?, vector = ?
                            WHERE repository_id = ?
                            """, (generated_description, 1, embedding_blob, repo['repository_id']))
                        db.commit()
                        flash("Description updated using AI.", "success")

                    else:
                        flash("Failed to generate description using AI.", "warning")
                else:
                    flash("No files to generate description.", "warning")
            else:
                # Update with user-provided description
                db.execute("""
                    UPDATE repositories 
                    SET description = ?, is_description_ai_generated = ?, vector = ?
                    WHERE repository_id = ?
                """, (new_description, 0, pickle.dumps(description_to_embedding(new_description)), repo['repository_id']))
                db.commit()
                flash("Description updated successfully.", "success")

        elif action == "update_diagram":
            new_diagram = request.files.get('diagram')
            if new_diagram and new_diagram.filename:
                diagram_filename = secure_filename(new_diagram.filename)
                diagram_path = os.path.join(app.config['DIAGRAM_FOLDER'], diagram_filename)
                new_diagram.save(diagram_path)
                # Optionally, remove the old diagram file
                if repo['diagram'] and os.path.exists(repo['diagram']):
                    os.remove(repo['diagram'])
                # Update the diagram path in the database
                db.execute("""
                    UPDATE repositories SET diagram = ? WHERE repository_id = ?
                """, (diagram_path, repo['repository_id']))
                db.commit()
                flash("Diagram updated successfully.", "success")

        return redirect(url_for('view_repository', author=author, repo_name=repo_name))

    # Fetch all files in the repository
    files = db.execute("""
        SELECT * FROM uploads WHERE repository_id = ?
    """, (repo['repository_id'],)).fetchall()

    # Fetch description from the database
    description = repo['description'] if repo['description'] else ""

    # Fetch the diagram path
    diagram = repo['diagram'] if repo['diagram'] and os.path.exists(repo['diagram']) else None

    return render_template("view_repository.html", repo=repo, files=files, description=description, author=author, diagram=diagram)

@app.route('/repo/<int:repo_id>/file/<int:file_id>')
@login_required
def view_repo(repo_id, file_id):
    db = get_db()
    cursor = db.execute("""
        SELECT u.*, r.user_id as repo_owner_id, r.is_open
        FROM uploads u
        JOIN repositories r ON u.repository_id = r.repository_id
        WHERE u.id = ? AND u.repository_id = ?
    """, (file_id, repo_id))
    file = cursor.fetchone()

    if not file:
        flash("File not found.", "error")
        return redirect(url_for('view_repositories'))

    repo_owner_id = file['repo_owner_id']
    is_open = file['is_open']

    # Access Control
    if not is_open and repo_owner_id != int(current_user.get_id()):
        flash("You do not have permission to view this file.", "error")
        return redirect(url_for('view_repositories'))

    # Read file content
    try:
        with open(file['filepath'], 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        flash(f"Error reading file: {e}", "error")
        return redirect(url_for('view_repository', author=db.execute("SELECT username FROM users WHERE id = ?", (repo_owner_id,)).fetchone()['username'], repo_name=db.execute("SELECT name FROM repositories WHERE repository_id = ?", (repo_id,)).fetchone()['name']))

    # Optional: Syntax Highlighting using Pygments
    try:
        lexer = get_lexer_for_filename(file['filename'])
    except:
        lexer = TextLexer()

    formatter = HtmlFormatter(linenos=True, cssclass="source")
    highlighted_content = highlight(content, lexer, formatter)

    return render_template("view_file.html", file=file, repo=db.execute("SELECT * FROM repositories WHERE repository_id = ?", (repo_id,)).fetchone(), author=db.execute("SELECT username FROM users WHERE id = ?", (repo_owner_id,)).fetchone()['username'], content=highlighted_content)

@app.route('/repo/<int:repo_id>/download_zip')
@login_required
def download_repo_zip(repo_id):
    db = get_db()
    cursor = db.execute("""
        SELECT * FROM repositories WHERE repository_id = ?
    """, (repo_id,))
    repo = cursor.fetchone()

    if not repo:
        flash("Repository not found.", "error")
        return redirect(url_for('view_repositories'))

    # Access Control
    if not repo['is_open'] and int(repo['user_id']) != int(current_user.get_id()):
        flash("You do not have permission to download this repository.", "error")
        return redirect(url_for('view_repositories'))

    repo_dir = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(repo['name']))
    if not os.path.exists(repo_dir):
        flash("Repository files not found on the server.", "error")
        return redirect(url_for('view_repository', author=db.execute("SELECT username FROM users WHERE id = ?", (repo['user_id'],)).fetchone()['username'], repo_name=repo['name']))

    # Create a ZIP in memory
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(repo_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, repo_dir)
                zipf.write(file_path, arcname)

    memory_file.seek(0)

    return send_file(
        memory_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f"{repo['name']}.zip"
    )

@app.route('/delete_file/<int:file_id>', methods=["POST", "GET"])
@login_required
def delete_file(file_id):
    db = get_db()
    dbase = FDataBase(db)
    current_user_id = int(current_user.get_id())

    cursor = db.execute("SELECT * FROM uploads WHERE id = ? AND user_id = ?", (file_id, current_user_id))
    file = cursor.fetchone()

    if not file:
        flash("File not found or you don't have permission to delete it.", "error")
        return redirect(url_for('view_repositories'))

    repo_id = file['repository_id']
    cursor = db.execute("SELECT name, user_id, is_open FROM repositories WHERE repository_id = ?", (repo_id,))
    repo = cursor.fetchone()

    if not repo:
        flash("Repository not found.", "error")
        return redirect(url_for('view_repositories'))

    author_id = repo['user_id']
    if author_id != current_user_id:
        flash("You do not have permission to delete files from this repository.", "error")
        return redirect(url_for('view_repositories'))

    cursor = db.execute("SELECT name FROM users WHERE id = ?", (author_id,))
    author = cursor.fetchone()

    if not author:
        flash("Author not found.", "error")
        return redirect(url_for('view_repositories'))

    author_name = author['name']
    repo_name = repo['name']

    try:
        if os.path.exists(file['filepath']):
            os.remove(file['filepath'])
        else:
            flash("File not found on the server.", "warning")
    except Exception as e:
        flash(f"Error deleting file from filesystem: {e}", "error")
        return redirect(url_for('view_repository', author=author_name, repo_name=repo_name))

    try:
        db.execute("DELETE FROM uploads WHERE id = ?", (file_id,))
        db.commit()
    except sqlite3.Error as e:
        flash(f"Error deleting file from database: {e}", "error")
        return redirect(url_for('view_repository', author=author_name, repo_name=repo_name))

    flash("File deleted successfully.", "success")
    return redirect(url_for('view_repository', author=author_name, repo_name=repo_name))



@app.route('/view_repositories')
@login_required
def view_repositories():
    db = get_db()
    cur = db.cursor()

    # Fetch open repositories and user's own repositories
    cur.execute("SELECT * FROM repositories WHERE user_id = ?", (current_user.get_id(),))
    repositories = cur.fetchall()

    # Extract repository IDs
    repo_ids = [repo['repository_id'] for repo in repositories]

    files = []
    if repo_ids:
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

    return render_template("view_repositories.html", repositories=repositories, files_by_repo=files_by_repo)

@app.route('/all_repositories', methods=["GET"])
@login_required
def all_repositories():
    db = get_db()
    cursor = db.cursor()

    # Get the current user's ID
    current_user_id = int(current_user.get_id())

    # Get search query from the request
    search_query = request.args.get('search', '').strip()

    # SQL query to include open repositories and current user's repositories
    query = """
    SELECT r.repository_id, r.name AS repo_name, r.created_time, r.description, u.username,
           u.first_name || ' ' || u.last_name AS author_name
    FROM repositories r
    JOIN users u ON r.user_id = u.id
    WHERE r.is_open = 1 OR r.user_id = ?
    ORDER BY r.created_time DESC
    """
    cursor.execute(query, (current_user_id,))


    repositories = cursor.fetchall()

    # Process descriptions and filter based on search query
    repos_with_descriptions = []
    for repo in repositories:
        description = repo['description'] if repo['description'] else ""

        # Filter results based on search query if provided
        if (not search_query or 
            search_query.lower() in description.lower() or 
            search_query.lower() in repo['repo_name'].lower() or 
            search_query.lower() in repo['author_name'].lower()):
            repos_with_descriptions.append({
                'repo_id': repo['repository_id'],
                'repo_name': repo['repo_name'],
                'created_time': repo['created_time'],
                'author_name': repo['author_name'],
                'description': description[:200],
                'username': repo['username'],
            })

    # Check if the request is an AJAX request
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify(repositories=repos_with_descriptions)

    # For normal requests, render the template
    return render_template("all_repositories.html", repositories=repos_with_descriptions, search_query=search_query)


@app.route('/download/<int:file_id>')
@login_required
def download_file(file_id):
    db = get_db()
    cursor = db.execute("SELECT filename, filepath, repository_id FROM uploads WHERE id = ?", (file_id,))
    file = cursor.fetchone()

    if file and file['filepath']:
        repo_cursor = db.execute("""
            SELECT user_id, is_open FROM repositories WHERE repository_id = ?
        """, (file['repository_id'],))
        repo = repo_cursor.fetchone()

        if repo:
            # Check permissions
            if repo['is_open'] or int(repo['user_id']) == int(current_user.get_id()):
                if os.path.exists(file['filepath']):
                    return send_file(file['filepath'], as_attachment=True, download_name=file['filename'])
                else:
                    flash("File not found on the server.", "error")
            else:
                flash("You do not have permission to download this file.", "error")
        else:
            flash("Repository not found.", "error")
    else:
        flash("File not found in the database.", "error")

    return redirect(url_for('view_repositories'))

@app.route('/download_description/<int:repo_id>')
@login_required
def download_description(repo_id):
    db = get_db()
    cursor = db.execute("""
        SELECT description, is_open, user_id FROM repositories WHERE repository_id = ?
    """, (repo_id,))
    repo = cursor.fetchone()

    if not repo:
        flash("Repository not found.", "error")
        return redirect(url_for('view_repositories'))

    # Access Control
    if not repo['is_open'] and int(repo['user_id']) != int(current_user.get_id()):
        flash("You do not have permission to download this description.", "error")
        return redirect(url_for('view_repositories'))

    description = repo['description'] if repo['description'] else ""

    if description:
        from io import BytesIO
        return send_file(
            BytesIO(description.encode('utf-8')),
            mimetype='text/plain',
            as_attachment=True,
            download_name='description.txt'
        )
    else:
        flash("Description is empty.", "warning")
        return redirect(url_for('view_repository', author=db.execute("SELECT name FROM users WHERE id = ?", (repo['user_id'],)).fetchone()['name'], repo_name=db.execute("SELECT name FROM repositories WHERE repository_id = ?", (repo_id,)).fetchone()['name']))

@app.route('/repo/<string:username>/<string:repo_name>/<int:file_id>', methods=["GET"])
@login_required
def view_file(username, repo_name, file_id):
    db = get_db()

    # Fetch the user by username
    user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if not user:
        flash("User not found.", "error")
        return redirect(url_for('view_repositories'))

    # Fetch the repository by user_id and repo_name
    repo = db.execute("""
        SELECT * FROM repositories WHERE user_id = ? AND name = ?
    """, (user['id'], repo_name)).fetchone()
    if not repo:
        flash("Repository not found.", "error")
        return redirect(url_for('view_repositories'))

    # Fetch the file by repository_id and file_id
    file = db.execute("""
        SELECT * FROM uploads WHERE id = ? AND repository_id = ?
    """, (file_id, repo['repository_id'])).fetchone()
    if not file:
        flash("File not found.", "error")
        return redirect(url_for('view_repository', author=username, repo_name=repo_name))

    # Check access permissions
    if not repo['is_open'] and int(repo['user_id']) != int(current_user.get_id()):
        flash("You do not have permission to access this file.", "error")
        return redirect(url_for('view_repositories'))

    # Read the file content
    filepath = file['filepath']
    if not os.path.exists(filepath):
        flash("File not found on the server.", "error")
        return redirect(url_for('view_repository', author=username, repo_name=repo_name))

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        flash(f"Error reading file: {e}", "error")
        return redirect(url_for('view_repository', author=username, repo_name=repo_name))

    # Syntax highlighting
    try:
        lexer = get_lexer_for_filename(file['filename'], fallback=TextLexer())
    except Exception:
        lexer = TextLexer()

    formatter = HtmlFormatter(linenos=True, cssclass="source")
    highlighted_code = highlight(content, lexer, formatter)

    return render_template("view_file.html", 
                           file=file, 
                           repo=repo, 
                           highlighted_code=highlighted_code, 
                           author=username)

@app.route('/vector_search', methods=["GET", "POST"])
@login_required
def vector_search():
    if request.method == "POST":
        # Retrieve 'search_query' from POST data
        search_query = request.form.get('search_query', '').strip()
        
        if not search_query:
            flash("Search query cannot be empty.", "error")
            return render_template("vector_search.html", repositories=[])
        
        db = get_db()
        similar_repo_ids = vector_search_repos(db, search_query, k=5)
        
        if not similar_repo_ids:
            flash("No similar repositories found.", "info")
            return render_template("vector_search.html", repositories=[], search_query=search_query)
        
        # Fetch repository details
        placeholders = ','.join(['?'] * len(similar_repo_ids))
        query = f"""
            SELECT r.*, u.username as author
            FROM repositories r
            JOIN users u ON r.user_id = u.id
            WHERE r.repository_id IN ({placeholders}) AND r.is_open = 1
        """
        repos = db.execute(query, similar_repo_ids).fetchall()
        
        # Optionally, order repos based on similarity
        repos_ordered = sorted(repos, key=lambda x: similar_repo_ids.index(x['repository_id']))
        
        return render_template("vector_search.html", repositories=repos_ordered, search_query=search_query)
    
    # For GET requests, simply render the search form without results
    return render_template("vector_search.html", repositories=[])


@app.route('/user/profile/<string:username>', methods=["GET"])
@login_required
def user_profile(username):
    db = get_db()
    dbase = FDataBase(db)

    # Fetch user information by username
    user = dbase.getUserByName(username)

    if not user:
        flash("User not found.", "error")
        return redirect(url_for('view_repositories'))

    # Fetch the open repositories for this user
    repositories = db.execute("""
        SELECT r.name AS repo_name, r.description, r.created_time 
        FROM repositories r 
        WHERE r.user_id = ? AND r.is_open = 1
        ORDER BY r.created_time DESC
    """, (user['id'],)).fetchall()

    return render_template(
        "user_profile.html",
        user={
            "first_name": user['first_name'],
            "last_name": user['last_name'],
            "organization": user['organization'],
            "country": user['country'],
            "city": user['city'],
            "address": user['address'],
            "username": user['username']
        },
        repositories=repositories
    )


if __name__ == "__main__":
    try:
        create_db()
    finally:
        app.run(host='0.0.0.0', debug=True, use_reloader=False)

