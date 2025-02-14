# api/chat.py
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
import httpx
import json
from typing import Dict
from database.models import ChatRename, ChatRequest, ChatBase
from database.manager import DatabaseManager
from core.security import get_current_user
from core.config import settings
from context.manager import ContextManager
from context.reasoning import Reasoning
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])
db = DatabaseManager()

@router.post("/create", response_model=Dict[str, int])
async def create_chat(
    chat: ChatBase,
    current_user: str = Depends(get_current_user)
):
    chat_id = db.create_chat(current_user, chat.title, chat.model, chat.system_prompt)
    logger.debug(f"Chat created with ID: {chat_id}")
    return {"chat_id": chat_id}

@router.get("/list")
async def get_chats(current_user: str = Depends(get_current_user)):
    return {"chats": db.get_user_chats(current_user)}

@router.get("/{chat_id}/details")
async def get_chat_details(
    chat_id: int,
    current_user: str = Depends(get_current_user)
):
    if not db.verify_chat_ownership(chat_id, current_user):
        raise HTTPException(status_code=403, detail="Not authorized to access this chat")
    details = db.get_chat_details(chat_id)
    if details:
        return details
    raise HTTPException(status_code=404, detail="Chat not found")

@router.get("/{chat_id}/messages")
async def get_chat_messages(
    chat_id: int,
    current_user: str = Depends(get_current_user)
):
    if not db.verify_chat_ownership(chat_id, current_user):
        raise HTTPException(status_code=403, detail="Not authorized to access this chat")
    return {"messages": db.get_chat_messages(chat_id)}

@router.delete("/{chat_id}")
async def delete_chat(
    chat_id: int,
    current_user: str = Depends(get_current_user)
):
    if not db.verify_chat_ownership(chat_id, current_user):
        raise HTTPException(status_code=403, detail="Not authorized to access this chat")
    db.delete_chat(chat_id)
    
    # Use the default model from config when deleting context.
    context_manager = ContextManager(chat_id=chat_id, model=settings.DEFAULT_MODEL)
    context_manager.delete_context()
    
    return {"message": "Chat and its context deleted successfully"}

@router.post("/regenerate")
async def regenerate_message(
    chat_id: int,
    message_index: int,
    current_user: str = Depends(get_current_user)
):
    if not db.verify_chat_ownership(chat_id, current_user):
        raise HTTPException(status_code=403, detail="Not authorized to access this chat")

    messages = db.get_chat_messages(chat_id)
    new_context = []
    
    for i, msg in enumerate(messages):
        if i < message_index:
            new_context.append(msg)
        elif i == message_index - 1 and msg['role'] == 'user':
            new_context.append(msg)
            
    chat_details = db.get_chat_details(chat_id)
    if not chat_details:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.OLLAMA_API_URL}/api/chat",
            json={
                "model": chat_details['model'],
                "messages": new_context,
                "stream": False
            }
        )
        
    if response.status_code == 200:
        data = response.json()
        new_response = data.get('message', {}).get('content', "")
        db.update_message(chat_id, message_index, new_response)
        logger.debug(f"Message regenerated for chat {chat_id} at index {message_index}")
        return {
            "message": "Message regenerated successfully",
            "new_response": new_response
        }
    else:
        logger.error("Regeneration failed with status code: %s", response.status_code)
        raise HTTPException(status_code=500, detail="Regeneration failed")

@router.put("/{chat_id}/rename")
async def rename_chat_endpoint(
    chat_id: int,
    rename: ChatRename,
    current_user: str = Depends(get_current_user)
):
    if not db.verify_chat_ownership(chat_id, current_user):
        raise HTTPException(status_code=403, detail="Not authorized to rename this chat")
    
    success = db.rename_chat(chat_id, rename.title)
    if success:
        logger.debug(f"Chat {chat_id} renamed to {rename.title}")
        return {"message": "Chat renamed successfully"}
    else:
        logger.error(f"Failed to rename chat {chat_id}")
        raise HTTPException(status_code=500, detail="Failed to rename chat")
    
