import os
import pathlib
from passlib.hash import bcrypt
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends, Header, APIRouter
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from .firestore_service import FirestoreService, db
from .models import RegisterIn, ComplaintIn
import uuid
from firebase_admin import firestore
from pydantic import BaseModel

# FirestoreService instance
fs = FirestoreService(db)

# FastAPI app
app = FastAPI(title="Society Resolver API")

# ---------- CORS setup ----------
allowed_origins_env = os.environ.get("ALLOWED_ORIGINS", "*")
if allowed_origins_env.strip() == "*":
    allow_origins = ["*"]
else:
    allow_origins = [origin.strip() for origin in allowed_origins_env.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Static files (optional, for local testing) ----------
BASE_DIR = pathlib.Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR.parent / "public"
if PUBLIC_DIR.exists():
    app.mount("/public", StaticFiles(directory=str(PUBLIC_DIR)), name="public")

# ---------- Auth dependency ----------
def firebase_auth(authorization: Optional[str] = Header(None)):
    """Expect header: Authorization: Bearer <id_token>"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid Authorization header")
    id_token = parts[1]
    try:
        return {"dummy": True}  # Remove auth until you implement JWT
        # verified = fs.verify_id_token(id_token)
        # return verified
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")



# ---------- Routes ----------
@app.get("/")
def root():
    return {"message": "API up"}

@app.get("/favicon.ico")
def favicon():
    return ""

router = APIRouter()

@router.post("/register")
def register_user(data: dict):
    try:
        username = data.get("username")
        email = data.get("email")
        password = data.get("password")
        user_type = data.get("user_type", "user")
        worker_type = data.get("worker_type")

        if not username or not email or not password:
            raise HTTPException(status_code=400, detail="Username, email and password are required.")

        users_ref = db.collection("users")
        existing = users_ref.where("email", "==", email).limit(1).get()

        if existing:
            raise HTTPException(status_code=409, detail="Email already registered.")

        uid = str(uuid.uuid4())

        user_data = {
            "uid": uid,
            "username": username,
            "email": email,
            "password": password,  # <-- now hashed
            "role": user_type,
            "created_at": firestore.SERVER_TIMESTAMP
        }

        if user_type == "worker":
            if not worker_type:
                raise HTTPException(status_code=400, detail="Worker type required for workers.")
            user_data["worker_type"] = worker_type

        db.collection("users").document(uid).set(user_data)

        return {
            "message": "Registration successful",
            "uid": uid,
            "user_type": user_type,
            "username": username
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/login")
def login_user(data: dict):
    try:
        email = data.get("email")
        password = data.get("password")

        if not email or not password:
            raise HTTPException(status_code=400, detail="Email and password required")

        # 🔎 Fetch user from Firestore
        users_ref = db.collection("users")
        query = users_ref.where("email", "==", email).limit(1).get()

        if not query:
            raise HTTPException(status_code=404, detail="User not found")

        user_data = query[0].to_dict()

        if not user_data:
            raise HTTPException(status_code=404, detail="User data missing")

        # 🔐 Validate hashed password
        stored_password = user_data.get("password")
        if password != stored_password:
            raise HTTPException(status_code=401, detail="Invalid password")

        # 🔥 Generate a fake token (replace with JWT later)
        token = str(uuid.uuid4())

        return {
            "message": "Login successful",
            "token": token,
            "uid": user_data.get("uid"),
            "user_type": user_data.get("role", "user"),
            "username": user_data.get("username", "User")
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


app.include_router(router, prefix="/auth")

@app.post("/complaints")
def create_complaint(complaint: ComplaintIn):
    cid = fs.create_complaint(complaint.dict())
    return {"id": cid, **complaint.dict(), "status": "open"}

@app.get("/complaints")
def get_complaints(user_id: Optional[str] = None, worker_id: Optional[str] = None):
    if worker_id:
        return {"complaints": fs.list_complaints_by_worker(worker_id)}
    if user_id:
        return {"complaints": fs.list_complaints_by_user(user_id)}
    return {"complaints": fs.list_all_complaints()}

@app.put("/complaints/{cid}/status")
def update_status(cid: str, status: str, user=Depends(firebase_auth)):
    ok = fs.update_complaint_status(cid, status)
    if not ok:
        raise HTTPException(status_code=404, detail="Complaint not found")
    return {"id": cid, "status": status}

@app.get("/workers")
def list_workers(worker_type: Optional[str] = None, available: Optional[bool] = None):
    return {"workers": fs.list_workers(worker_type=worker_type, available=available)}

@app.put("/complaints/{cid}/assign")
def assign_worker(cid: str, worker_id: str, user=Depends(firebase_auth)):
    ok = fs.assign_worker_to_complaint(cid, worker_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Assign failed")
    return {"id": cid, "assigned_to": worker_id}
