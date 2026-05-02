from langgraph.graph import StateGraph , START , END 
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from typing import TypedDict , Annotated , Optional , Union
from langchain_core.messages import BaseMessage , HumanMessage , AIMessage , SystemMessage
from langgraph.prebuilt import ToolNode , tools_condition
from langchain_core.tools import tool 
from langgraph.graph.message import add_messages
from pydantic import Field
from langgraph.types import interrupt , Command
from langgraph.checkpoint.sqlite import SqliteSaver
import sqlite3
from app.models.input import Input
import httpx #HTTP client for Python 3 that provides both synchronous and asynchronous APIs
import os 
import requests
from langchain_core.runnables import RunnableConfig
from dotenv import load_dotenv
import json
load_dotenv()

# Api keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
CHATBOT_SERVICE_KEY=os.getenv("CHATBOT_SERVICE_KEY")


# Models 
# gemini_model = ChatGoogleGenerativeAI(
#     model="gemini-2.5-flash" 
# )

groq_model = ChatGroq(
    model="meta-llama/llama-4-scout-17b-16e-instruct" ,
    groq_api_key=os.getenv("GROQ_API_KEY")
)


system_prompt = SystemMessage(content="""
You are a smart and helpful car buying assistant.

Your primary goal is to help users explore and understand cars clearly using accurate data.

CRITICAL RULES:
- ONLY use the data provided by tools.
- DO NOT add, assume, or hallucinate any information.
- If a field is missing, simply skip it (do not guess).
- The tool output is the single source of truth.

RESPONSE STYLE:
- Provide detailed information when available.
- For each car, include all available fields such as:
  - Name
  - Price
  - Fuel Type
  - Mileage
  - Transmission
  - Any description or features
- Do NOT give overly short answers if data is available.
- Format responses in a clean, structured way (bullet points or numbered list).
- Keep responses readable and well-organized.

BEHAVIOR:
- If multiple cars are available, present each clearly.
- If no cars are found, say:
  "No relevant cars found based on your criteria."
- Help the user make decisions, but do not fabricate details.

Remember:
Accuracy > Creativity. Never invent information.
""")


# State 
class ChatState(TypedDict):
    messages : Annotated[list[BaseMessage] , add_messages]
    booking_allowed : bool
    awaiting_confirmation : bool 
    
