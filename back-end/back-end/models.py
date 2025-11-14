from pydantic import BaseModel, EmailStr, Field
from typing import Optional

class RegisterIn(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: Optional[str] = "user"
    worker_type: Optional[str] = None


class ComplaintIn(BaseModel):
    user_id: Optional[str] = None
    name: str
    category: str
    description: str
    date: str
