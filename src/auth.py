"""
Authentication Module for Equipment Explorer

Handles user authentication, sessions, and access control.
"""

import os
import hashlib
import secrets
from datetime import datetime, timedelta
from functools import wraps
from flask import session, redirect, url_for, request, flash, g
from database import ShipCableDB


# Session configuration
SESSION_LIFETIME_HOURS = 24
SECRET_KEY = os.environ.get('SECRET_KEY', secrets.token_hex(32))


def hash_password(password: str, salt: str = None) -> tuple:
    """Hash a password with salt using SHA-256."""
    if salt is None:
        salt = secrets.token_hex(16)
    salted = f"{salt}{password}".encode('utf-8')
    hashed = hashlib.sha256(salted).hexdigest()
    return hashed, salt


def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    """Verify a password against stored hash."""
    hashed, _ = hash_password(password, salt)
    return secrets.compare_digest(hashed, stored_hash)


def init_auth_tables(db: ShipCableDB):
    """Initialize authentication-related tables."""
    with db._get_connection() as conn:
        conn.executescript('''
            -- Users table
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                email TEXT,
                role TEXT NOT NULL DEFAULT 'viewer' CHECK(role IN ('admin', 'editor', 'viewer')),
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                created_by INTEGER,
                FOREIGN KEY (created_by) REFERENCES users(user_id)
            );
            
            -- Sessions table
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                ip_address TEXT,
                user_agent TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );
            
            -- Access logs table
            CREATE TABLE IF NOT EXISTS access_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                action TEXT NOT NULL,
                details TEXT,
                ip_address TEXT,
                user_agent TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL
            );
            
            -- Error logs table  
            CREATE TABLE IF NOT EXISTS error_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                error_type TEXT NOT NULL,
                error_message TEXT NOT NULL,
                stack_trace TEXT,
                endpoint TEXT,
                user_id INTEGER,
                ip_address TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL
            );
            
            -- Application settings table
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by INTEGER,
                FOREIGN KEY (updated_by) REFERENCES users(user_id)
            );
            
            -- Indexes
            CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
            CREATE INDEX IF NOT EXISTS idx_access_logs_user ON access_logs(user_id);
            CREATE INDEX IF NOT EXISTS idx_access_logs_timestamp ON access_logs(timestamp);
            CREATE INDEX IF NOT EXISTS idx_error_logs_timestamp ON error_logs(timestamp);
            CREATE INDEX IF NOT EXISTS idx_error_logs_type ON error_logs(error_type);
        ''')


def create_default_admin(db: ShipCableDB):
    """Create default admin user if no users exist."""
    with db._get_connection() as conn:
        cursor = conn.execute('SELECT COUNT(*) FROM users')
        count = cursor.fetchone()[0]
        
        if count == 0:
            # Create default admin with password 'admin' (should be changed immediately)
            password_hash, salt = hash_password('admin')
            conn.execute('''
                INSERT INTO users (username, password_hash, password_salt, email, role)
                VALUES (?, ?, ?, ?, ?)
            ''', ('admin', password_hash, salt, 'admin@localhost', 'admin'))
            return True
    return False


