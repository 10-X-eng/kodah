# main.py
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, UploadFile, File
from fastapi.responses import FileResponse, Response, StreamingResponse, HTMLResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from datetime import datetime, timedelta
import jwt
import httpx
import os
import shutil
import asyncio
import json
from typing import List, Dict, Optional
from database import DatabaseManager
from context import ContextManager

# Initialize FastAPI and database
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
db = DatabaseManager()

# Security configuration
SECRET_KEY = os.urandom(32).hex()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Models
class User(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class ChatRequest(BaseModel):
    message: str
    model: str
    chat_id: Optional[int] = None

class ChatCreate(BaseModel):
    title: str
    model: str
    system_prompt: Optional[str] = None

class Message(BaseModel):
    content: str
    role: str

class UserPreferences(BaseModel):
    default_model: Optional[str] = None
    theme: Optional[str] = None
    default_system_prompt: Optional[str] = None



# Global state for available models
available_models: Dict[str, dict] = {}

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

async def poll_models():
    """Poll Ollama for available models periodically."""
    while True:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get("http://localhost:11434/api/tags")
                if response.status_code == 200:
                    models_data = response.json()
                    # Update the global models dict with model details
                    available_models.clear()
                    for model in models_data.get('models', []):
                        available_models[model['name']] = {
                            'name': model['name'],
                            'modified_at': model.get('modified_at', ''),
                            'size': model.get('size', 0)
                        }
        except Exception as e:
            print(f"Error polling models: {e}")
        
        await asyncio.sleep(30)  # Poll every 30 seconds

# Authentication functions
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401)
        return username
    except jwt.PyJWTError:
        raise HTTPException(status_code=401)

# Routes
@app.get("/{chat_id:int}", response_class=HTMLResponse)
@app.get("/", response_class=HTMLResponse)
async def read_root(chat_id: Optional[int] = None):
    """Serve the main HTML page for any URL path."""
    with open("static/index.html") as f:
        return f.read()

@app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    if not db.verify_user(form_data.username, form_data.password):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    
    access_token = create_access_token(data={"sub": form_data.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/chats")
async def create_chat(chat: ChatCreate, current_user: str = Depends(get_current_user)):
    chat_id = db.create_chat(current_user, chat.title, chat.model, chat.system_prompt)
    return {"chat_id": chat_id}

@app.get("/chats")
async def get_chats(current_user: str = Depends(get_current_user)):
    return {"chats": db.get_user_chats(current_user)}

@app.get("/chats/{chat_id}/messages")
async def get_chat_messages(chat_id: int, current_user: str = Depends(get_current_user)):
    messages = db.get_chat_messages(chat_id)
    return {"messages": messages}

@app.post("/chat/{chat_id}/upload")
async def upload_file(chat_id: int, file: UploadFile = File(...), 
                     current_user: str = Depends(get_current_user)):
    file_path = os.path.join(UPLOAD_DIR, f"{chat_id}_{file.filename}")
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"filename": file.filename, "path": file_path}

@app.get("/chat/{chat_id}/files/{filename}")
async def get_file(chat_id: int, filename: str, current_user: str = Depends(get_current_user)):
    file_path = os.path.join(UPLOAD_DIR, f"{chat_id}_{filename}")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)

@app.get("/chats/{chat_id}/export")
async def export_chat(chat_id: int, current_user: str = Depends(get_current_user)):
    # Verify chat ownership first.
    if not db.verify_chat_ownership(chat_id, current_user):
        raise HTTPException(status_code=403, detail="Not authorized to access this chat")
    messages = db.get_chat_messages(chat_id)
    transcript = ""
    for msg in messages:
        # If you later add timestamps to your messages, include them here.
        transcript += f"{msg['role'].upper()}: {msg['content']}\n"
    headers = {"Content-Disposition": f"attachment; filename=chat_{chat_id}.txt"}
    return Response(content=transcript, media_type="text/plain", headers=headers)

@app.delete("/chats/{chat_id}")
async def delete_chat(chat_id: int, current_user: str = Depends(get_current_user)):
    if not db.verify_chat_ownership(chat_id, current_user):
        raise HTTPException(status_code=403, detail="Not authorized to access this chat")
    db.delete_chat(chat_id)
    return {"message": "Chat deleted successfully"}

