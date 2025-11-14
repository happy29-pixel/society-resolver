# # back-end/main.py
# from fastapi import FastAPI, HTTPException, Depends, Header, Form
# from fastapi import requests
# from fastapi.middleware.cors import CORSMiddleware
# import os
# from typing import Optional
# from firestore_service import init_firebase, FirestoreService
# from models import RegisterIn, ComplaintIn

# SERVICE_ACCOUNT = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "serviceAccountKey.json")
# db = init_firebase(SERVICE_ACCOUNT)
# fs = FirestoreService(db)

# app = FastAPI(title="Society Resolver API")

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],  # during dev. Restrict to your origin for production.
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# # Optional: verify Firebase ID token from Authorization header
# def firebase_auth(authorization: Optional[str] = Header(None)):
#     if not authorization:
#         raise HTTPException(status_code=401, detail="Authorization header missing")
#     parts = authorization.split()
#     if len(parts) != 2 or parts[0].lower() != "bearer":
#         raise HTTPException(status_code=401, detail="Invalid Authorization header")
#     id_token = parts[1]
#     try:
#         decoded = fs.verify_id_token(id_token)
#         return decoded
#     except Exception as e:
#         raise HTTPException(status_code=401, detail="Invalid token")

# @app.get("/")
# def root():
#     return {"message": "API up"}

# @app.post("/register")
# def register(user: RegisterIn):
#     try:
#         user_data = user.dict()
#         new_user = fs.create_user(
#             username=user_data["username"],
#             email=user_data["email"],
#             password=user_data["password"]
#         )
#         return {"message": "User created", "uid": new_user["uid"]}
#     except Exception as e:
#         print("🔥 Register error:", e)
#         raise HTTPException(status_code=400, detail=str(e))

# # CREATE COMPLAINT (called from complaint-form.html)
# @app.post("/complaints")
# def create_complaint(complaint: ComplaintIn):
#     # if front-end has Firebase Auth, front-end should send user_id or id token
#     cid = fs.create_complaint(complaint.dict())
#     return {"id": cid, **complaint.dict(), "status": "open"}

# # Get complaints for a user
# @app.get("/complaints")
# def get_complaints(user_id: Optional[str] = None):
#     if user_id:
#         return {"complaints": fs.list_complaints_by_user(user_id)}
#     return {"complaints": fs.list_all_complaints()}

# # Get single complaint
# @app.get("/complaints/{cid}")
# def get_complaint(cid: str):
#     c = fs.get_complaint(cid)
#     if not c:
#         raise HTTPException(status_code=404, detail="Not found")
#     return c

# # Update status (requires auth)
# @app.put("/complaints/{cid}/status")
# def update_status(cid: str, status: str, user=Depends(firebase_auth)):
#     ok = fs.update_complaint_status(cid, status)
#     if not ok:
#         raise HTTPException(status_code=404, detail="Complaint not found")
#     return {"id": cid, "status": status}

from firebase_admin import firestore
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import pathlib, os
from models import RegisterIn, ComplaintIn
from firestore_service import init_firebase, FirestoreService

# init firebase admin client (expects serviceAccountKey.json in back-end or env var)
SERVICE_ACCOUNT = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "serviceAccountKey.json")
db = init_firebase(SERVICE_ACCOUNT)
fs = FirestoreService(db)

app = FastAPI(title="Society Resolver API")

# Mount static public files (so backend can serve frontend during local testing)
BASE_DIR = pathlib.Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR.parent / "public"
if PUBLIC_DIR.exists():
    app.mount("/public", StaticFiles(directory=str(PUBLIC_DIR)), name="public")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def firebase_auth(authorization: Optional[str] = Header(None)):
    # simplified: expect "Bearer <id_token>"
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid Authorization header")
    id_token = parts[1]
    return fs.verify_id_token(id_token)

@app.get("/")
def root():
    return {"message": "API up"}

# register endpoint - accepts JSON, creates auth user and user doc with type
@app.post("/register")
def register(payload: RegisterIn):
    try:
        user = fs.create_user(username=payload.username, email=payload.email, password=payload.password,
                              user_type=getattr(payload, "user_type", "user"),
                              worker_type=getattr(payload, "worker_type", None))
        return {"message": "User created", "uid": user["uid"]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# -------------------------------------------------------------------------
# 🔑 Login endpoint (Direct email + password + role check)
# -------------------------------------------------------------------------
from firebase_admin import firestore  # ensure this import exists

@app.post("/login")
def login_user(data: dict):
    """
    Login user by verifying email and password stored in Firestore.
    Returns user's role for dashboard redirection.
    """
    try:
        email = data.get("email")
        password = data.get("password")

        if not email or not password:
            raise HTTPException(status_code=400, detail="Email and password required")

        # ✅ Firestore query
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
        # Log the actual error so you can see it in console
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# complaints endpoints
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

# Workers endpoints for admin assignment
@app.get("/workers")
def list_workers(worker_type: Optional[str] = None, available: Optional[bool] = None):
    return {"workers": fs.list_workers(worker_type=worker_type, available=available)}

@app.put("/complaints/{cid}/assign")
def assign_worker(cid: str, worker_id: str, user=Depends(firebase_auth)):
    # set complaint assigned_to and set worker availability false
    ok = fs.assign_worker_to_complaint(cid, worker_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Assign failed")
    return {"id": cid, "assigned_to": worker_id}
