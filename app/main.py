from fastapi import FastAPI , Request
from app.routes import general_chatting , ragroute
# Bcz hum uvicorn Backend se run kar rhe so app.routes but agar app se hi run kar rhe hote to just routes hota 
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import redis.asyncio as redis 
from contextlib import asynccontextmanager
from ChatBot_Backend.app.services.persistence_service import initialize_checkpointing, close_checkpointing
import logging
import os 

REDIS_URL = os.getenv("REDIS_URL")
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = redis.from_url(REDIS_URL)
    initialize_checkpointing()
    try:
        yield
    finally:
        await app.state.redis.aclose()
        close_checkpointing()

app = FastAPI(lifespan=lifespan)


origins = [
    "http://localhost:5173",   # Vite frontend
    "https://autora-frontend.vercel.app" , #autora deployed frontend 
    "https://autora-backend.vercel.app" , #autora deployed backend
    "http://localhost:8080" #local backend
]


RATE_LIMIT_SCRIPT = """
local count = redis.call('GET', KEYS[1])

if not count then
    redis.call('SET', KEYS[1], 1, 'EX', ARGV[1])
    return 1
end

if tonumber(count) > 0 then
    redis.call('DECR', KEYS[1])
    return 1
end

return 0
"""



@app.middleware("http")
async def rate_limiter_middleware(request: Request, call_next):
    try:
        path = request.url.path
        if request.method != "POST" or path not in {"/ai", "/ai/answer"}:
            return await call_next(request)
        
        body = await request.json() 
        
        client = request.app.state.redis
        if(path == "/ai"):
            # request intended for autora agent
            user_id = body.get("user_id")
                        
            key = f"autora_agent:{user_id}"
                        
            count = await client.get(key)
                        
            # if(count is not None and int(count) > 0):
            #     await client.decr(key)
            # elif(count is not None):
            #     return JSONResponse(content={"error": "Rate limit exceeded for autora agent. Try again after a minute."}, status_code=429)
            # else:
            #     await client.setex(key , 60 , "1")
            
            allowed = await client.eval(
                RATE_LIMIT_SCRIPT,
                1,
                key,
                60
            )
            
            if(allowed == 0):
                return JSONResponse(content={"error": "Rate limit exceeded for autora agent. Try again after a minute."}, status_code=429)

        elif(path == "/ai/answer"):
            # request intended for rag agent
            user_id = body["config"]["configurable"]["auth_token"]
                        
            key= f"rag_agent:{user_id}"
                        
            count = await client.get(key)
                        
            # if(count is not None and int(count) > 0):
            #     await client.decr(key)
            # elif(count is not None):
            #     return JSONResponse(content={"error": "Rate limit exceeded for rag agent. Try again after a minute."}, status_code=429)
            # else:
            #     await client.setex(key , 60 , "1")
            
            allowed = await client.eval(
                RATE_LIMIT_SCRIPT, 
                1,
                key,
                60
            )
            
            if(allowed == 0):
                return JSONResponse(content={"error": "Rate limit exceeded for rag agent. Try again after a minute."}, status_code=429)
        response = await call_next(request)
        return response
                
            
    except Exception:
        logger.exception("Rate limiter middleware failed")
        raise

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(general_chatting.router)
app.include_router(ragroute.router)