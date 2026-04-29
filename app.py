
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

# Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-this-in-production")

app = FastAPI()
db = FaceDatabase()

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

# Geofencing Configuration
OFFICE_LAT = 2.982273
OFFICE_LON = 101.661411
ALLOWED_RADIUS_METERS = 50
ALLOWED_PUBLIC_IP = "118.101.251.39" 

@app.middleware("http")
async def network_gatekeeper(request: Request, call_next):
    # Get the IP the server sees
    client_ip = request.client.host
    print(f"DEBUG: Connection attempt from IP: {client_ip}") 

    # 1. Always allow the machine itself
    if client_ip in ["127.0.0.1", "localhost", "::1"]:
        return await call_next(request)

    # 2. ONLY allow if it matches the BigData@5G Public IP
    # If you are on a different Wi-Fi (like the iPhone hotspot), 
    # your Public IP will change, and this will block you.
    if client_ip != ALLOWED_PUBLIC_IP:
        # Check if it's a local IP from a different network
        # If you want to be EXTREMELY strict, remove the 'startswith' check below
        if not client_ip.startswith("192.168.") and not client_ip.startswith("10.") and not client_ip.startswith("172."): 
            raise HTTPException(
                status_code=403, 
                detail="FORBIDDEN: Unauthorized Network. Please connect to BigData@5G."
            )
    
    return await call_next(request)

def is_in_office(user_lat, user_lon):
    """Calculates if the user is within the office radius using Haversine formula."""
    R = 6371000  # Earth radius in meters
    phi1 = math.radians(OFFICE_LAT)
    phi2 = math.radians(user_lat)
    dphi = math.radians(user_lat - OFFICE_LAT)
    dlambda = math.radians(user_lon - OFFICE_LON)

    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2) * math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    distance = R * c
    
    print(f"User Distance: {distance:.2f}m") # Helpful for debugging
    return distance <= ALLOWED_RADIUS_METERS


def send_email_notification(to_email: str, subject: str, body: str):
    """Helper function to isolate SMTP configuration and email sending."""
    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587
    SENDER_EMAIL = "your_email@gmail.com" 
    SENDER_PASSWORD = "your_app_password" 
    
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
    known_faces = db.get_all_users()
    print(f"Received Request - Location: {lat}, {lon}")

    # --- STEP 1: Geofence Check ---
    if not is_in_office(lat, lon):
        return {"success": False, "error": f"Access Denied: You are outside the office area."}

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
