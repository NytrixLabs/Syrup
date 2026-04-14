
import hashlib
import json
import os
import secrets
import shutil
import sqlite3
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path

SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8080
UPLOAD_DIR = Path("./uploads")
DB_PATH = "./server.db"
MAX_PACKAGE_SIZE_GB = 2
MAX_PACKAGE_SIZE_BYTES = MAX_PACKAGE_SIZE_GB * 1024 * 1024 * 1024

UPLOAD_DIR.mkdir(exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS packages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            filename TEXT NOT NULL,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    
    conn.commit()
    conn.close()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def generate_token():
    return secrets.token_hex(32)

def get_user_by_username(username):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, password_hash FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    return user

def get_user_by_token(token):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.id, u.username 
        FROM users u 
        JOIN tokens t ON u.id = t.user_id 
        WHERE t.token = ?
        """)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", 
                      (username, password_hash))
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        return user_id
    except sqlite3.IntegrityError:
        conn.close()
        return None

def create_token(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    token = generate_token()
    cursor.execute("INSERT INTO tokens (user_id, token) VALUES (?, ?)", (user_id, token))
    conn.commit()
    conn.close()
    return token

def delete_token(token):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tokens WHERE token = ?", (token,))
    conn.commit()
    conn.close()

def save_package(user_id, name, filename):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO packages (user_id, name, filename) VALUES (?, ?, ?)",
                  (user_id, name, filename))
    conn.commit()
    conn.close()

def get_package(username, name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.filename, u.username 
        FROM packages p 
        JOIN users u ON p.user_id = u.id 
        WHERE u.username = ? AND p.name = ?
    """, (username, name))
    package = cursor.fetchone()
    conn.close()
    return package