@router.post("/message")
async def send_message(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    current_user: str = Depends(get_current_user)
):
    if not request.chat_id:
        request.chat_id = db.create_chat(current_user, "", request.model)
    
    if not db.verify_chat_ownership(request.chat_id, current_user):
        raise HTTPException(status_code=403, detail="Not authorized to access this chat")
    
    chat_details = db.get_chat_details(request.chat_id)
    if not chat_details:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    context_manager = ContextManager(chat_id=request.chat_id, model=request.model)
    existing_messages = db.get_chat_messages(request.chat_id)
    system_prompt = chat_details.get('system_prompt')
    
    optimized_messages = context_manager.optimize_messages(existing_messages, system_prompt)
    
    user_message = request.message
    user_message_tokens = context_manager._estimate_tokens([{"role": "user", "content": user_message}])
    
    context_str = "\n".join(f"{m['role']}: {m['content']}" for m in optimized_messages)
    logger.debug(f"Optimized context for chat {request.chat_id}:\n{context_str[:200]}...")
    
    # Get user preferences, defaulting to True if not specified
    _, _, _, use_reasoning = db.get_user_preferences(current_user)
    use_reasoning = use_reasoning if use_reasoning is not None else True
    
    # Save user message immediately
    db.save_message(request.chat_id, "user", user_message)
    
    if not use_reasoning:
        # Direct chat without reasoning
        async def generate_basic():
            full_response = ""
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{settings.OLLAMA_API_URL}/api/chat",
                    json={
                        "model": chat_details['model'],
                        "messages": optimized_messages + [{"role": "user", "content": user_message}],
                        "stream": True
                    }
                )
                
                async for line in response.aiter_lines():
                    if not line:
                        continue  # skip empty lines
                    # Remove any "data: " prefix if present.
                    if line.startswith("data: "):
                        line = line[6:]
                    try:
                        data = json.loads(line)
                        content = data.get("message", {}).get("content", "")
                        if content:
                            full_response += content
                            # Yield intermediate chunks so the client can display partial output.
                            yield f"data: {json.dumps({'type': 'intermediate', 'content': content})}\n\n"
                    except json.JSONDecodeError:
                        logger.error(f"Error parsing JSON from response: {line}")
                        continue
            
            # After the stream is complete, save the full response to the database.
            if full_response:
                db.save_message(request.chat_id, "assistant", full_response)
                background_tasks.add_task(db.update_chat_title, request.chat_id, request.model)
                # Send one final event indicating completion.
                yield f"data: {json.dumps({'type': 'final', 'content': full_response})}\n\n"
        
        return StreamingResponse(
            generate_basic(),
            media_type="text/event-stream",
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'Content-Type': 'text/event-stream'
            }
        )
    
    else:
        # Use reasoning pathway
        
        
        if user_message_tokens > (context_manager.max_context_length // 2):
            async def generate_chunked_response():
                full_final = ""
                max_chunk_tokens = 300
                overlap_tokens = 50
                chunks = context_manager.chunk_text(user_message, max_chunk_tokens, overlap_tokens)
                logger.debug(f"User message chunked into {len(chunks)} parts")
                
                for i, chunk in enumerate(chunks):
                    logger.debug(f"Processing chunk {i+1}/{len(chunks)}: {chunk[:100]}...")
                    chunk_context_messages = context_manager.optimize_messages(
                        existing_messages + [{"role": "user", "content": chunk}],
                        system_prompt
                    )
                    chunk_context_str = "\n".join(f"{m['role']}: {m['content']}" for m in chunk_context_messages)
                    reasoning = Reasoning(model_name=request.model, context_str=chunk_context_str)
                    async for event in reasoning.perform_chain_of_thought_reasoning(chunk):
                        logger.debug(f"Chunk {i+1}: Received event: {event}")
                        yield f"data: {json.dumps(event)}\n\n"
                        if event.get("type") == "final":
                            full_final += event.get("content", "")
                
                await reasoning.close()
                
                if full_final:
                    db.save_message(request.chat_id, "assistant", full_final.strip())
                    background_tasks.add_task(db.update_chat_title, request.chat_id, request.model)
            
            return StreamingResponse(
                generate_chunked_response(),
                media_type="text/event-stream",
                headers={
                    'Cache-Control': 'no-cache',
                    'Connection': 'keep-alive',
                    'Content-Type': 'text/event-stream'
                }
            )
        else:
            async def generate_response():
                final_answer = ""
                reasoning = Reasoning(model_name=request.model, context_str=context_str)
                async for event in reasoning.perform_chain_of_thought_reasoning(user_message):
                    logger.debug(f"Received event: {event}")
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("type") == "final":
                        final_answer += event.get("content", "")
                
                await reasoning.close()
                
                if final_answer:
                    db.save_message(request.chat_id, "assistant", final_answer.strip())
                    background_tasks.add_task(db.update_chat_title, request.chat_id, request.model)
            
            return StreamingResponse(
                generate_response(),
                media_type="text/event-stream",
                headers={
                    'Cache-Control': 'no-cache',
                    'Connection': 'keep-alive',
                    'Content-Type': 'text/event-stream'
                }
            )
