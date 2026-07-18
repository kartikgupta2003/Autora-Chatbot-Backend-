from pinecone import Pinecone
from langchain_pinecone import PineconeVectorStore
import os 
from langchain_google_genai import GoogleGenerativeAIEmbeddings

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

embedding = GoogleGenerativeAIEmbeddings(
    model="gemini-embedding-001",
    api_key=GEMINI_API_KEY
)
pc = Pinecone(
    api_key=os.getenv("PINECONE_API_KEY")
)
index=pc.Index("autora")
vectorstore = PineconeVectorStore(
    index_name="autora",
    embedding=embedding ,
    pinecone_api_key=os.getenv("PINECONE_API_KEY")
)