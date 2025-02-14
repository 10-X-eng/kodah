# database/manager.py
import sqlite3
import hashlib
import os
from typing import Optional, List, Dict, Any, Tuple
import logging
import httpx
from core.config import settings
from context.manager import ContextManager

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self):
        self.db_path = settings.DATABASE_PATH
        self.embedding_client = httpx.AsyncClient()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL
                )
            ''')
            
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
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_preferences (
                    username TEXT PRIMARY KEY,
                    default_model TEXT,
                    theme TEXT DEFAULT 'light',
                    default_system_prompt TEXT,
                    use_reasoning INTEGER DEFAULT 0,
                    FOREIGN KEY (username) REFERENCES users(username)
                )
            ''')
            
            conn.commit()

    def create_chat(self, username: str, title: Optional[str], model: str, system_prompt: Optional[str] = None) -> int:
        """Create a new chat for the given user."""
        if not title:
            title = "New Chat..."
            
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

    async def update_chat_title(self, chat_id: int, model: str) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT title FROM chats WHERE id = ?", (chat_id,))
            row = cursor.fetchone()
            if not row or row[0] != "New Chat...":
                return

            cursor.execute(
                "SELECT content FROM messages WHERE chat_id = ? ORDER BY created_at ASC LIMIT 1",
                (chat_id,)
            )
            first_message = cursor.fetchone()
            if not first_message:
                return

        # Initialize the context manager for this model
        context_manager = ContextManager(chat_id=chat_id, model=model)
        first_message_text = first_message[0].strip()

        # Estimate tokens for the first message
        estimated_tokens = context_manager._estimate_tokens(
            [{"role": "user", "content": first_message_text}]
        )
        # Define a threshold (here, we use half the model's max context length)
        threshold = context_manager.max_context_length // 2

        # If the message is too long, summarize it before generating the title
        if estimated_tokens > threshold:
            summarized_text = context_manager.summarize_context(
                [{"role": "user", "content": first_message_text}]
            )
            content_for_prompt = summarized_text
        else:
            content_for_prompt = first_message_text

        prompt = (
            f"Generate a short, concise title for the following chat message:\n\n"
            f"{content_for_prompt}\n\nTitle:"
        )

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{settings.OLLAMA_API_URL}/api/generate",
                    json={
                        "model": model,
                        "prompt": prompt,
                        "stream": False
                    }
                )
                if response.status_code == 200:
                    data = response.json()
                    generated_title = data.get("response", "").strip()
                    generated_title = generated_title.split("\n")[0].strip()

                    # Remove surrounding quotes if present
                    if (generated_title.startswith('"') and generated_title.endswith('"')) or \
                    (generated_title.startswith("'") and generated_title.endswith("'")):
                        generated_title = generated_title[1:-1].strip()

                    if not generated_title:
                        generated_title = first_message_text
                    max_length = 60
                    if len(generated_title) > max_length:
                        generated_title = generated_title[:max_length].rstrip() + "..."

                    with self._get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            "UPDATE chats SET title = ? WHERE id = ?",
                            (generated_title, chat_id)
                        )
                        conn.commit()
        except Exception as e:
            logger.error(f"Error updating chat title: {e}")

    def update_chat_model(self, chat_id: int, model: str) -> None:
        """Update the model associated with a chat."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE chats SET model = ? WHERE id = ?",
                (model, chat_id)
            )
            conn.commit()

    def rename_chat(self, chat_id: int, new_title: str) -> bool:
        """Rename an existing chat."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE chats SET title = ? WHERE id = ?",
                    (new_title, chat_id)
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error renaming chat: {e}")
            return False

    def _hash_password(self, password: str, salt: Optional[str] = None) -> Tuple[str, str]:
        if salt is None:
            salt = os.urandom(16).hex()
        password_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        ).hex()
        return password_hash, salt

    def create_user(self, username: str, password: str) -> bool:
        password_hash, salt = self._hash_password(password)
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)",
                    (username, password_hash, salt)
                )
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            logger.warning(f"Attempted to create duplicate user: {username}")
            return False

    def verify_user(self, username: str, password: str) -> bool:
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

    def get_user_chats(self, username: str) -> List[Dict[str, Any]]:
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
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

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
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_chat_details(self, chat_id: int) -> Optional[Dict[str, Any]]:
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

    def verify_chat_ownership(self, chat_id: int, username: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM chats WHERE id = ? AND username = ?",
                (chat_id, username)
            )
            return cursor.fetchone() is not None

    def save_message(self, chat_id: int, role: str, content: str) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO messages (chat_id, role, content) 
                VALUES (?, ?, ?)""",
                (chat_id, role, content)
            )
            conn.commit()

    def update_message(self, chat_id: int, message_index: int, new_content: str) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE messages 
                SET content = ? 
                WHERE chat_id = ? 
                AND id = (
                    SELECT id FROM messages 
                    WHERE chat_id = ? 
                    ORDER BY created_at 
                    LIMIT 1 OFFSET ?
                )""",
                (new_content, chat_id, chat_id, message_index)
            )
            conn.commit()

    def set_user_preferences(self, username: str, default_model: Optional[str] = None,
                            theme: Optional[str] = None, default_system_prompt: Optional[str] = None,
                            use_reasoning: Optional[bool] = True) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO user_preferences (username, default_model, theme, default_system_prompt, use_reasoning)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    default_model = COALESCE(?, default_model),
                    theme = COALESCE(?, theme),
                    default_system_prompt = COALESCE(?, default_system_prompt),
                    use_reasoning = COALESCE(?, use_reasoning)
                """,
                (username, default_model, theme, default_system_prompt, int(use_reasoning),
                default_model, theme, default_system_prompt, int(use_reasoning))
            )
            conn.commit()

    def get_user_preferences(self, username: str) -> Tuple[Optional[str], str, Optional[str], bool]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT default_model, theme, default_system_prompt, use_reasoning 
                FROM user_preferences 
                WHERE username = ?""",
                (username,)
            )
            result = cursor.fetchone()
            if result:
                # Convert the use_reasoning value (stored as integer) to boolean
                return (result[0], result[1], result[2], bool(result[3]))
            return (None, 'light', None, True)

    def delete_chat(self, chat_id: int) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
            cursor.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
            conn.commit()

    def user_exists(self, username: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM users WHERE username = ?", (username,))
            return cursor.fetchone() is not None