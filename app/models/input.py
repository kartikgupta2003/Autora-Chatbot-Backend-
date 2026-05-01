from pydantic import BaseModel

class Input(BaseModel):
    user_message : str 
    config : dict