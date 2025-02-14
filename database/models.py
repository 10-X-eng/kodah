# database/models.py
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime

class UserBase(BaseModel):
    username: str

class UserCreate(UserBase):
    password: str

class User(UserBase):
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True

class TokenData(BaseModel):
    username: Optional[str] = None

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class ChatBase(BaseModel):
    title: str
    model: str
    system_prompt: Optional[str] = None

class Chat(ChatBase):
    id: int
    username: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True

class MessageBase(BaseModel):
    role: str
    content: str

class MessageCreate(MessageBase):
    chat_id: int

class Message(MessageBase):
    id: int
    chat_id: int
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True

class UserPreferences(BaseModel):
    default_model: Optional[str] = None
    theme: Optional[str] = "light"
    default_system_prompt: Optional[str] = None
    use_reasoning: bool = True

    class Config:
        from_attributes = True

class ChatRequest(BaseModel):
    message: str
    model: str
    chat_id: Optional[int] = None

class ChatResponse(BaseModel):
    response: str
    chat_id: int

class ChatRename(BaseModel):
    title: str