# Tools
@tool
def filter_cars_tool(budget : Optional[Union[float, str]]=None , car_type : Optional[str]=None , fuel_type : Optional[str]=None , brand : Optional[str]=None , search : Optional[str]=None , transmission : Optional[str]=None)->list[dict]:
    """
    Retrieve and filter cars from the database based on user preferences.

    This tool is used when the user is searching for cars with constraints
    such as budget, body type (e.g., SUV, sedan), fuel type, brand, or
    when the user directly searches for a specific car by name.

    The tool should be invoked whenever the user expresses intent to:
    - Find or explore cars within a certain price range
    - Search for a specific category of cars (e.g., SUV under 10L)
    - Filter cars based on features such as fuel type, mileage, or brand
    - Search for a specific car model by name (e.g., "Nexon", "i20", "Creta")
    
    Fetch cars with all prices normalized to USD.

    IMPORTANT:
    - Budget is always converted to USD before sending to backend.
    - If user provides INR (like 10 lakh), it is converted automatically.

    Parameters:
        budget (Optional[float]):
            Maximum budget specified by the user. Cars with price less than or
            equal to this value will be returned.

        car_type (Optional[str]):
            Type/category of the car (e.g., "SUV", "sedan", "hatchback").

        fuel_type (Optional[str]):
            Fuel preference (e.g., "petrol", "diesel", "electric").

        brand (Optional[str]):
            Specific car manufacturer (e.g., "Tata", "Hyundai").
            
        transmission (Optional[str]):
            (e.g., "Manual" , "Automatic").

        search (Optional[str]):
            Free-text search query for car model names.
            This is used when the user directly mentions a car name
            (e.g., "Nexon", "Hyundai i20").

    Returns:
        List[Dict]:
            A list of cars matching the filters. Each car object contains:
            - _id (str):
                Unique identifier of the car to book (MongoDB _id).
                Example: "65f2a9c8e8b3..." 
            - model (str): Car model name
            - price (float): Price of the car
            - mileage (float): Mileage information
            - fuel_type (str): Fuel type
            - additional attributes if available

    Notes:
        - If multiple filters are provided, they are applied together (AND logic).
        - If 'search' is provided, it should match car names or relevant keywords.
        - If no filters are provided, a default set of popular cars may be returned.
        - The tool does not generate recommendations or comparisons; it only retrieves data.
          Interpretation and explanation should be handled by the language model.

    Example:
        User: "Show me SUVs under 10 lakh"
        → Calls filter_cars_tool(budget=1000000, car_type="SUV")

        User: "Electric cars by Tata"
        → Calls filter_cars_tool(fuel_type="electric", brand="Tata")

        User: "Show me Nexon"
        → Calls filter_cars_tool(search="Nexon")

        User: "Hyundai i20 under 8 lakh"
        → Calls filter_cars_tool(search="Hyundai i20", budget=800000)
    """
    try:
        print("fetch car i/p " , budget , car_type , fuel_type , brand , search , transmission)
        # async with httpx.AsyncClient(timeout=5.0) as client :
        response = requests.get(f"https://autora-chatbot-backend.vercel.app/api/chatbot/fetchCars?maxPrice={budget}&bodyType={car_type}&fuelType={fuel_type}&make={brand}&search={search}&transmission={transmission}" , 
                                    headers={
                                        "service-key" : CHATBOT_SERVICE_KEY
                                    }) #None transforms to null 
        if(response.status_code != 200): #request backend pe phuchi but usne reject kiya 
            return json.dumps({
                "error": "Backend error",
                "message": response.text
            })

        
        data = response.json()
            
        
        if(not data):
            return json.dumps({
                "message" : "No cars found" ,
                "bookings" : []
            })
        
        return json.dumps(data) 
        
    except requests.exceptions.Timeout:
        return json.dumps({
            "error": "Timeout",
            "message": "Server is taking too long to respond."
        })

    except requests.exceptions.RequestException:
        return json.dumps({
            "error": "Network error",
            "message": "Cannot reach backend server."
        })

    except Exception as e:
        return json.dumps({
            "error": "Unexpected error",
            "message": str(e)
        })
    

@tool
def book_test_drive_tool(
    car_id: str,
    booking_date: str,
    start_time: str,
    end_time: str,
    notes: Optional[str] = None ,
    config : RunnableConfig = None
) -> dict:
    """
    Book a test drive for a specific car on a given date and time range.

    This tool performs the final booking action by sending a request to the backend API.
    It MUST only be invoked after explicit user confirmation (Human-in-the-Loop).

    The tool should be invoked when:
    - The user explicitly confirms booking (e.g., "yes", "confirm", "book it")
    - A valid car_id, booking_date, start_time, and end_time are already determined
    - Do NOT hallucinate date/time values . Ask the user to provide date/time if they have not provided .

    The tool should NOT be used when:
    - The user is still exploring or comparing cars
    - The user has not confirmed the booking
    - The time slot has not been finalized

    Parameters:
        car_id (str):
            Unique identifier of the car to book (MongoDB _id).
            Example: "65f2a9c8e8b3..."

        booking_date (str):
            Date of the test drive in ISO format (YYYY-MM-DD).
            Example: "2026-02-25"

        start_time (str):
            Start time of the test drive slot in 24-hour format.
            Example: "15:00"

        end_time (str):
            End time of the test drive slot in 24-hour format.
            Example: "16:00"

        notes (Optional[str]):
            Optional user notes or special instructions for the booking.

    Returns:
    Dict:
        The complete booking document created in the database, including:
        - _id (str): Unique booking identifier
        - carId (str): Car identifier
        - userId (str): User identifier
        - bookingDate (str): Date of booking
        - startTime (str): Start time
        - endTime (str): End time
        - status (str): Booking status (e.g., "PENDING")
        - notes (Optional[str]): Additional notes

    Notes:
        - This tool performs an irreversible action (booking).
        - Always ensure explicit user approval before invoking this tool.
        - The backend validates:
            - Car availability
            - Date normalization
            - Time slot conflicts (PENDING / CONFIRMED)
        - Do NOT hallucinate date/time values; 

    Example:
        User: "Yes, book it"
        → Calls book_test_drive_tool(
            car_id="65f2a9c8e8b3",
            booking_date="2026-02-25",
            start_time="15:00",
            end_time="16:00",
            notes="Prefer morning if possible"
          )
    """
    try:
        if not booking_date or not start_time or not end_time:
            return json.dumps({
                "error": "Missing booking details",
                "message": "Please provide booking date, start time and end time before booking."
            })
        # async with httpx.AsyncClient(timeout=5.0) as client :
        auth_token = config["configurable"]["auth_token"]
        data = {
            "carId" : car_id , 
            "bookingDate" : booking_date , 
            "startTime" : start_time , 
            "endTime" : end_time , 
            "notes" : notes
        }
        response = requests.post(f"https://autora-chatbot-backend.vercel.app/api/chatbot/book-test-drive" , 
                                 json=data ,
                                    headers={
                                        "service-key" : CHATBOT_SERVICE_KEY ,
                                        "Authorization" : auth_token
                                    } , timeout=5) #None transforms to null 
        if(response.status_code != 200): #request backend pe phuchi but usne reject kiya 
             return json.dumps({
                "error": "Backend error",
                "message": response.text
            }) #Let llm handle the error gracefully 
        
        data = response.json()
        
        return json.dumps(data) 
        
    except requests.exceptions.Timeout:
        return json.dumps({
            "error": "Timeout",
            "message": "Booking service is slow."
        })

    except requests.exceptions.RequestException:
        return json.dumps({
            "error": "Network error",
            "message": "Cannot reach booking service."
        })

    except Exception as e: #Generic error
        return json.dumps({
            "error": "Unexpected error",
            "message": str(e)
        })
    
    

