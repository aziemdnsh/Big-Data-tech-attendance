// frontend/dashboard.js
document.addEventListener('DOMContentLoaded', () => {
    loadAttendanceLogs();
    
    document.getElementById('logoutBtn').addEventListener('click', () => {
        // Clear the session cookie by setting expiry to the past
        document.cookie = "admin_session=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
        window.location.href = "/frontend/login.html";
    });
});

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
                const statusClass = log.status === "IN" ? "status-in" : "status-out";
                return `
                    <tr>
                        <td>${log.name}</td>
                        <td>${log.time}</td>
                        <td><span class="${statusClass}">${log.status}</span></td>
                        <td style="color: #d4af37">SECURE-MATCH</td>
                    </tr>
                `;
            }).join('');
        }
    } catch (err) {
        console.error("Dashboard Error:", err);
        tbody.innerHTML = '<tr><td colspan="4" style="color: #ff4d4d; text-align:center;">CRITICAL ERROR RETRIEVING DATA</td></tr>';
    }
}