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

function setupDownloadForm() {
    const monthSelect = document.getElementById('month-select');
    const yearSelect = document.getElementById('year-select');
    const downloadForm = document.getElementById('download-form');
    const downloadError = document.getElementById('download-error');

    if (!monthSelect || !yearSelect || !downloadForm || !downloadError) {
        console.warn("Download form elements not found in dashboard.html. Skipping download form setup.");
        return;
    }

    // Populate months
    const months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
    months.forEach((month, index) => {
        const option = document.createElement('option');
        option.value = index + 1;
        option.textContent = month;
        monthSelect.appendChild(option);
    });

    // Populate years (current year + last 4 years)
    const currentYear = new Date().getFullYear();
    for (let i = 0; i < 5; i++) {
        const year = currentYear - i;
        const option = document.createElement('option');
        option.value = year;
        option.textContent = year;
        yearSelect.appendChild(option);
    }

    // Set current month and year as default
    const currentDate = new Date();
    monthSelect.value = currentDate.getMonth() + 1;
    yearSelect.value = currentDate.getFullYear();

    downloadForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        downloadError.textContent = '';

        const year = yearSelect.value;
        const month = monthSelect.value;
        const url = `/download-attendance?year=${year}&month=${month}`;
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
            a.download = `attendance_${year}_${String(month).padStart(2, '0')}.xlsx`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(downloadUrl);
            a.remove();
        } catch (error) {
            console.error('Download failed:', error);
            downloadError.textContent = `Error: ${error.message}`;
        } finally {
            submitButton.textContent = 'Download Excel';
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