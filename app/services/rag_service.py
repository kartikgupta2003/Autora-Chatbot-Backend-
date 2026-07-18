from langgraph.graph import START , END , StateGraph
from app.services.vector_store import vectorstore
from langchain_core.tools import tool 
from langchain_core.runnables import RunnableConfig
from typing import TypedDict , Annotated
from langchain_core.messages import BaseMessage , HumanMessage , AIMessage , SystemMessage
from langgraph.graph.message import add_messages
from langchain_groq import ChatGroq
from langgraph.prebuilt import ToolNode , tools_condition
from app.models.input import Input
from langgraph.checkpoint.postgres import PostgresSaver
import os
from psycopg_pool import ConnectionPool

class ChatState(TypedDict):
    messages : Annotated[list[BaseMessage] , add_messages]

system_prompt = SystemMessage(content="""
You are AutoDoc AI, an intelligent automotive document assistant integrated into the Autora platform.

Your primary responsibility is to help users understand uploaded vehicle-related documents such as:
- Car manuals
- Insurance documents
- Warranty papers
- Service guides
- Technical PDFs

You must answer questions ONLY using:
1. The retrieved document context provided to you
2. The ongoing conversation context

-----------------------------------
BEHAVIOR RULES
-----------------------------------

1. BE GROUNDED
- Do NOT hallucinate.
- Do NOT invent specifications, features, numbers, or policies.
- If the answer is not present in the provided context, clearly say:
  "I could not find this information in the uploaded document."

2. BE CLEAR AND SIMPLE
- Explain technical automotive concepts in beginner-friendly language.
- Keep answers concise but useful.
- Use bullet points when appropriate.

3. STAY DOCUMENT-SCOPED
- Prioritize uploaded document knowledge over general knowledge.
- Do NOT answer using assumptions.
- If the user asks something unrelated to the uploaded document, politely mention that the information is not available in the current document.

4. HANDLE AMBIGUITY
- If the question is unclear, ask a short clarification question.
- Example:
  "Which vehicle or document are you referring to?"

5. CITATIONS
- If page metadata is available, mention the page number naturally.
- Example:
  "According to page 12 of the uploaded manual..."

6. RESPONSE STYLE
- Be professional, helpful, and calm.
- Avoid overly robotic responses.
- Avoid unnecessary long explanations.

7. SAFETY
- Never provide dangerous automotive advice with certainty if the document does not explicitly mention it.
- Never fabricate maintenance or safety instructions.

-----------------------------------
CONTEXT USAGE
-----------------------------------

You may receive:
- Retrieved chunks from a vector database
- Previous conversation messages
- Metadata such as:
  - filename
  - page number
  - document id

Use them carefully to generate accurate contextual answers.

-----------------------------------
FAILURE HANDLING
-----------------------------------

If retrieval context is empty or insufficient:
- Say that the required information could not be found in the uploaded document.
- Suggest uploading another relevant document if appropriate.

-----------------------------------
OUTPUT STYLE EXAMPLES
-----------------------------------

Good:
"According to page 18 of the uploaded manual, the recommended engine oil grade is 0W-20."

Good:
"I could not find mileage information in the uploaded document."

Bad:
"Most SUVs usually use 0W-20 oil."
(Do not assume information.)

-----------------------------------
IDENTITY
-----------------------------------

You are AutoDoc AI.
You are part of the Autora platform.
You specialize in vehicle document understanding and contextual Q/A.
""") 

GROQ_API_KEY = os.getenv("GROQ_API_KEY")  
groq_model = ChatGroq(
    model="meta-llama/llama-4-scout-17b-16e-instruct" ,
    groq_api_key=os.getenv("GROQ_API_KEY")
)
DB_URL = os.getenv("DB_URL")

