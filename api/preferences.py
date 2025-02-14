# api/preferences.py
from fastapi import APIRouter, Depends
from database.models import UserPreferences
from database.manager import DatabaseManager
from core.security import get_current_user

router = APIRouter(prefix="/preferences", tags=["preferences"])
db = DatabaseManager()

@router.post("")
async def set_preferences(
    preferences: UserPreferences,  # Ensure your pydantic model includes use_reasoning: bool
    current_user: str = Depends(get_current_user)
):
    db.set_user_preferences(
        current_user,
        preferences.default_model,
        preferences.theme,
        preferences.default_system_prompt,
        preferences.use_reasoning  # New flag
    )
    return {"message": "Preferences updated successfully"}

@router.get("")
async def get_preferences(current_user: str = Depends(get_current_user)):
    default_model, theme, default_system_prompt, use_reasoning = db.get_user_preferences(current_user)
    return {
        "default_model": default_model,
        "theme": theme,
        "default_system_prompt": default_system_prompt,
        "use_reasoning": use_reasoning  # Return the flag
    }
