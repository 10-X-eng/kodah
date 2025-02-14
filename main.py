# main.py
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from typing import Optional
import asyncio
from core.config import settings
from api import auth, chat, models, files, preferences

app = FastAPI(title=settings.APP_NAME, version=settings.VERSION)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(auth.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(preferences.router, prefix="/api")
app.include_router(models.router, prefix="/api")

@app.get("/{chat_id:int}", response_class=HTMLResponse)
@app.get("/", response_class=HTMLResponse)
async def read_root(chat_id: Optional[int] = None):
    """Serve the main HTML page for any URL path."""
    with open("static/index.html") as f:
        return f.read()

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return {
        "detail": exc.detail,
        "status_code": exc.status_code
    }

async def start_model_polling():
    asyncio.create_task(models.poll_models())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)