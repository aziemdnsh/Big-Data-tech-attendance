const video = document.getElementById("webcam");
const canvas = document.getElementById("canvas");
const statusText = document.getElementById("status");

let isProcessing = false; // State to prevent concurrent requests

// Fetch and render Live Attendance
async function fetchLiveAttendance() {
    try {
        const res = await fetch('/api/live-attendance');
        const data = await res.json();
        if (data.success) {
            const container = document.getElementById('attendance-list');
            if (!container) return; // Wait until HTML is added

            container.innerHTML = data.logs.map(log => {
                let badgeClass = 'status-out';
                if (log.status.includes('IN')) {
                    badgeClass = log.status.includes('LATE') ? 'status-late' : 'status-in';
                }
                return `
                    <div class="live-log-item">
                        <div>
                            <strong>${log.name}</strong><br>
                            <span style="font-size: 0.8em; color: #888;">${log.time}</span>
                        </div>
                        <span class="status-badge ${badgeClass}">${log.status}</span>
                    </div>
                `;
            }).join('');
        }
    } catch (err) {
        console.error("Failed to fetch live attendance", err);
    }
}

// Call it initially and poll every 10 seconds
fetchLiveAttendance();
setInterval(fetchLiveAttendance, 10000);

// Start webcam
async function startWebcam() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true });
        video.srcObject = stream;
        // Once the video can play, start the recognition loop
        video.addEventListener('canplay', () => {
            statusText.textContent = "System Online. Scanning...";
            setInterval(runRecognition, 2500); // Check every 2.5 seconds
        });
    } catch (err) {
        statusText.textContent = "❌ Camera access denied";
        statusText.style.color = "#ff4d4d";
        console.error(err);
    }
}
startWebcam();

// Get GPS Position
async function getPosition() {
    return new Promise((resolve, reject) => {
        if (!navigator.geolocation) {
            reject(new Error("Geolocation not supported by browser"));
        }
        navigator.geolocation.getCurrentPosition(resolve, reject, {
            enableHighAccuracy: true, // Use GPS if available for better precision
            timeout: 5000,
            maximumAge: 0
        });
    });
}

// Capture frame
function captureImage() {
    const context = canvas.getContext("2d");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    context.drawImage(video, 0, 0, canvas.width, canvas.height);

    return new Promise(resolve => {
        canvas.toBlob(resolve, "image/jpeg");
    });
}

function resetScanner(delay = 3000) {
    setTimeout(() => {
        isProcessing = false;
        statusText.textContent = "System Online. Scanning...";
        statusText.style.color = "rgba(255, 255, 255, 0.7)";
    }, delay);
}

function handleRecognitionError(errorMsg) {
    // For non-critical errors like "no face", we just reset immediately silently.
    if (errorMsg !== "No face detected" && errorMsg !== "Face crop failed" && errorMsg !== "Embedding extraction failed") {
        statusText.textContent = "⚠️ " + errorMsg;
        statusText.style.color = "#ff9800"; // Warning orange
        resetScanner(3000);
    } else {
        isProcessing = false;
    }
}

function handleRecognitionSuccess(data) {
    let actionColor = "#d4af37"; // Default Gold for OUT
    let actionText = "CHECKED-OUT";

    if (data.action === "IN") {
        actionColor = "#4CAF50"; // Green for on-time IN
        actionText = "CHECKED-IN";
    } else if (data.action === "IN (LATE)") {
        actionColor = "#ff9800"; // Orange for LATE IN
        actionText = "CHECKED-IN (LATE)";
    }

    statusText.innerHTML = `✅ ${data.name} <br> <span style="color: ${actionColor}; font-size: 0.8em;">${actionText}</span>`;
    fetchLiveAttendance(); // Refresh the attendance sidebar immediately
    resetScanner(4000); // Pause processing to show the result
}

async function runRecognition() {
    if (isProcessing || document.hidden) { // Don't run if tab is not visible or already processing
        return;
    }
    isProcessing = true;

    try {
        // 1. Get Location
        const position = await getPosition();
        
        // 2. Capture Image
        const blob = await captureImage();

        // 3. Prepare Form Data
        const formData = new FormData();
        formData.append("file", blob, "face.jpg");
        formData.append("lat", position.coords.latitude);
        formData.append("lon", position.coords.longitude);
        
        // 4. Send to Backend
        const res = await fetch("/recognize", {
            method: "POST",
            body: formData,
        });
        
        const data = await res.json();

        if (!data.success) {
            handleRecognitionError(data.error);
        } else {
            handleRecognitionSuccess(data);
        }
    } catch (err) {
        statusText.style.color = "#ff4d4d";
        if (err.code === 1) {
            statusText.textContent = "❌ Please allow Location Access";
        } else {
            statusText.textContent = "❌ Connection or Location Error";
        }
        console.error(err);
        // On critical errors, pause for a bit before retrying.
        resetScanner(5000);
    }
}
// --- Live Clock & Date Logic ---
function updateKioskTime() {
    const clock = document.getElementById('live-clock');
    const dateDisplay = document.getElementById('current-date');
    
    const now = new Date();
    
    // Format: 10:52:16 AM
    clock.textContent = now.toLocaleTimeString([], { 
        hour: '2-digit', 
        minute: '2-digit', 
        second: '2-digit' 
    });

    // Format: Tuesday, April 21, 2026
    dateDisplay.textContent = now.toLocaleDateString([], { 
        weekday: 'long', 
        month: 'long', 
        day: 'numeric', 
        year: 'numeric' 
    });
}

// Update clock every second
setInterval(updateKioskTime, 1000);
updateKioskTime(); // Run immediately so it doesn't show "Loading..."