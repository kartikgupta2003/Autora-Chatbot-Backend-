from fastapi import Request, Response
from app.main import app as fastapi_app

app = fastapi_app

@app.middleware("http")
async def cors_middleware(request: Request, call_next):
    # Handle preflight request
    if request.method == "OPTIONS":
        response = Response()
    else:
        response = await call_next(request)

    response.headers["Access-Control-Allow-Origin"] = "https://autora-frontend.vercel.app"
    response.headers["Access-Control-Allow-Methods"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"

    return response