from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import pathlib, os

from models import RegisterIn, ComplaintIn
from firestore_service import init_firebase, FirestoreService
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Access them
api_key = os.getenv("FIREBASE_API_KEY")
print("Firebase API Key:", api_key)

# ✅ Initialize Firebase Admin
SERVICE_ACCOUNT = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "serviceAccountKey.json")
db = init_firebase(SERVICE_ACCOUNT)
fs = FirestoreService(db)

app = FastAPI(title="Society Resolver API")

# ✅ Serve static frontend files (for local testing)
BASE_DIR = pathlib.Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR.parent / "public"
if PUBLIC_DIR.exists():
    app.mount("/public", StaticFiles(directory=str(PUBLIC_DIR)), name="public")

# ✅ Allow CORS for frontend → backend calls
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------------------------
# 🔒 Firebase Auth dependency
# -------------------------------------------------------------------------
def firebase_auth(authorization: Optional[str] = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid Authorization header")

    id_token = parts[1]
    try:
        return fs.verify_id_token(id_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

# -------------------------------------------------------------------------
# 🌐 Root endpoint
# -------------------------------------------------------------------------
@app.get("/")
def root():
    return {"message": "API running successfully ✅"}

# -------------------------------------------------------------------------
# 👤 Register endpoint
# -------------------------------------------------------------------------
@app.post("/register")
def register(payload: RegisterIn):
    """
    Register a new user and store them in Firestore.
    Expected JSON:
    {
        "username": "...",
        "email": "...",
        "password": "...",
        "role": "user" | "worker" | "admin",
        "worker_type": "plumber" | "electrician" | "cleaner" | null
    }
    """
    try:
        user = fs.create_user(
            username=payload.username,
            email=payload.email,
            password=payload.password,
            role=getattr(payload, "role", "user"),
            worker_type=getattr(payload, "worker_type", None)
        )
        return {"message": "User created successfully", "uid": user["uid"]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# -------------------------------------------------------------------------
# 📬 Complaints endpoints
# -------------------------------------------------------------------------
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

# -------------------------------------------------------------------------
# 👷 Workers management endpoints (Admin)
# -------------------------------------------------------------------------
@app.get("/workers")
def list_workers(worker_type: Optional[str] = None, available: Optional[bool] = None):
    return {"workers": fs.list_workers(worker_type=worker_type, available=available)}

@app.put("/complaints/{cid}/assign")
def assign_worker(cid: str, worker_id: str, user=Depends(firebase_auth)):
    ok = fs.assign_worker_to_complaint(cid, worker_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Assign failed")
    return {"id": cid, "assigned_to": worker_id}

# -------------------------------------------------------------------------
# 🔑 Login endpoint (Direct email + password + role check)
# -------------------------------------------------------------------------
@app.post("/login")
def login_user(data: dict):
    """
    Login user by verifying email and password stored in Firestore.
    Returns user's role for dashboard redirection.
    """
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")

    try:
        users_ref = db.collection("users")
        user_docs = users_ref.where("email", "==", email).limit(1).get()

        if not user_docs:
            raise HTTPException(status_code=404, detail="User not found")

        user_data = user_docs[0].to_dict()

        if user_data.get("password") != password:
            raise HTTPException(status_code=401, detail="Invalid password")

        role = user_data.get("role", "user")
        return {"message": "Login successful", "role": role}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
