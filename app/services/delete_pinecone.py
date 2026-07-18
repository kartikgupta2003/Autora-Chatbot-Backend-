from pinecone import Pinecone
import os
from dotenv import load_dotenv
load_dotenv()

pc = Pinecone(
    api_key=os.getenv("PINECONE_API_KEY")
)

pinecone_index = pc.Index(
    os.getenv("PINECONE_INDEX_NAME", "autora")
)

pinecone_index.delete(
    delete_all=True,
    namespace=""
)