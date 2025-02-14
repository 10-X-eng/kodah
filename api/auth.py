# api/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from database.models import UserCreate, Token
from database.manager import DatabaseManager
from core.security import create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["authentication"])
db = DatabaseManager()

@router.post("/register", response_model=dict)
async def register_user(user: UserCreate):
    if not db.create_user(user.username, user.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )
    return {"message": "User created successfully"}

@router.post("/token", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    if not db.verify_user(form_data.username, form_data.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": form_data.username})
    return Token(access_token=access_token, token_type="bearer")