
import math
import os
import io
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from typing import Optional

import numpy as np
import cv2
import pandas as pd
from scipy.spatial.distance import cosine

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, Response, Cookie, Depends
from fastapi.middleware.cors import CORSMiddleware  
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse

from database import FaceDatabase
from utils.face_detector import FaceDetector
from utils.face_embedder import FaceEmbedder
from utils.antispoof import AntiSpoof
from utils.liveness import LivenessDetector
from dotenv import load_dotenv
load_dotenv()

# Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-this-in-production")

app = FastAPI()
db = FaceDatabase(
    host=os.getenv("MYSQL_HOST", "localhost"),
    user=os.getenv("MYSQL_USER", "root"),
    password=os.getenv("MYSQL_PASSWORD", "Danish@123"),
    database=os.getenv("MYSQL_DB", "attendance_db")
)

# Enable CORS for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize models
detector = FaceDetector()
embedder = FaceEmbedder()
spoof = AntiSpoof()
liveness = LivenessDetector()

# Geofencing Configuration - Main office is now just the default location
MAIN_OFFICE_LOCATION = {
    "name": "Main Office HQ",
    "lat": 2.982273,
    "lon": 101.661411,
    "radius": 50
}
ALLOWED_PUBLIC_IP = "118.101.251.39"

# For testing on mobile, you might need to disable this via an environment variable
DISABLE_NETWORK_GATEKEEPER = os.getenv("DISABLE_NETWORK_GATEKEEPER", "false").lower() == "true"

@app.middleware("http")
async def network_gatekeeper(request: Request, call_next):
    if DISABLE_NETWORK_GATEKEEPER:
        print("DEBUG: Network gatekeeper is DISABLED.")
        return await call_next(request)

    client_ip = request.client.host
    print(f"DEBUG: Connection attempt from IP: {client_ip}") 

    is_local = client_ip in ["127.0.0.1", "localhost", "::1"]
    # Check for private IP ranges (e.g., 192.168.x.x, 10.x.x.x)
    is_lan = client_ip.startswith("192.168.") or client_ip.startswith("10.") or (client_ip.startswith("172.") and 16 <= int(client_ip.split('.')[1]) <= 31)
    is_allowed_public = client_ip == ALLOWED_PUBLIC_IP

    if is_local or is_lan or is_allowed_public:
        return await call_next(request)
    
    # If not in any allowed category, deny access.
    raise HTTPException(
        status_code=403, 
        detail=f"FORBIDDEN: Your IP ({client_ip}) is not authorized. Please connect to the correct network."
    )

