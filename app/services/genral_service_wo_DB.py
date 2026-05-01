from langgraph.graph import StateGraph , START , END
from langchain_google_genai import ChatGoogleGenerativeAI
from typing import TypedDict , Annotated
from langchain_core.messages import BaseMessage , HumanMessage , AIMessage
from langgraph.graph import add_messages 
from langgraph.checkpoint.memory import InMemorySaver
from dotenv import load_dotenv
load_dotenv()
from app.models.input import Input

model = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash"
)

class ChatState(TypedDict):
    messages : Annotated[list[BaseMessage] , add_messages]
    
def chat_node(state : ChatState)->ChatState:
    response = model.invoke(state["messages"])
    return {'messages' : [response]}

checkpointer = InMemorySaver()
    
graph = StateGraph(ChatState)
graph.add_node('chat_node' , chat_node)

graph.add_edge(START , 'chat_node')
graph.add_edge('chat_node' , END)

workflow = graph.compile(checkpointer=checkpointer)

def chatbot(user_query : Input)->str:
    
    print(user_query)
    query = HumanMessage(content=user_query.user_message)
    
    response = workflow.invoke({'messages' : [query]} , config=user_query.config)
    
    return response['messages'][-1].content

def fetchState(body : dict)->ChatState:
    
    print(body)
    state = workflow.get_state(config=body['config'])
    
    messages = state.values.get("messages" , [])
    
    formatted = []
    
    for msg in messages:
        role=""
        if(msg.__class__.__name__ == "HumanMessage"):
            role="user"
        else:
            role="assitant"
            
        formatted.append({
            "role" : role ,
            "content" : msg.content
        })
        
    return formatted

