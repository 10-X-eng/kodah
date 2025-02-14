# api/models.py
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
import httpx
import asyncio
from typing import Dict, List
from core.security import get_current_user
from core.config import settings

router = APIRouter(prefix="/models", tags=["models"])

# Global state for available models
available_models: Dict[str, dict] = {}

async def fetch_models() -> List[Dict]:
    """Fetch models from Ollama immediately."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{settings.OLLAMA_API_URL}/api/tags")
            if response.status_code == 200:
                models_data = response.json()
                available_models.clear()
                for model in models_data.get('models', []):
                    available_models[model['name']] = {
                        'name': model['name'],
                        'modified_at': model.get('modified_at', ''),
                        'size': model.get('size', 0)
                    }
                return list(available_models.values())
    except Exception as e:
        print(f"Error fetching models: {e}")
        return []

async def poll_models():
    """Poll Ollama for available models periodically."""
    while True:
        await fetch_models()
        await asyncio.sleep(30)

@router.get("")
async def get_models(current_user: str = Depends(get_current_user)):
    """Get list of available chat models."""
    # If no models are available, fetch them immediately
    if not available_models:
        models = await fetch_models()
    else:
        models = [m for m in available_models.values()]
    
    # Filter out embedding models
    models = [m for m in models if "-embedding" not in m["name"]]
    
    if not models:
        raise HTTPException(status_code=503, detail="No models available")
        
    return {"models": models}