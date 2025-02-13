# database.py
import sqlite3
import hashlib
import os
from typing import Optional, Tuple, List, Dict, Any
import httpx

class DatabaseManager:
    """A simple SQLite-based database manager for users, chats, messages, and preferences."""
    
    def __init__(self, db_path: str = 'users.db'):
        self.db_path = db_path
        self._init_db()
        self.embedding_client = httpx.AsyncClient()
    
    def _init_db(self) -> None:
        """Initialize the SQLite database with the required tables."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL
                )
            ''')
            # Chats table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    model TEXT NOT NULL,
                    system_prompt TEXT,
                    FOREIGN KEY (username) REFERENCES users(username)
                )
            ''')
            # Messages table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (chat_id) REFERENCES chats(id)
                )
            ''')
            # User preferences table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_preferences (
                    username TEXT PRIMARY KEY,
                    default_model TEXT,
                    theme TEXT DEFAULT 'light',
                    default_system_prompt TEXT,
                    FOREIGN KEY (username) REFERENCES users(username)
                )
            ''')
            conn.commit()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Return a new SQLite connection."""
        return sqlite3.connect(self.db_path)
    
    def create_chat(self, username: str, title: Optional[str], model: str, system_prompt: Optional[str] = None) -> int:
        """
        Create a new chat for the given user.
        
        If a title is not provided or is empty, a default title "pending..." is used.
        """
        if not title:
            title = "pending..."
            
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO chats (username, title, model, system_prompt)
                VALUES (?, ?, ?, ?)""",
                (username, title, model, system_prompt)
            )
            chat_id = cursor.lastrowid
            conn.commit()
            return chat_id

    
    async def update_chat_title(self, chat_id: int, model) -> None:
        """
        Update the chat title by generating a short summary title using the completion API.
        
        This function will only update the title if it is still "pending...". It retrieves the
        first message, then sends a prompt to generate a short title. The generated title is then
        truncated and stored.
        """
        # Only update if the current title is "pending..."
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT title FROM chats WHERE id = ?", (chat_id,))
            row = cursor.fetchone()
            if not row or row[0] != "pending...":
                return  # Title already updated

        # Retrieve the first message content for the chat.
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT content FROM messages WHERE chat_id = ? ORDER BY created_at ASC LIMIT 1",
                (chat_id,)
            )
            first_message = cursor.fetchone()
        if not first_message:
            return

        # Build a prompt to generate a short, clear title.
        prompt = (
            f"Generate a short, concise title for the following chat message:\n\n"
            f"{first_message[0]}\n\nTitle:"
        )

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:11434/api/generate",
                    json={
                        "model": model,
                        "prompt": prompt,
                        "stream": False
                    }
                )
            if response.status_code == 200:
                data = response.json()
                # Expect the non-streaming response to have a "response" field with the generated text.
                generated_title = data.get("response", "").strip()
                # Use only the first line (in case the model returns extra text).
                generated_title = generated_title.split("\n")[0].strip()
                # Fallback to the first message if nothing was generated.
                if not generated_title:
                    generated_title = first_message[0].strip()
                # Truncate the title to a maximum length (e.g., 60 characters).
                max_length = 60
                if len(generated_title) > max_length:
                    generated_title = generated_title[:max_length].rstrip() + "..."
                # Update the chat title in the database.
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE chats SET title = ? WHERE id = ?", (generated_title, chat_id))
                    conn.commit()
        except Exception as e:
            print(f"Error updating chat title: {e}")
    
    def get_user_chats(self, username: str) -> List[Dict[str, Any]]:
        """
        Retrieve all chats for a given user.
        
        Returns a list of dictionaries with keys: id, title, created_at, and model.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, title, created_at, model 
                   FROM chats 
                   WHERE username = ? 
                   ORDER BY created_at DESC""",
                (username,)
            )
            columns = ['id', 'title', 'created_at', 'model']
            chats = [dict(zip(columns, row)) for row in cursor.fetchall()]
            return chats
    
    def get_chat_messages(self, chat_id: int) -> List[Dict[str, str]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT role, content, created_at 
                FROM messages 
                WHERE chat_id = ? 
                ORDER BY created_at""",
                (chat_id,)
            )
            columns = ['role', 'content', 'created_at']
            messages = [dict(zip(columns, row)) for row in cursor.fetchall()]
            return messages
    
    def get_chat_details(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """
        Get details of a specific chat, including title, model, system_prompt, and username.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT title, model, system_prompt, username 
                   FROM chats 
                   WHERE id = ?""",
                (chat_id,)
            )
            result = cursor.fetchone()
            if result:
                return {
                    "title": result[0],
                    "model": result[1],
                    "system_prompt": result[2],
                    "username": result[3]
                }
            return None
    def update_message(self, chat_id: int, message_index: int, new_content: str) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # This is a simplified example.
            # You might want to use a unique message ID instead of an index.
            cursor.execute(
                "UPDATE messages SET content = ? WHERE chat_id = ? ORDER BY created_at LIMIT 1 OFFSET ?",
                (new_content, chat_id, message_index)
            )
            conn.commit()
    
    def verify_chat_ownership(self, chat_id: int, username: str) -> bool:
        """
        Verify that the given chat belongs to the specified user.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM chats WHERE id = ? AND username = ?",
                (chat_id, username)
            )
            return cursor.fetchone() is not None
    
    def save_message(self, chat_id: int, role: str, content: str) -> None:
        """
        Save a message to the specified chat.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO messages (chat_id, role, content) 
                   VALUES (?, ?, ?)""",
                (chat_id, role, content)
            )
            conn.commit()
    
    def set_user_preferences(self, username: str, default_model: Optional[str] = None,
                             theme: Optional[str] = None, default_system_prompt: Optional[str] = None) -> None:
        """
        Set or update user preferences.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO user_preferences (username, default_model, theme, default_system_prompt)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(username) DO UPDATE SET
                       default_model = COALESCE(?, default_model),
                       theme = COALESCE(?, theme),
                       default_system_prompt = COALESCE(?, default_system_prompt)""",
                (username, default_model, theme, default_system_prompt,
                 default_model, theme, default_system_prompt)
            )
            conn.commit()
    
    def get_user_preferences(self, username: str) -> Tuple[Optional[str], str, Optional[str]]:
        """
        Retrieve the user preferences.
        
        Returns a tuple: (default_model, theme, default_system_prompt).
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT default_model, theme, default_system_prompt FROM user_preferences WHERE username = ?",
                (username,)
            )
            result = cursor.fetchone()
            if result:
                return result
            return (None, 'light', None)
    
    def create_user(self, username: str, password: str) -> bool:
        """
        Create a new user with a hashed password.
        
        Returns True on success or False if the username already exists.
        """
        password_hash, salt = self._hash_password(password)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)",
                    (username, password_hash, salt)
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False
    
    def verify_user(self, username: str, password: str) -> bool:
        """
        Verify user credentials.
        
        Returns True if the provided password matches the stored hash.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT password_hash, salt FROM users WHERE username = ?",
                (username,)
            )
            result = cursor.fetchone()
            if not result:
                return False
            stored_hash, salt = result
            password_hash = self._hash_password(password, salt)[0]
            return password_hash == stored_hash
    
    def _hash_password(self, password: str, salt: Optional[str] = None) -> Tuple[str, str]:
        """
        Hash the password using PBKDF2 with SHA256.
        
        Returns a tuple of (hashed_password, salt).
        """
        if salt is None:
            salt = os.urandom(16).hex()
        password_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        ).hex()
        return password_hash, salt
    
    def user_exists(self, username: str) -> bool:
        """
        Check if a user exists.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM users WHERE username = ?", (username,))
            return cursor.fetchone() is not None

    def delete_chat(self, chat_id: int) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Delete messages first
            cursor.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
            # Then delete the chat record itself
            cursor.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
            conn.commit()
