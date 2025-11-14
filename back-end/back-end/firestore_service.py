import firebase_admin
from firebase_admin import credentials, firestore, auth
from typing import Optional, Dict, Any, List
from datetime import datetime

def init_firebase(service_account_path: Optional[str] = None):
    if not firebase_admin._apps:
        if service_account_path and firestore:
            cred = credentials.Certificate(service_account_path)
            firebase_admin.initialize_app(cred)
        else:
            firebase_admin.initialize_app()
    return firestore.client()

class FirestoreService:
    def __init__(self, db):
        self.db = db

    def create_user(self, username, email, password, role="user", worker_type=None):
        """
        Creates a Firebase Auth user and corresponding Firestore user document.
        Args:
            username: display name
            email: user email
            password: login password
            role: "user", "worker", or "admin"
            worker_type: optional for workers (e.g., "plumber", "electrician")
        """

        # --- Validate role and worker_type ---
        role = (role or "user").lower()
        if role == "worker" and not worker_type:
            raise ValueError("worker_type is required when role is 'worker'")

        # --- Create Firebase Authentication user ---
        auth_user = auth.create_user(email=email, password=password, display_name=username)

        # --- Prepare Firestore document ---
        user_doc = {
            "uid": auth_user.uid,
            "username": username,
            "email": email,
            "role": role,
            "worker_type": worker_type if role == "worker" else None,
            "available": True if role == "worker" else None,
            "created_at": datetime.utcnow().isoformat()
        }

        # --- Save to Firestore ---
        self.db.collection("users").document(auth_user.uid).set(user_doc)

        # --- Return full saved document ---
        return user_doc


    def list_workers(self, worker_type: Optional[str] = None, available: Optional[bool] = None) -> List[Dict[str, Any]]:
        col = self.db.collection("users")
        q = col.where("user_type", "==", "worker")
        if worker_type:
            q = q.where("worker_type", "==", worker_type)
        if available is not None:
            q = q.where("available", "==", available)
        docs = q.stream()
        return [{**d.to_dict(), "id": d.id} for d in docs]

    # COMPLAINTS
    def create_complaint(self, complaint_data: Dict[str, Any]) -> str:
        doc_ref = self.db.collection("complaints").document()
        doc_data = {
            **complaint_data,
            "status": "open",
            "assigned_to": None,
            "created_at": datetime.utcnow().isoformat()
        }
        doc_ref.set(doc_data)
        return doc_ref.id

    def get_complaint(self, cid: str) -> Optional[Dict[str, Any]]:
        doc = self.db.collection("complaints").document(cid).get()
        if doc.exists:
            return {**doc.to_dict(), "id": doc.id}
        return None

    def list_complaints_by_user(self, user_id: str) -> List[Dict[str, Any]]:
        q = self.db.collection("complaints").where("user_id", "==", user_id).stream()
        return [{**d.to_dict(), "id": d.id} for d in q]

    def list_complaints_by_worker(self, worker_id: str) -> List[Dict[str, Any]]:
        q = self.db.collection("complaints").where("assigned_to", "==", worker_id).stream()
        return [{**d.to_dict(), "id": d.id} for d in q]

    def list_all_complaints(self) -> List[Dict[str, Any]]:
        docs = self.db.collection("complaints").stream()
        return [{**d.to_dict(), "id": d.id} for d in docs]

    def update_complaint_status(self, cid: str, status: str) -> bool:
        ref = self.db.collection("complaints").document(cid)
        if ref.get().exists:
            ref.update({"status": status})
            # if resolved, free assigned worker
            if status == "resolved":
                current = ref.get().to_dict()
                wid = current.get("assigned_to")
                if wid:
                    self.db.collection("users").document(wid).update({"available": True})
            return True
        return False

    def assign_worker_to_complaint(self, cid: str, worker_id: str) -> bool:
        comp_ref = self.db.collection("complaints").document(cid)
        if not comp_ref.get().exists:
            return False
        # set complaint assigned_to and status
        comp_ref.update({"assigned_to": worker_id, "status": "in_progress"})
        # mark worker unavailable
        self.db.collection("users").document(worker_id).update({"available": False})
        return True

    def verify_id_token(self, id_token: str) -> dict:
        return auth.verify_id_token(id_token)
