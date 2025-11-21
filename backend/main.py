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

from fastapi import HTTPException

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

    except HTTPException as e:
        # Re-raise all HTTPExceptions (422, 400, etc.)
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    except Exception as e:
        # Unknown backend error
        raise HTTPException(status_code=400, detail=str(e))


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

@app.get("/user-by-email")
def get_user_by_email(email: str):
    try:
        users_ref = firestore.client().collection("users")
        query = users_ref.where("email", "==", email).limit(1).stream()

        for doc in query:
            user_data = doc.to_dict()
            user_data["uid"] = doc.id  # include Firestore document ID
            return user_data

        raise HTTPException(status_code=404, detail="User not found")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------- Render: Port handling ----------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