@tool
def get_test_drive_slots_tool(car_id: str) -> list[dict]:
    """
    Retrieve existing test drive bookings for a specific car.

    This tool is used when the user wants to book a test drive or
    check availability for a car. It fetches all existing bookings
    (PENDING and CONFIRMED) for the given car, which the language model
    can use to determine available time slots.

    The tool should be invoked when:
    - The user wants to book a test drive
    - The user asks about availability of a specific car
    - The system needs booking data to suggest the next available slot

    The tool should NOT be used when:
    - The user is only browsing or comparing cars
    - No booking-related intent is present

    Parameters:
        car_id (str):
            Unique identifier of the car (MongoDB _id).

    Returns:
        List[Dict]:
            A list of existing test drive bookings for the given car.
            Each booking object contains:

            - id (str):
                Unique booking identifier

            - carId (str):
                Car identifier

            - car (Dict):
                Serialized car details (name, price, etc.)

            - bookingDate (str):
                Booking date in ISO format (YYYY-MM-DDTHH:mm:ss)

            - startTime (str):
                Start time of the booking (e.g., "15:00")

            - endTime (str):
                End time of the booking (e.g., "16:00")

            - status (str):
                Booking status ("PENDING" or "CONFIRMED")

            - notes (Optional[str]):
                Additional notes

            - createdAt (str):
                Booking creation timestamp

            - updatedAt (str):
                Last update timestamp

    Notes:
        - This tool ONLY retrieves booking data; it does NOT calculate
          available slots directly.
        - The language model must analyze the returned bookings and
          infer which time slots are free.
        - Only bookings with status "PENDING" or "CONFIRMED" should be
          considered as occupied slots.
        - Always ensure a valid car_id is provided.

    Example:
        User: "Book a test drive for Nexon"
        → Calls get_test_drive_slots_tool(car_id="65f2a9c8e8b3")

        User: "Is Nexon available tomorrow?"
        → Calls get_test_drive_slots_tool(car_id="65f2a9c8e8b3")
    """
    try:
        # async with httpx.AsyncClient(timeout=5.0) as client :
        response = requests.get(f"https://autora-chatbot-backend.vercel.app/api/chatbot/test-drive-slots?id={car_id}" , 
                                    headers={
                                        "service-key" : CHATBOT_SERVICE_KEY
                                    } , timeout=5) #None transforms to null 
        if(response.status_code != 200): #request backend pe phuchi but usne reject kiya 
            return json.dumps({
                "message": "No bookings found",
                "data": []
            })
        
        data = response.json()
        
        if(not data):
            return json.dumps({
                "message" : "No test drive bookings found" ,
                "bookings" : []
            })
        
        return json.dumps(data)  #LLM ko json format me hi O/P dekhna acha lagta 
        
    except requests.exceptions.Timeout:
        return json.dumps({
            "error": "Timeout",
            "message": "Server slow."
        })

    except requests.exceptions.RequestException:
        return json.dumps({
            "error": "Network error",
            "message": "Cannot reach server."
        })

    except Exception as e:
        return json.dumps({
            "error": "Unexpected error",
            "message": str(e)
        })
    

