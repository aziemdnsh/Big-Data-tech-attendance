const video = document.getElementById("webcam");
const canvas = document.getElementById("canvas");
const statusText = document.getElementById("status");
const registerBtn = document.getElementById("registerBtn");
const nameInput = document.getElementById("userName");
const emailInput = document.getElementById("userEmail");
const deptInput = document.getElementById("userDept");

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
    const email = emailInput.value.trim();
    const department = deptInput.value.trim();
    if (!name) {
        statusText.textContent = "❌ Please enter a name";
        return;
    }
    
    if (!email) {
        statusText.textContent = "❌ Please enter an email address";
        return;
    }
    
    if (!department) {
        statusText.textContent = "❌ Please enter a department";
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
        formData.append("email", email);
        formData.append("department", department);

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
                emailInput.value = ""; 
                deptInput.value = "";
                fetchStaffList(); // Automatically reload table on success
            } else {
                statusText.textContent = "❌ " + data.error;
            }

        } catch (err) {
            console.error(err);
            statusText.textContent = "❌ Server error. Check connection.";
        }
    }, "image/jpeg");
});

// --- STAFF MANAGEMENT LOGIC ---

async function fetchStaffList() {
    try {
        const res = await fetch("/api/users");
        if (res.status === 401) return;
        const data = await res.json();
        
        if (data.success) {
            const tbody = document.getElementById("staffTableBody");
            tbody.innerHTML = data.users.map(u => `
                <tr>
                    <td style="padding: 10px 5px; border-bottom: 1px solid rgba(255,255,255,0.1);">${u.name}</td>
                    <td style="padding: 10px 5px; border-bottom: 1px solid rgba(255,255,255,0.1);">${u.email || 'N/A'}</td>
                    <td style="padding: 10px 5px; border-bottom: 1px solid rgba(255,255,255,0.1);">${u.department || 'N/A'}</td>
                    <td style="padding: 10px 5px; border-bottom: 1px solid rgba(255,255,255,0.1); text-align: right;">
                        <button onclick="openEditModal(${u.id}, '${u.name.replace(/'/g, "\\'")}', '${(u.email || '').replace(/'/g, "\\'")}', '${(u.department || '').replace(/'/g, "\\'")}')" style="background: rgba(76, 175, 80, 0.2); color: #4CAF50; border: 1px solid #4CAF50; padding: 4px 8px; cursor: pointer; border-radius: 4px; font-size: 10px; margin-right: 5px;">EDIT</button>
                        <button onclick="deleteStaff(${u.id})" style="background: rgba(255, 77, 77, 0.2); color: #ff4d4d; border: 1px solid #ff4d4d; padding: 4px 8px; cursor: pointer; border-radius: 4px; font-size: 10px;">DEL</button>
                    </td>
                </tr>
            `).join('');
        }
    } catch (err) {
        console.error("Failed to load staff list", err);
    }
}

async function deleteStaff(id) {
    if (!confirm("Are you sure you want to permanently delete this staff member? Their attendance logs will remain, but their face data will be destroyed.")) return;
    
    try {
        const res = await fetch(`/api/users/${id}`, { method: "DELETE" });
        const data = await res.json();
        if (data.success) fetchStaffList();
        else alert("Failed to delete staff member.");
    } catch (err) { console.error(err); }
}

function openEditModal(id, name, email, dept) {
    document.getElementById("editUserId").value = id;
    document.getElementById("editUserName").value = name;
    document.getElementById("editUserEmail").value = email;
    document.getElementById("editUserDept").value = dept;
    document.getElementById("editUserModal").style.display = "flex";
}

function closeModal() { document.getElementById("editUserModal").style.display = "none"; }

async function submitEdit() {
    const id = document.getElementById("editUserId").value;
    const formData = new FormData();
    formData.append("name", document.getElementById("editUserName").value.trim());
    formData.append("email", document.getElementById("editUserEmail").value.trim());
    formData.append("department", document.getElementById("editUserDept").value.trim());

    try {
        const res = await fetch(`/api/users/${id}`, { method: "PUT", body: formData });
        const data = await res.json();
        if (data.success) { closeModal(); fetchStaffList(); } 
        else { alert("Failed to update staff member."); }
    } catch (err) { console.error(err); }
}

// Load table on boot
fetchStaffList();