def list_packages(username=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if username:
        cursor.execute("""
            SELECT u.username, p.name, p.uploaded_at 
            FROM packages p 
            JOIN users u ON p.user_id = u.id 
            WHERE u.username = ?
        """, (username,))
    else:
        cursor.execute("""
            SELECT u.username, p.name, p.uploaded_at 
            FROM packages p 
            JOIN users u ON p.user_id = u.id
        """)
    packages = cursor.fetchall()
    conn.close()
    return packages

class SyrupHandler(BaseHTTPRequestHandler):
    def send_json_response(self, status_code, data):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def get_token_from_headers(self):
        auth_header = self.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            return auth_header[7:]
        return None
    
    def do_GET(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        query = parse_qs(parsed_path.query)
        
        if path == '/api/packages':
            username = query.get('user', [None])[0]
            packages = list_packages(username)
            result = [{"username": p[0], "name": p[1], "uploaded_at": p[2]} for p in packages]
            self.send_json_response(200, {"packages": result})
        
        elif path.startswith('/api/download/'):
            parts = path.split('/')
            if len(parts) >= 4:
                username = parts[3]
                name = parts[4] if len(parts) > 4 else None
                
                if name:
                    package = get_package(username, name)
                    if package:
                        filename = package[0]
                        filepath = UPLOAD_DIR / username / filename
                        if filepath.exists():
                            self.send_response(200)
                            self.send_header('Content-Type', 'application/octet-stream')
                            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
                            self.end_headers()
                            with open(filepath, 'rb') as f:
                                self.wfile.write(f.read())
                            return
                        else:
                            self.send_json_response(404, {"error": "Package file not found"})
                            return
                    else:
                        self.send_json_response(404, {"error": "Package not found"})
                        return
            
            self.send_json_response(400, {"error": "Invalid download path"})
        
        elif path == '/api/user':
            token = self.get_token_from_headers()
            if not token:
                self.send_json_response(401, {"error": "No token provided"})
                return
            user = get_user_by_token(token)
            if user:
                self.send_json_response(200, {"id": user[0], "username": user[1]})
            else:
                self.send_json_response(401, {"error": "Invalid token"})
        
        else:
            self.send_json_response(404, {"error": "Not found"})
    
    def do_POST(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode() if content_length > 0 else '{}'
        
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            data = {}
        
        if path == '/api/register':
            username = data.get('username')
            password = data.get('password')
            
            if not username or not password:
                self.send_json_response(400, {"error": "Username and password required"})
                return
            
            if len(username) < 3:
                self.send_json_response(400, {"error": "Username must be at least 3 characters"})
                return
            
            if len(password) < 6:
                self.send_json_response(400, {"error": "Password must be at least 6 characters"})
                return
            
            password_hash = hash_password(password)
            user_id = create_user(username, password_hash)
            
            if user_id:
                token = create_token(user_id)
                self.send_json_response(201, {"message": "User registered", "token": token, "username": username})
            else:
                self.send_json_response(400, {"error": "Username already exists"})
        
        elif path == '/api/login':
            username = data.get('username')
            password = data.get('password')
            
            if not username or not password:
                self.send_json_response(400, {"error": "Username and password required"})
                return
            
            user = get_user_by_username(username)
            if user and user[2] == hash_password(password):
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM tokens WHERE user_id = ?", (user[0],))
                conn.commit()
                conn.close()
                
                token = create_token(user[0])
                self.send_json_response(200, {"message": "Login successful", "token": token, "username": user[1]})
            else:
                self.send_json_response(401, {"error": "Invalid credentials"})
        
        elif path == '/api/logout':
            token = self.get_token_from_headers()
            if not token:
                self.send_json_response(401, {"error": "No token provided"})
                return
            
            delete_token(token)
            self.send_json_response(200, {"message": "Logged out successfully"})
        
        elif path == '/api/upload':
            token = self.get_token_from_headers()
            if not token:
                self.send_json_response(401, {"error": "No token provided"})
                return
            
            user = get_user_by_token(token)
            if not user:
                self.send_json_response(401, {"error": "Invalid token"})
                return
            
            user_id = user[0]
            username = user[1]
            
            package_name = self.headers.get('X-Package-Name', data.get('name'))
            
            if not package_name:
                self.send_json_response(400, {"error": "Package name required"})
                return
            
            if content_length > MAX_PACKAGE_SIZE_BYTES:
                self.send_json_response(413, {"error": f"File too large. Maximum size is {MAX_PACKAGE_SIZE_GB}GB"})
                return
            
            content_type = self.headers.get('Content-Type', '')
            
            if 'multipart/form-data' in content_type:
                boundary = content_type.split('boundary=')[1] if 'boundary=' in content_type else None
                if boundary:
                    parts = body.split(f'--{boundary}')
                    file_data = None
                    for part in parts:
                        if 'filename=' in part:
                            lines = part.split('\r\n\r\n', 1)
                            if len(lines) > 1:
                                file_data = lines[1].rstrip('\r\n--').encode() if isinstance(lines[1], str) else lines[1]
                                file_data = file_data.rstrip(b'\r\n--')
                    
                    if file_data:
                        if len(file_data) > MAX_PACKAGE_SIZE_BYTES:
                            self.send_json_response(413, {"error": f"File too large. Maximum size is {MAX_PACKAGE_SIZE_GB}GB"})
                            return
                        
                        user_upload_dir = UPLOAD_DIR / username
                        user_upload_dir.mkdir(exist_ok=True)
                        
                        filename = f"{package_name}.syp"
                        filepath = user_upload_dir / filename
                        
                        with open(filepath, 'wb') as f:
                            f.write(file_data)
                        
                        save_package(user_id, package_name, filename)
                        self.send_json_response(201, {"message": "Package uploaded", "filename": filename})
                        return
            
            if content_length > 0:
                user_upload_dir = UPLOAD_DIR / username
                user_upload_dir.mkdir(exist_ok=True)
                filename = f"{package_name}.syp"
                filepath = user_upload_dir / filename
                
                file_content = self.rfile.read(content_length) if hasattr(self.rfile, 'read') else body.encode()
                if len(file_content) > MAX_PACKAGE_SIZE_BYTES:
                    self.send_json_response(413, {"error": f"File too large. Maximum size is {MAX_PACKAGE_SIZE_GB}GB"})
                    return
                
                with open(filepath, 'wb') as f:
                    f.write(file_content)
                
                save_package(user_id, package_name, filename)
                self.send_json_response(201, {"message": "Package uploaded", "filename": filename})
            else:
                self.send_json_response(400, {"error": "No file content provided"})
        
        else:
            self.send_json_response(404, {"error": "Not found"})
    
    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {args[0]}")

def main():
    init_db()
    
    server = HTTPServer((SERVER_HOST, SERVER_PORT), SyrupHandler)
    print(f"Syrup Server starting on http://{SERVER_HOST}:{SERVER_PORT}")
    print("API Endpoints:")
    print("  POST /api/register - Register new user")
    print("  POST /api/login    - Login user")
    print("  POST /api/logout   - Logout user (requires Bearer token)")
    print("  POST /api/upload   - Upload .syp file (requires Bearer token)")
    print("  GET  /api/packages - List packages")
    print("  GET  /api/download/@username/name - Download package")
    print("  GET  /api/user     - Get current user info")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.shutdown()

if __name__ == "__main__":
    main()
