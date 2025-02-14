# core/config.py
import os
from typing import Dict, Optional
from pathlib import Path

class Settings:
    # Application settings
    APP_NAME: str = "Chat Application"
    VERSION: str = "1.0.0"
    UPLOAD_DIR: Path = Path("uploads")
    DATABASE_PATH: str = "users.db"
    
    # Security settings
    SECRET_KEY: str = os.urandom(32).hex()
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # API settings
    OLLAMA_API_URL: str = "http://localhost:11434"
    
    # Model settings
    DEFAULT_CONTEXT_LENGTH: int = 4096
    MODEL_CONTEXT_LENGTHS: Dict[str, int] = {
        "llama2": 4096,
        "mistral": 8192,
        "codellama": 16384,
        "neural-chat": 8192,
        "starling-lm": 8192
    }
    DEFAULT_MODEL: str = "granite3-dense:2b"
    INDEX_PATH = "context_index.bin"
    MEMORY_TEXTS_PATH = "context_texts.json"

    def __init__(self):
        os.makedirs(self.UPLOAD_DIR, exist_ok=True)
    
    def get_model_context_length(self, model_name: str) -> int:
        base_model = model_name.split(":")[0].lower()
        return self.MODEL_CONTEXT_LENGTHS.get(base_model, self.DEFAULT_CONTEXT_LENGTH)

settings = Settings()