@app.post("/chat/regenerate")
async def regenerate_message(chat_id: int, message_index: int, current_user: str = Depends(get_current_user)):
    # Retrieve the full chat context
    messages = db.get_chat_messages(chat_id)
    # Assume message_index points to the assistant message to be regenerated.
    # Remove that message from the context.
    new_context = []
    for i, msg in enumerate(messages):
        # Keep all messages before the message to be regenerated
        if i < message_index:
            new_context.append(msg)
        # Also add the user message right before it if exists
        elif i == message_index - 1 and msg['role'] == 'user':
            new_context.append(msg)
    # Call the generation API with the updated context.
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:11434/api/chat",
            json={
                "model": messages[0].get('model', "default-model"),
                "messages": new_context,
                "stream": False
            }
        )
    if response.status_code == 200:
        data = response.json()
        new_response = data.get('message', {}).get('content', "")
        # Update the message in the database (or return it to the frontend to update the UI)
        db.update_message(chat_id, message_index, new_response)
        return {"message": "Message regenerated successfully", "new_response": new_response}
    else:
        raise HTTPException(status_code=500, detail="Regeneration failed")

@app.post("/preferences")
async def set_preferences(preferences: UserPreferences, 
                         current_user: str = Depends(get_current_user)):
    db.set_user_preferences(
        current_user,
        preferences.default_model,
        preferences.theme,
        preferences.default_system_prompt
    )
    return {"message": "Preferences updated successfully"}

@app.get("/preferences")
async def get_preferences(current_user: str = Depends(get_current_user)):
    prefs = db.get_user_preferences(current_user)
    return {
        "default_model": prefs[0],
        "theme": prefs[1],
        "default_system_prompt": prefs[2]
    }

@app.post("/chat")
async def chat(request: ChatRequest, current_user: str = Depends(get_current_user)):
    if request.model not in available_models:
        raise HTTPException(status_code=400, detail="Selected model is not available")
    
    if not request.chat_id:
        request.chat_id = db.create_chat(current_user, "", request.model)
    
    chat_details = db.get_chat_details(request.chat_id)
    if not chat_details:
        raise HTTPException(status_code=404, detail="Chat not found")
    if not db.verify_chat_ownership(request.chat_id, current_user):
        raise HTTPException(status_code=403, detail="Not authorized to access this chat")
    
    # Initialize context manager with the specific model
    context_manager = ContextManager(request.model)
    
    # Get existing messages and system prompt from database
    existing_messages = db.get_chat_messages(request.chat_id)
    system_prompt = chat_details.get('system_prompt')
    
    # Convert database messages to chat format
    message_history = [
        {
            "role": msg["role"],
            "content": msg["content"]
        } for msg in existing_messages
    ]
    
    # Add new user message to history
    message_history.append({
        "role": "user",
        "content": request.message
    })
    
    # Get optimized context window for this conversation
    optimized_messages = context_manager.optimize_messages(
        messages=message_history,
        system_prompt=system_prompt
    )
    
    async def generate():
        full_response = ""
        async with httpx.AsyncClient() as client:
            async with client.stream(
                'POST',
                "http://localhost:11434/api/chat",
                json={
                    "model": request.model,
                    "messages": optimized_messages,
                    "stream": True
                }
            ) as response:
                async for line in response.aiter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            if 'message' in data and 'content' in data['message']:
                                content = data['message']['content']
                                full_response += content
                                yield f"data: {json.dumps({'response': content})}\n\n"
                        except json.JSONDecodeError:
                            continue
        
        # Save both the user message and assistant response in the database
        db.save_message(request.chat_id, "user", request.message)
        db.save_message(request.chat_id, "assistant", full_response)
        
        # Update chat title in background
        asyncio.create_task(db.update_chat_title(request.chat_id, request.model))
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Content-Type': 'text/event-stream'
        }
    )

@app.get("/models")
async def get_models(current_user: str = Depends(get_current_user)):
    """Get list of available chat models (exclude embedding models)."""
    models = [m for m in available_models.values() if "-embedding" not in m["name"]]
    return {"models": models}


@app.post("/users")
async def create_user(user: User):
    if not db.create_user(user.username, user.password):
        raise HTTPException(status_code=400, detail="Username already exists")
    return {"message": "User created successfully"}

# Startup and shutdown events
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(poll_models())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)