def is_in_allowed_location(user_lat: float, user_lon: float):
    """
    Checks if the user is within the radius of the main office or any active on-site locations.
    """
    # 1. Get all active sites from the database
    active_sites = db.get_active_sites()
    
    # 2. Add the main office to the list of locations to check
    all_allowed_locations = [MAIN_OFFICE_LOCATION] + active_sites
    
    print(f"DEBUG: Checking against {len(all_allowed_locations)} allowed locations.")

    # 3. Check user's location against each allowed area
    for loc in all_allowed_locations:
        R = 6371000  # Earth radius in meters
        phi1 = math.radians(loc["lat"])
        phi2 = math.radians(user_lat)
        dphi = math.radians(user_lat - loc["lat"])
        dlambda = math.radians(user_lon - loc["lon"])

        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2) * math.sin(dlambda/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        distance = R * c
        
        print(f"DEBUG: Distance from '{loc['name']}': {distance:.2f}m. Required: <= {loc['radius']}m")
        
        if distance <= loc["radius"]:
            return True # User is inside an allowed zone

    return False # User is not in any allowed zone

def send_email_notification(to_email: str, subject: str, body: str):
    """Helper function to isolate SMTP configuration and email sending."""
    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587
    SENDER_EMAIL = os.getenv("SENDER_EMAIL", "your_email@gmail.com")
    SENDER_PASSWORD = os.getenv("SENDER_PASSWORD", "your_app_password")
    
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = SENDER_EMAIL
    msg['To'] = to_email

    server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
    server.starttls()
    server.login(SENDER_EMAIL, SENDER_PASSWORD)
    server.send_message(msg)
    server.quit()

@app.post("/recognize")
async def recognize(
    file: UploadFile = File(...), 
    lat: float = Form(...), 
    lon: float = Form(...)
):

    # --- STEP 1: Geofence Check ---
    if not is_in_allowed_location(lat, lon):
        return {"success": False, "error": f"Access Denied: You are outside the allowed office/site area."}

    # --- STEP 2: Process Image ---
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if image is None:
        return {"success": False, "error": "Invalid image format"}

    # --- STEP 3: Face Detection ---
    boxes = detector.detect(image)
    if not boxes:
        return {"success": False, "error": "No face detected"}

    # Take the first detected face
    x1, y1, x2, y2 = boxes[0]
    
    # Ensure coordinates are within image boundaries
    y1, y2 = max(0, y1), min(image.shape[0], y2)
    x1, x2 = max(0, x1), min(image.shape[1], x2)
    
    face = image[y1:y2, x1:x2]
    
    if face.size == 0:
        return {"success": False, "error": "Face crop failed"}

    # --- STEP 4: Anti-spoof & Liveness Checks ---
    if not spoof.check(image, (x1, y1, x2, y2)):
        return {"success": False, "error": "Spoof detected (Static Photo/Screen)"}

    if not liveness.check(face):
        return {"success": False, "error": "Liveness check failed (3D Depth check)"}

    # --- STEP 5: Recognition & Embedding ---
    emb = embedder.get_embedding(image)
    if emb is None:
        return {"success": False, "error": "Embedding extraction failed"}

    # ————— TODO: Compare with database embeddings —————
    # Example: Check cosine similarity with stored vectors here
    
    known_faces = db.get_all_users()
    if not known_faces:
        return {"success": False, "error": "Database is empty. Please register first."}

    best_name = "Unknown"
    highest_sim = 0.0
    threshold = 0.45 # 0.4 - 0.6 is the sweet spot for InsightFace

    for name, stored_emb in known_faces.items():
        # Calculate Cosine Similarity
        similarity = 1 - cosine(emb, stored_emb)
        if similarity > highest_sim:
            highest_sim = similarity
            best_name = name

    if highest_sim < threshold:
        return {"success": False, "error": "Face not recognized in system"}
    
    if highest_sim >= threshold:
       current_action = db.log_attendance(best_name)
    else:
       current_action = None
    
    return {
        "success": True,
        "message": f"Welcome, {best_name}!",
        "name": best_name,
        "action": current_action, # "IN" or "OUT"
        "confidence": round(float(highest_sim), 2)
    }

@app.post("/login")
async def login(response: Response, username: str = Form(...), password: str = Form(...)):
    if db.verify_admin(username, password):
        # We set a simple cookie. In a real company, use a random string, 
        # but for this demo, we'll just set "logged_in" to "true".
        response.set_cookie(key="admin_session", value="authorized", httponly=True)
        return {"success": True}
    raise HTTPException(status_code=401, detail="Invalid credentials")

@app.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key="admin_session", httponly=True)
    return {"success": True}

@app.post("/register")
async def register(
    name: str = Form(...), 
    email: str = Form(...),
    department: str = Form(...),
    file: UploadFile = File(...),
    admin_session: Optional[str] = Cookie(None) # FastAPI automatically checks cookies
):
    if admin_session != "authorized":
        raise HTTPException(status_code=401, detail="Admin access required")
    
    """Register a new user"""
    # 1. Convert image
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    # 2. Extract Embedding
    boxes = detector.detect(image)
    if not boxes:
        return {"success": False, "error": "No face detected for registration"}
    
    emb = embedder.get_embedding(image)
    if emb is None:
        return {"success": False, "error": "Failed to extract face features"}

    # 3. Save to SQLite
    try:
        db.register_user(name, email, department, emb)
        return {"success": True, "message": f"{name} registered successfully!"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/send-warning")
async def send_warning(
    name: str = Form(...),
    email: str = Form(...),
    time: str = Form(...),
    admin_session: Optional[str] = Cookie(None)
):
    if admin_session != "authorized":
        raise HTTPException(status_code=401, detail="Admin access required")
    
    subject = "Late Arrival Warning"
    body = f"Dear {name},\n\nThis is a formal warning regarding your late arrival recorded at {time}.\n\nPlease ensure you arrive on time in the future.\n\nManagement"

    try:
        send_email_notification(email, subject, body)
        return {"success": True, "message": "Warning email sent successfully!"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/users")
async def get_users(admin_session: Optional[str] = Cookie(None)):
    if admin_session != "authorized":
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"success": True, "users": db.get_all_users_details()}

@app.delete("/api/users/{user_id}")
async def delete_user(user_id: int, admin_session: Optional[str] = Cookie(None)):
    if admin_session != "authorized":
        raise HTTPException(status_code=401, detail="Unauthorized")
    db.delete_user(user_id)
    return {"success": True}

@app.put("/api/users/{user_id}")
async def update_user(
    user_id: int, 
    name: str = Form(...), 
    email: str = Form(...), 
    department: str = Form(...), 
    admin_session: Optional[str] = Cookie(None)
):
    if admin_session != "authorized":
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    db.update_user(user_id, name, email, department)
    return {"success": True}


# --- SITE MANAGEMENT API ---

@app.get("/api/sites")
async def get_sites(admin_session: Optional[str] = Cookie(None)):
    if admin_session != "authorized":
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"success": True, "sites": db.get_all_sites()}

