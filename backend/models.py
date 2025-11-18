from pydantic import BaseModel, EmailStr, Field
from typing import Optional

class RegisterIn(BaseModel):
    username: str = Field(..., example="Ayush")
    email: EmailStr = Field(..., example="ayush@example.com")
    password: str = Field(..., min_length=6)
    user_type: Optional[str] = Field("user", example="user")  # user or worker or admin
    worker_type: Optional[str] = Field(None, example="plumber")  # plumber, electrician, other

class ComplaintIn(BaseModel):
    user_id: Optional[str] = None
    name: str
    category: str
    description: str
    date: str
