import hashlib
import os
from typing import Any
from langchain_community.document_loaders import PyPDFLoader
import httpx
from fastapi import HTTPException, UploadFile
from langchain_google_genai import ChatGoogleGenerativeAI , GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pinecone import Pinecone
from langchain_pinecone import PineconeVectorStore
from app.services.vector_store import vectorstore , embedding

MAX_FILE_SIZE = 10 * 1024 * 1024
UPLOAD_DIR = "uploads"
CHATBOT_SERVICE_KEY = os.getenv("CHATBOT_SERVICE_KEY")


os.makedirs(UPLOAD_DIR, exist_ok=True)


async def uploader(file: UploadFile, auth_token: str | None = None , user_id : str | None = None):
    print("file jo ayi " , file)
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    content = await file.read() #read data in bits
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded PDF is empty")

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="PDF size must be under 10 MB")

    file_hash = hashlib.sha256(content).hexdigest()
    print("file hash " , file_hash)
    payload = {
        "doc_name": file.filename,
        "doc_hash": file_hash,
        "doc_size": round(len(content) / (1024 * 1024), 4),
    }
    
    print(payload)
    headers = {}
    if auth_token:
        headers["Authorization"] = auth_token

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://autora-backend.vercel.app/api/docs/upload",
                json=payload,
                headers=headers,
            )
            print("response " , response)
            response.raise_for_status()
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504 ,
            detail="Backend timeout"
        )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Cannot connect to backend"
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=e.response.text
        )
    except httpx.RequestError:
        raise HTTPException(
            status_code=500,
            detail="Network request failed"
        )
    except Exception as e : #generic exception handler 
        print("erro " ,e)
        raise HTTPException(
        status_code=500,
        detail=str(e)
        )

    backend_data = response.json() #converts json into python object 
    print("data " , backend_data)
    if backend_data["already_uploaded"]:
        print(file_hash)
        return {
            "already_uploaded": True,
            "doc_hash": file_hash,
            "message": "PDF already uploaded.",
        }

    file_path = os.path.join(UPLOAD_DIR, f"{file_hash}.pdf")
    try:
        with open(file_path, "wb") as temp_pdf:
            temp_pdf.write(content)
        
        loader = PyPDFLoader(
            file_path=file_path
        )

        docs = loader.load() #list of document objects of each pdf page 
        
        for doc in docs :
            doc.metadata["file_hash"]=file_hash 
            doc.metadata["filename"]=file.filename
            doc.metadata["user_id"]=user_id
        
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=100,
        )
        
        chunks = splitter.split_documents(docs)
        
        vectorstore.add_documents(chunks) 
        # better rhega batches me chunks store karaye 
        
        # for i in range(0 , len(chunks) , 50):
        #     batch = chunks[i : i+50] 
        #     vectorstore.add_documents(batch)
    
    except Exception as e : #generic exception handler 
        # rollback meta data
        print(e)
        payload = {            
            "doc_hash": file_hash
        } 
        headers = {}
        if auth_token:
            headers["Authorization"] = auth_token
        try :
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.patch(
                    "https://autora-backend.vercel.app/api/docs/remove",
                    json=payload,
                    headers=headers,
                )
                print(response)
                response.raise_for_status()
        except:
            pass
        print("ai error " , e)
        raise HTTPException(
        status_code=500,
        detail=str(e)
        )
        
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
        
    return {
            "already_uploaded": False,
            "doc_hash": file_hash,
            "message": "PDF successfully uploaded.",
        }