@app.post("/api/sites")
async def add_site(
    name: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    radius: int = Form(...),
    admin_session: Optional[str] = Cookie(None)
):
    if admin_session != "authorized":
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        db.add_site(name, latitude, longitude, radius)
        return {"success": True, "message": "Site added successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/sites/{site_id}")
async def update_site(
    site_id: int,
    name: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    radius: int = Form(...),
    is_active: bool = Form(...),
    admin_session: Optional[str] = Cookie(None)
):
    if admin_session != "authorized":
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        db.update_site(site_id, name, latitude, longitude, radius, is_active)
        return {"success": True, "message": "Site updated successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/sites/{site_id}")
async def delete_site(site_id: int, admin_session: Optional[str] = Cookie(None)):
    if admin_session != "authorized":
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        db.delete_site(site_id)
        return {"success": True, "message": "Site deleted successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ————— FRONTEND SERVING —————

@app.get("/api/live-attendance")
async def get_live_attendance():
    """Public endpoint to show recent logs without exposing emails."""
    logs = db.get_attendance_logs()
    safe_logs = [{"name": log["name"], "time": log["time"], "status": log["status"]} for log in logs[:15]]
    return {"success": True, "logs": safe_logs}

if os.path.exists("frontend"):
    app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")

@app.get("/attendance-data")
async def get_attendance(admin_session: Optional[str] = Cookie(None)):
    if admin_session != "authorized":
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    logs = db.get_attendance_logs()
    return {"success": True, "logs": logs}

@app.get("/download-attendance")
async def download_attendance(
    start_date: str,
    end_date: str,
    name: Optional[str] = None,
    admin_session: Optional[str] = Cookie(None)
):
    if admin_session != "authorized":
        raise HTTPException(status_code=401, detail="Unauthorized")

    logs = db.get_attendance_logs_by_query(start_date, end_date, name)

    if not logs:
        raise HTTPException(status_code=404, detail=f"No attendance data found for the selected criteria.")

    df = pd.DataFrame(logs)
    df.rename(columns={'name': 'Name', 'time': 'Timestamp', 'status': 'Status'}, inplace=True)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Attendance')
        worksheet = writer.sheets['Attendance']
        # Auto-adjust column widths for better readability
        for idx, col in enumerate(df):
            series = df[col]
            # Handle empty series and find max length
            max_len = max((
                series.astype(str).map(len).max() or 0,
                len(str(series.name))
            )) + 2
            worksheet.set_column(idx, idx, max_len)

    output.seek(0)

    filename = f"attendance_{start_date}_to_{end_date}.xlsx"
    if name and name != "All":
        filename = f"attendance_{name}_{start_date}_to_{end_date}.xlsx"

    headers = {'Content-Disposition': f'attachment; filename="{filename}"'}

    return StreamingResponse(
        output,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers=headers
    )

@app.get("/")
async def read_index():
    return FileResponse('frontend/index.html')

@app.get("/verify-session")
async def verify_session(admin_session: Optional[str] = Cookie(None)):
    if admin_session == "authorized":
        return {"status": "ok"}
    raise HTTPException(status_code=401, detail="Unauthorized")

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