tools = [filter_cars_tool , book_test_drive_tool , get_test_drive_slots_tool]

# Nodes

def pre_confirm_node(state : ChatState)->ChatState:
    return {"awaiting_confirmation" : True}

def confirm_node(state : ChatState)->ChatState:
    decision = interrupt({
        "type": "confirmation",
        "message": "Do you want to confirm this test drive booking? reply in yes or no ."
    })
    
    if decision["approved"]:
        return {"booking_allowed": True , "awaiting_confirmation" : False}
    else:
        return {"booking_allowed": False , "awaiting_confirmation" : False}
    
def chat_node(state : ChatState)->ChatState:
    llm_with_tools = groq_model.bind_tools(tools
)
    
    response = llm_with_tools.invoke(state["messages"])
    
    return {"messages" : [response]}

tool_node = ToolNode(tools)
    

#conditional edge functions    
def custom_condition(state : ChatState):
    """
    Decide next node after chat_node.

    Priority:
    1) If LLM is trying to call booking tool -> go to confirm_node
    2) If LLM is calling any other tool -> go to tool_node
    3) Otherwise -> END
    """
    
    last = state["messages"][-1]
    
    if(last.tool_calls):
        for call in last.tool_calls :
            if(call["name"] == "get_test_drive_slots_tool" or call["name"] == 'filter_cars_tool'):
                return "tool_node"
            
            if(call["name"] == "book_test_drive_tool"):
                return "pre_confirm_node"
            
    return END

def confirm_condition(state : ChatState):
    if(state["booking_allowed"] == True):
        return "tool_node"
    else:
        return END


connection_object = sqlite3.connect(database='chatbot.db' , check_same_thread=False)

graph = StateGraph(ChatState)

graph.add_node("chat_node" , chat_node)
graph.add_node("confirm_node" , confirm_node)
graph.add_node("tool_node" , tool_node)
graph.add_node("pre_confirm_node" , pre_confirm_node)

graph.add_edge(START , "chat_node")
graph.add_conditional_edges("chat_node" , custom_condition)
graph.add_edge("tool_node" , "chat_node")
graph.add_edge("pre_confirm_node" , "confirm_node")
graph.add_conditional_edges("confirm_node" , confirm_condition)

checkpointer = SqliteSaver(conn=connection_object)
workflow = graph.compile(checkpointer=checkpointer)

def autoMate(user_input : Input):
    existing_state = workflow.get_state(config=user_input.config) #Although our state is a dictionary , but it returns a sanpshot object of our state which is of the form (existing_values, metadata)
    
    state_values = existing_state.values if existing_state else {}
    if((state_values.get("awaiting_confirmation", False) == True) and (user_input.user_message.lower() == "yes" or user_input.user_message.lower() == "no")):
        approved = True if user_input.user_message.lower() == "yes" else False
        
        if(approved == False):
            return "Okay, booking cancelled."

        final_result = workflow.invoke(
            Command(resume={"approved": approved}),
            config=user_input.config
        )
        # final_result = workflow.invoke(Command(resume={"approved" : user_input.user_message}) , config=user_input.config)
        
        
        return final_result["messages"][-1].content 
        
    else:
        message = HumanMessage(content=user_input.user_message)
        
        existing_state = workflow.get_state(config=user_input.config)
        
        initial_state = dict()
        
        if not existing_state.values :  #returns a view object called dict_values that contains all the values stored in a dictionary. 
            initial_state = {
                "messages" : [system_prompt , message] ,
                "booking_allowed" : False ,
                "awaiting_confirmation" : False
            }
        else:
            initial_state = {
                "messages" : [message]
            }
         
        
        response = workflow.invoke(initial_state , config=user_input.config)
        if "__interrupt__" in response:
            hitl_message = response['__interrupt__'][0].value["message"]
            return hitl_message
        else:
            return response['messages'][-1].content   
    
def fetchState(body : dict)->ChatState:
    
    state = workflow.get_state(config=body['config'])
    
    messages = state.values.get("messages" , [])
    
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
