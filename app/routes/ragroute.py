from fastapi import UploadFile , File , Header 
from fastapi import APIRouter , Request
from app.services.file_upload_service import uploader
from app.services.rag_service import fetch_state , question_answer

router = APIRouter()

@router.post("/upload-pdf")
async def upload_pdf(authorization : str = Header(...) , user_id : str = Header(...) , file : UploadFile =  File(...)):
    # UploadFile -> Ye FastAPI ka special type hai jo: uploaded file ko represent karta hai
    # File(...) -> Ye FastAPI ko batata hai: Ye parameter request ke multipart/form-data se ayega.hash 
    data = await uploader(file=file , auth_token=authorization , user_id=user_id)
    return data 

@router.post("/qa/fetch")
def fetch_chats(body : dict):
    # print("ftech karna hai " , flush=True)
    data = fetch_state(body)

    # response = JSONResponse(content=data)

    # response.headers["Access-Control-Allow-Origin"] = "https://autora-frontend.vercel.app"
    # response.headers["Access-Control-Allow-Methods"] = "*"
    # response.headers["Access-Control-Allow-Headers"] = "*"

    return data

@router.post("/ai/answer")
async def fetch_answer(request : Request):
    body = await request.json()
    
    data = question_answer(body)
    
    return data 
    