#tools
@tool
def rag_tool(query : str = None , config : RunnableConfig = None)->str:
    """
    Retrieve relevant document chunks from the vector database using
    semantic similarity search scoped to the currently active document.

    This tool is used by AutoDoc AI whenever the user's query requires
    information from the uploaded PDF/manual associated with the current
    chat session.

    The retrieval pipeline performs:
    1. Query embedding generation
    2. Similarity search in the vector database
    3. Metadata-based filtering using:
       - user_id
       - filename
       - file_hash

    Metadata filtering ensures retrieval is restricted only to the
    active document uploaded by the current authenticated user,
    preventing cross-document retrieval ambiguity.

    Args:
        query (str):
            The user's natural language query.

        config (RunnableConfig):
            LangGraph/LangChain runtime configuration containing:
            - auth_token (used as user_id)
            - filename
            - file_hash

    Returns:
            Retrieved relevant document chunks that will later be used
            by the LLM to generate grounded contextual responses.

    Example:
        User Query:
            "What is the recommended engine oil?"

        Retrieval Flow:
            Query → Embedding → ChromaDB Similarity Search
            → Metadata Filter → Relevant Chunks Returned
    """
    user_id =config["configurable"]["auth_token"]
    filename = config["configurable"]["filename"]
    file_hash = config["configurable"]["file_hash"]
    
    # print("info khecho " , user_id , filename , file_hash)
    
    retriever = vectorstore.as_retriever(search_kwargs={"k" : 3 ,
                                                        "filter" : {
                                                            "user_id" : user_id ,
                                                            "filename" : filename ,
                                                            "file_hash" : file_hash
                                                            }}) #3 doc objects
    
    docs = retriever.invoke(input=query) 
    # print("chunks jo match hue " , docs)
    if not docs:
        return "No relevant information was found."

    results = []

    for doc in docs:
        page = doc.metadata.get(
            "page_label",
            doc.metadata.get("page", "unknown")
        )

        results.append(
            f"Page: {page}\n"
            f"Content: {doc.page_content}"
        )

    return "\n\n---\n\n".join(results) 
  
tools = [rag_tool]

llm_with_tools = groq_model.bind_tools(tools)

  
#nodes
def chat_node(state : ChatState)->ChatState:
     response = llm_with_tools.invoke(state["messages"])
     
     return {"messages" : [response]} 
   
tool_node = ToolNode(tools)


# graph 
graph = StateGraph(ChatState)
graph.add_node("chat_node" , chat_node)
graph.add_node("tools" , tool_node)

graph.add_edge(START , "chat_node")
graph.add_conditional_edges("chat_node" , tools_condition)
graph.add_edge("tools" , "chat_node")


# with PostgresSaver.from_conn_string(DB_URL) as checkpointer:
#     checkpointer.setup()
#     chatbot = graph.compile(checkpointer=checkpointer)

# with block khatam hote hi PostgresSaver PostgreSQL connection close kar deta hai. chatbot variable to available rehta hai, lekin uske andar stored checkpointer closed connection ko refer kar raha hota hai.

# Connection remains open
# checkpointer_context = PostgresSaver.from_conn_string(
#     DB_URL
# )

# checkpointer = checkpointer_context.__enter__()

# checkpointer.setup()

# chatbot = graph.compile(
#     checkpointer=checkpointer
# )

pool = ConnectionPool(
    conninfo=DB_URL,
    min_size=0,
    max_size=5,
    kwargs={
        "autocommit": True,
        "prepare_threshold": 0
    },
    check=ConnectionPool.check_connection
)

checkpointer = PostgresSaver(pool)

checkpointer.setup()

chatbot = graph.compile(
    checkpointer=checkpointer
)

def fetch_state(body : dict)->ChatState:
  state = chatbot.get_state(config=body['config'])
#   print("state jo fetch hui " , state)
  messages = state.values.get("messages", [])
#   state.get returns a LangGraph state snapshot object. That object contains metadata plus the actual graph state.
# state.values -> dictionary return karta hai 
# {
#     "messages": [
#         HumanMessage(content="Hello"),
#         AIMessage(content="Hi, how can I help?")
#     ]
# }

# Uske baad:

# state.values.get("messages", [])

# dictionary se "messages" key ki value nikal lega:
    
  formatted = []
    
  for msg in messages:
      if(msg.content == ""):
          continue
      role=""
      if(msg.__class__.__name__ == "HumanMessage"):
          role="user"
          formatted.append({
              "role" : role ,
              "content" : msg.content
          })
      elif(msg.__class__.__name__ == "AIMessage"):
          role="assistant"
          formatted.append({
              "role" : role ,
              "content" : msg.content
          })
            
        
  return formatted

def question_answer(data : Input):
  query = data["user_message"]
  config = data["config"]
  user_message = HumanMessage(content=query)
  
  existing_state = chatbot.get_state(config=config)
  state = {}
  
  if(not existing_state.values):
    state={
      "messages" : [system_prompt , user_message]
    }
  else:
    state={
      "messages" : [user_message]
    }
    
  response = chatbot.invoke(state , config=config)
  
  return response["messages"][-1].content
  
  
  
  