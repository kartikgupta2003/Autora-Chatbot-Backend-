from fastapi import FastAPI 
from app.routes import general_chatting
# Bcz hum uvicorn Backend se run kar rhe so app.routes but agar app se hi run kar rhe hote to just routes hota 
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

origins = [
    "http://localhost:5173",   # Vite frontend 
    "https://ask-tube.vercel.app" #vercel frontend ,
    "http://localhost:8080"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(general_chatting.router)
