const video = document.getElementById("webcam");
const canvas = document.getElementById("canvas");
const statusText = document.getElementById("status");
const registerBtn = document.getElementById("registerBtn");
const nameInput = document.getElementById("userName");

// Immediate check for admin session
    async function protectPage() {
        try {
            const res = await fetch('/verify-session');
            if (res.status !== 200) {
                window.location.href = "/frontend/login.html";
            }
        } catch (err) {
            window.location.href = "/frontend/login.html";
        }
    }
    protectPage();

async function startWebcam() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true });
        video.srcObject = stream;
    } catch (err) {
        statusText.textContent = "❌ Camera Access Denied";
    }
}
startWebcam();

registerBtn.addEventListener("click", async () => {
    const name = nameInput.value.trim();
    if (!name) {
        statusText.textContent = "❌ Please enter a name";
        return;
    }

    statusText.textContent = "Status: Registering...";

    // 1. Prepare Canvas
    const context = canvas.getContext("2d");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    
    // 2. Capture Frame
    context.drawImage(video, 0, 0, canvas.width, canvas.height);

    // 3. Convert to Blob and Send
    canvas.toBlob(async (blob) => {
        const formData = new FormData();
        formData.append("file", blob, "register.jpg");
        formData.append("name", name);

        try {
            // Browser automatically attaches cookies for session validation
            const res = await fetch("/register", {
                method: "POST",
                body: formData
            });

            // Handle Unauthorized (Cookie missing or expired)
            if (res.status === 401) {
                statusText.textContent = "❌ Not logged in. Redirecting...";
                setTimeout(() => {
                    window.location.href = "/frontend/login.html";
                }, 2000);
                return;
            }

            const data = await res.json();
            if (data.success) {
                statusText.textContent = `✅ ${data.message || "Success!"}`;
                nameInput.value = ""; // Clear input for next user
            } else {
                statusText.textContent = "❌ " + data.error;
            }

        } catch (err) {
            console.error(err);
            statusText.textContent = "❌ Server error. Check connection.";
        }
    }, "image/jpeg");
});