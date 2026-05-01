from fastapi import APIRouter , Request
from app.services.autora_service import autoMate , fetchState
from app.models.input import Input

router = APIRouter()

@router.post("/ai")
async def get_answer(request : Request):
    body = await request.json()
    
    user_message = body.get("user_message")
    thread_id = body.get("thread_id")
    auth_token = request.headers.get("Authorization")
    
    config = {
        "configurable": {
            "auth_token": auth_token,   
            "thread_id": thread_id       
        }
    }
    
    query = Input(user_message=user_message , config=config)
    
    return autoMate(query)

@router.post("/ai/fetch")
def fetch_chats(body : dict):
    return fetchState(body)