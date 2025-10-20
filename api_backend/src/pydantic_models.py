from pydantic import BaseModel
from typing import List

class Message(BaseModel):
    role: str  # "user" | "assistant" | "system"
    content: str # text of the message

class ChatRequest(BaseModel):
    messages: List[Message]