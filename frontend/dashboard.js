// frontend/dashboard.js
document.addEventListener('DOMContentLoaded', () => {
    loadAttendanceLogs();
    setupDownloadForm();
    
    document.getElementById('logoutBtn').addEventListener('click', () => {
        // Clear the session cookie by setting expiry to the past
        document.cookie = "admin_session=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
        window.location.href = "/frontend/login.html";
    });
});

async function setupDownloadForm() {
    const startDateInput = document.getElementById('start-date');
    const endDateInput = document.getElementById('end-date');
    const nameSelect = document.getElementById('name-select');
    const downloadForm = document.getElementById('download-form');
    const downloadError = document.getElementById('download-error');

    if (!startDateInput || !endDateInput || !nameSelect || !downloadForm || !downloadError) {
        console.warn("Download form elements not found in dashboard.html. Skipping download form setup.");
        return;
    }

    // Set default dates (e.g., first day of current month to today)
    const today = new Date();
    const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);
    
    // Format to YYYY-MM-DD
    const formatDate = (date) => {
        const d = new Date(date);
        let month = '' + (d.getMonth() + 1);
        let day = '' + d.getDate();
        const year = d.getFullYear();

        if (month.length < 2) month = '0' + month;
        if (day.length < 2) day = '0' + day;

        return [year, month, day].join('-');
    };

    startDateInput.value = formatDate(firstDay);
    endDateInput.value = formatDate(today);

    // Populate names from backend
    try {
        const response = await fetch('/api/users');
        if (response.ok) {
            const data = await response.json();
            if (data.success && data.users) {
                data.users.forEach(user => {
                    const option = document.createElement('option');
                    option.value = user.name;
                    option.textContent = user.name;
                    nameSelect.appendChild(option);
                });
            }
        }
    } catch (err) {
        console.error("Failed to fetch users for dropdown:", err);
    }

    downloadForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        downloadError.textContent = '';

        const startDate = startDateInput.value;
        const endDate = endDateInput.value;
        const name = nameSelect.value;
        
        let url = `/download-attendance?start_date=${startDate}&end_date=${endDate}`;
        if (name !== 'All') {
            url += `&name=${encodeURIComponent(name)}`;
        }
        
        const submitButton = downloadForm.querySelector('button');

        try {
            submitButton.textContent = 'Downloading...';
            submitButton.disabled = true;

            const response = await fetch(url);

            if (response.status === 401) {
                window.location.href = "/frontend/login.html";
                return;
            }

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to download file.');
            }

            const blob = await response.blob();
            const downloadUrl = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = downloadUrl;
            let filename = `attendance_${startDate}_to_${endDate}.xlsx`;
            if (name !== 'All') {
                filename = `attendance_${name}_${startDate}_to_${endDate}.xlsx`;
            }
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(downloadUrl);
            a.remove();
        } catch (error) {
            console.error('Download failed:', error);
            downloadError.textContent = `Error: ${error.message}`;
        } finally {
            submitButton.textContent = 'Generate Excel';
            submitButton.disabled = false;
        }
    });
}

async function loadAttendanceLogs() {
    const tbody = document.getElementById('attendance-rows');
    try {
        const response = await fetch('/attendance-data'); 

        // Handle Session Expiry
        if (response.status === 401) {
            window.location.href = "/frontend/login.html";
            return;
        }

        const data = await response.json();

        if (data.success) {
            // Check if there are actually logs to show
            if (data.logs.length === 0) {
                tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; padding: 20px;">NO ATTENDANCE RECORDS FOUND</td></tr>';
                return;
            }

            // Map data into rows
            tbody.innerHTML = data.logs.map(log => {
                let statusClass = "status-out";
                if (log.status === "IN") statusClass = "status-in";
                else if (log.status === "IN (LATE)") statusClass = "status-late";
                
                let actionHtml = '<span style="color: #d4af37">SECURE-MATCH</span>';
                if (log.status === "IN (LATE)" && log.email && log.email !== "No Email") {
                    actionHtml = `<button onclick="sendWarningEmail('${log.name}', '${log.email}', '${log.time}', this)" class="nav-btn" style="background: rgba(255, 77, 77, 0.8); color: #fff; padding: 5px 10px; border-radius: 4px; border: none; cursor: pointer; font-size: 10px;">SEND WARNING EMAIL</button>`;
                }

                return `
                    <tr>
                        <td>${log.name}<br><span style="font-size: 11px; color: rgba(255,255,255,0.5);">${log.email || "No Email"}</span></td>
                        <td>${log.time}</td>
                        <td><span class="${statusClass}">${log.status}</span></td>
                        <td>${actionHtml}</td>
                    </tr>
                `;
            }).join('');
        }
    } catch (err) {
        console.error("Dashboard Error:", err);
        tbody.innerHTML = '<tr><td colspan="4" style="color: #ff4d4d; text-align:center;">CRITICAL ERROR RETRIEVING DATA</td></tr>';
    }
}

// Function to trigger the backend email sending
async function sendWarningEmail(name, email, time, buttonElement) {
    const originalText = buttonElement.textContent;
    buttonElement.textContent = "SENDING...";
    buttonElement.disabled = true;

    const formData = new FormData();
    formData.append("name", name);
    formData.append("email", email);
    formData.append("time", time);

    try {
        const res = await fetch("/send-warning", {
            method: "POST",
            body: formData
        });
        const data = await res.json();
        
        if (data.success) {
            buttonElement.textContent = "SENT ✅";
            buttonElement.style.background = "#4CAF50"; // Turn green
        } else {
            alert("Failed to send email: " + data.error);
            buttonElement.textContent = originalText;
            buttonElement.disabled = false;
        }
    } catch (err) {
        alert("Network error while sending email.");
        buttonElement.textContent = originalText;
        buttonElement.disabled = false;
    }
}