class AuthManager:
    """Manages authentication operations."""
    
    def __init__(self, db: ShipCableDB):
        self.db = db
        init_auth_tables(db)
        if create_default_admin(db):
            print("Created default admin user (username: admin, password: admin)")
    
    def authenticate(self, username: str, password: str) -> dict:
        """Authenticate a user and return user data if successful."""
        with self.db._get_connection() as conn:
            cursor = conn.execute('''
                SELECT user_id, username, password_hash, password_salt, role, is_active
                FROM users WHERE username = ?
            ''', (username,))
            user = cursor.fetchone()
            
            if user and user[5]:  # is_active
                if verify_password(password, user[2], user[3]):
                    return {
                        'user_id': user[0],
                        'username': user[1],
                        'role': user[4]
                    }
        return None
    
    def create_session(self, user_id: int, ip_address: str = None, user_agent: str = None) -> str:
        """Create a new session for a user."""
        session_id = secrets.token_urlsafe(32)
        expires_at = datetime.now() + timedelta(hours=SESSION_LIFETIME_HOURS)
        
        with self.db._get_connection() as conn:
            # Clean up old sessions for this user (keep max 5)
            conn.execute('''
                DELETE FROM sessions WHERE user_id = ? AND session_id NOT IN (
                    SELECT session_id FROM sessions WHERE user_id = ?
                    ORDER BY created_at DESC LIMIT 4
                )
            ''', (user_id, user_id))
            
            conn.execute('''
                INSERT INTO sessions (session_id, user_id, expires_at, ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?)
            ''', (session_id, user_id, expires_at, ip_address, user_agent))
            
            # Update last login
            conn.execute('''
                UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE user_id = ?
            ''', (user_id,))
        
        return session_id
    
    def validate_session(self, session_id: str) -> dict:
        """Validate a session and return user data if valid."""
        if not session_id:
            return None
            
        with self.db._get_connection() as conn:
            cursor = conn.execute('''
                SELECT u.user_id, u.username, u.role, s.expires_at
                FROM sessions s
                JOIN users u ON s.user_id = u.user_id
                WHERE s.session_id = ? AND u.is_active = 1
            ''', (session_id,))
            result = cursor.fetchone()
            
            if result:
                expires_at = datetime.fromisoformat(result[3])
                if expires_at > datetime.now():
                    return {
                        'user_id': result[0],
                        'username': result[1],
                        'role': result[2]
                    }
                else:
                    # Session expired, clean up
                    conn.execute('DELETE FROM sessions WHERE session_id = ?', (session_id,))
        return None
    
    def destroy_session(self, session_id: str):
        """Destroy a session (logout)."""
        with self.db._get_connection() as conn:
            conn.execute('DELETE FROM sessions WHERE session_id = ?', (session_id,))
    
    def log_access(self, user_id: int, username: str, action: str, details: str = None,
                   ip_address: str = None, user_agent: str = None):
        """Log an access event."""
        with self.db._get_connection() as conn:
            conn.execute('''
                INSERT INTO access_logs (user_id, username, action, details, ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, username, action, details, ip_address, user_agent))
    
    def log_error(self, error_type: str, error_message: str, stack_trace: str = None,
                  endpoint: str = None, user_id: int = None, ip_address: str = None):
        """Log an error event."""
        with self.db._get_connection() as conn:
            conn.execute('''
                INSERT INTO error_logs (error_type, error_message, stack_trace, endpoint, user_id, ip_address)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (error_type, error_message, stack_trace, endpoint, user_id, ip_address))
    
    def get_access_logs(self, limit: int = 100, offset: int = 0, user_id: int = None) -> list:
        """Get access logs with optional user filter."""
        with self.db._get_connection() as conn:
            if user_id:
                cursor = conn.execute('''
                    SELECT log_id, user_id, username, action, details, ip_address, user_agent, timestamp
                    FROM access_logs WHERE user_id = ?
                    ORDER BY timestamp DESC LIMIT ? OFFSET ?
                ''', (user_id, limit, offset))
            else:
                cursor = conn.execute('''
                    SELECT log_id, user_id, username, action, details, ip_address, user_agent, timestamp
                    FROM access_logs
                    ORDER BY timestamp DESC LIMIT ? OFFSET ?
                ''', (limit, offset))
            
            return [dict(zip(['log_id', 'user_id', 'username', 'action', 'details', 
                            'ip_address', 'user_agent', 'timestamp'], row)) 
                    for row in cursor.fetchall()]
    
    def get_error_logs(self, limit: int = 100, offset: int = 0, error_type: str = None) -> list:
        """Get error logs with optional type filter."""
        with self.db._get_connection() as conn:
            if error_type:
                cursor = conn.execute('''
                    SELECT log_id, error_type, error_message, stack_trace, endpoint, user_id, ip_address, timestamp
                    FROM error_logs WHERE error_type = ?
                    ORDER BY timestamp DESC LIMIT ? OFFSET ?
                ''', (error_type, limit, offset))
            else:
                cursor = conn.execute('''
                    SELECT log_id, error_type, error_message, stack_trace, endpoint, user_id, ip_address, timestamp
                    FROM error_logs
                    ORDER BY timestamp DESC LIMIT ? OFFSET ?
                ''', (limit, offset))
            
            return [dict(zip(['log_id', 'error_type', 'error_message', 'stack_trace', 
                            'endpoint', 'user_id', 'ip_address', 'timestamp'], row)) 
                    for row in cursor.fetchall()]
    
    def get_access_log_count(self, user_id: int = None) -> int:
        """Get total count of access logs."""
        with self.db._get_connection() as conn:
            if user_id:
                cursor = conn.execute('SELECT COUNT(*) FROM access_logs WHERE user_id = ?', (user_id,))
            else:
                cursor = conn.execute('SELECT COUNT(*) FROM access_logs')
            return cursor.fetchone()[0]
    
    def get_error_log_count(self, error_type: str = None) -> int:
        """Get total count of error logs."""
        with self.db._get_connection() as conn:
            if error_type:
                cursor = conn.execute('SELECT COUNT(*) FROM error_logs WHERE error_type = ?', (error_type,))
            else:
                cursor = conn.execute('SELECT COUNT(*) FROM error_logs')
            return cursor.fetchone()[0]
    
    # User management methods
    def get_users(self) -> list:
        """Get all users."""
        with self.db._get_connection() as conn:
            cursor = conn.execute('''
                SELECT user_id, username, email, role, is_active, created_at, last_login
                FROM users ORDER BY username
            ''')
            return [dict(zip(['user_id', 'username', 'email', 'role', 'is_active', 
                            'created_at', 'last_login'], row)) 
                    for row in cursor.fetchall()]
    
    def get_user(self, user_id: int) -> dict:
        """Get a single user by ID."""
        with self.db._get_connection() as conn:
            cursor = conn.execute('''
                SELECT user_id, username, email, role, is_active, created_at, last_login
                FROM users WHERE user_id = ?
            ''', (user_id,))
            row = cursor.fetchone()
            if row:
                return dict(zip(['user_id', 'username', 'email', 'role', 'is_active', 
                                'created_at', 'last_login'], row))
        return None
    
    def create_user(self, username: str, password: str, email: str = None, 
                    role: str = 'viewer', created_by: int = None) -> int:
        """Create a new user."""
        password_hash, salt = hash_password(password)
        with self.db._get_connection() as conn:
            cursor = conn.execute('''
                INSERT INTO users (username, password_hash, password_salt, email, role, created_by)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (username, password_hash, salt, email, role, created_by))
            return cursor.lastrowid
    
    def update_user(self, user_id: int, username: str = None, email: str = None,
                    role: str = None, is_active: bool = None):
        """Update user details."""
        updates = []
        params = []
        
        if username is not None:
            updates.append('username = ?')
            params.append(username)
        if email is not None:
            updates.append('email = ?')
            params.append(email)
        if role is not None:
            updates.append('role = ?')
            params.append(role)
        if is_active is not None:
            updates.append('is_active = ?')
            params.append(is_active)
        
        if updates:
            params.append(user_id)
            with self.db._get_connection() as conn:
                conn.execute(f'''
                    UPDATE users SET {', '.join(updates)} WHERE user_id = ?
                ''', params)
    
    def change_password(self, user_id: int, new_password: str):
        """Change a user's password."""
        password_hash, salt = hash_password(new_password)
        with self.db._get_connection() as conn:
            conn.execute('''
                UPDATE users SET password_hash = ?, password_salt = ? WHERE user_id = ?
            ''', (password_hash, salt, user_id))
    
    def delete_user(self, user_id: int):
        """Delete a user."""
        with self.db._get_connection() as conn:
            # First delete their sessions
            conn.execute('DELETE FROM sessions WHERE user_id = ?', (user_id,))
            conn.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
    
    def get_active_sessions(self, user_id: int = None) -> list:
        """Get active sessions, optionally filtered by user."""
        with self.db._get_connection() as conn:
            if user_id:
                cursor = conn.execute('''
                    SELECT s.session_id, s.user_id, u.username, s.created_at, s.expires_at, s.ip_address
                    FROM sessions s
                    JOIN users u ON s.user_id = u.user_id
                    WHERE s.user_id = ? AND s.expires_at > CURRENT_TIMESTAMP
                    ORDER BY s.created_at DESC
                ''', (user_id,))
            else:
                cursor = conn.execute('''
                    SELECT s.session_id, s.user_id, u.username, s.created_at, s.expires_at, s.ip_address
                    FROM sessions s
                    JOIN users u ON s.user_id = u.user_id
                    WHERE s.expires_at > CURRENT_TIMESTAMP
                    ORDER BY s.created_at DESC
                ''')
            
            return [dict(zip(['session_id', 'user_id', 'username', 'created_at', 
                            'expires_at', 'ip_address'], row)) 
                    for row in cursor.fetchall()]
    
    # Settings methods
    def get_setting(self, key: str, default: str = None) -> str:
        """Get an application setting."""
        with self.db._get_connection() as conn:
            cursor = conn.execute('SELECT value FROM app_settings WHERE key = ?', (key,))
            row = cursor.fetchone()
            return row[0] if row else default
    
    def set_setting(self, key: str, value: str, updated_by: int = None):
        """Set an application setting."""
        with self.db._get_connection() as conn:
            conn.execute('''
                INSERT OR REPLACE INTO app_settings (key, value, updated_at, updated_by)
                VALUES (?, ?, CURRENT_TIMESTAMP, ?)
            ''', (key, value, updated_by))
    
    def get_all_settings(self) -> dict:
        """Get all application settings."""
        with self.db._get_connection() as conn:
            cursor = conn.execute('SELECT key, value FROM app_settings')
            return {row[0]: row[1] for row in cursor.fetchall()}


# Flask decorators for authentication

def login_required(f):
    """Decorator to require login for a route."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not g.get('user'):
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Decorator to require admin role for a route."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not g.get('user'):
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login', next=request.url))
        if g.user.get('role') != 'admin':
            flash('Admin access required.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


def editor_required(f):
    """Decorator to require editor or admin role for a route."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not g.get('user'):
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login', next=request.url))
        if g.user.get('role') not in ('admin', 'editor'):
            flash('Editor access required.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function
