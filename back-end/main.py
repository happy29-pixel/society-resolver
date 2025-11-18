import os
import json
import pathlib
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from firebase_admin import credentials, initialize_app, firestore
# Import your app-specific models and FirestoreService implementation
from models import RegisterIn, ComplaintIn
from firestore_service import FirestoreService

# ---------- Firebase initialization ----------
# Expecting the full JSON in this exact env var on Render:
# GOOGLE_APPLICATION_CREDENTIALS_JSON
cred_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
if not cred_json:
    # Fail fast - Render logs will show this
    raise RuntimeError(
        "Missing Firebase credentials. Set GOOGLE_APPLICATION_CREDENTIALS_JSON environment variable."
    )

try:
    cred_dict = json.loads(cred_json)
except Exception as e:
    raise RuntimeError(f"Failed to parse GOOGLE_APPLICATION_CREDENTIALS_JSON: {e}")

# Initialize Firebase Admin SDK
cred = credentials.Certificate(cred_dict)
initialize_app(cred)
db = firestore.client()

# Create FirestoreService wrapper (your implementation)
fs = FirestoreService(db)

# ---------- FastAPI app ----------
app = FastAPI(title="Society Resolver API")

# ---------- Static files (optional, for local testing) ----------
BASE_DIR = pathlib.Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR.parent / "public"
if PUBLIC_DIR.exists():
    app.mount("/public", StaticFiles(directory=str(PUBLIC_DIR)), name="public")

# ---------- CORS ----------
# For production, set ALLOWED_ORIGINS env var to your frontend origin (comma-separated).
# Example: REACT_APP_URL=https://your-firebase-site.web.app
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
        # fs.verify_id_token should call firebase_admin.auth.verify_id_token internally
        verified = fs.verify_id_token(id_token)
        return verified
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

# ---------- Routes ----------
@app.get("/")
def root():
    return {"message": "API up"}

@app.post("/register")
def register(payload: RegisterIn):
    try:
        user = fs.create_user(
            username=payload.username,
            email=payload.email,
            password=payload.password,
            user_type=getattr(payload, "user_type", "user"),
            worker_type=getattr(payload, "worker_type", None),
        )
        return {"message": "User created", "uid": user["uid"]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/login")
def login_user(data: dict):
    """
    If your frontend uses FirebaseAuth, it should perform signInWithEmailAndPassword
    and send idToken to backend. This endpoint is only needed if you do manual login.
    Here we keep an email/password check against Firestore (if you store password there).
    """
    try:
        email = data.get("email")
        password = data.get("password")

        if not email or not password:
            raise HTTPException(status_code=400, detail="Email and password required")

        users_ref = db.collection("users")
        query = users_ref.where("email", "==", email).limit(1).get()

        if not query or len(query) == 0:
            raise HTTPException(status_code=404, detail="User not found")

        user_data = query[0].to_dict()
        if not user_data:
            raise HTTPException(status_code=404, detail="User data missing")

        if user_data.get("password") != password:
            raise HTTPException(status_code=401, detail="Invalid password")

        role = user_data.get("role", "user")
        return {"message": "Login successful", "role": role}

    except HTTPException:
        raise
    except Exception as e:
        # Log stack trace will appear in Render logs
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

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
