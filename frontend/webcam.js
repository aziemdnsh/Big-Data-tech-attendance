const video = document.getElementById("webcam");
const canvas = document.getElementById("canvas");
const statusText = document.getElementById("status");
const button = document.getElementById("captureBtn");

// Start webcam
async function startWebcam() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true });
        video.srcObject = stream;
    } catch (err) {
        statusText.textContent = "❌ Camera access denied";
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

// Send image and location to backend
// Send image and location to backend
button.addEventListener("click", async () => {
    statusText.textContent = "Status: Locating...";

    try {
        // 1. Get Location
        const position = await getPosition();
        const lat = position.coords.latitude;
        const lon = position.coords.longitude;

        statusText.textContent = "Status: Scanning Face...";

        // 2. Capture Image
        const blob = await captureImage();
        
        // 3. Prepare Form Data
        const formData = new FormData();
        formData.append("file", blob, "face.jpg");
        formData.append("lat", lat);
        formData.append("lon", lon);

        // 4. Send to Backend
        // Removed 'http://localhost:8000' to make it relative (better for mobile hotspot)
        const res = await fetch("/recognize", {
            method: "POST",
            body: formData,
        });

        const data = await res.json();

        if (!data.success) {
            statusText.textContent = "❌ " + data.error;
            statusText.style.color = "#ff4d4d"; // Error Red
        } else {
            // NEW: Logic to handle IN/OUT toggle feedback
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
            
            // Revert status text after 4 seconds
            setTimeout(() => {
                statusText.textContent = "System Online";
                statusText.style.color = "rgba(255, 255, 255, 0.7)";
            }, 4000);
        }

    } catch (err) {
        statusText.style.color = "#ff4d4d";
        if (err.code === 1) {
            statusText.textContent = "❌ Please allow Location Access";
        } else {
            statusText.textContent = "❌ Connection or Location Error";
        }
        console.error(err);
    }
});

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