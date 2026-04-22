const loginBtn = document.getElementById('loginBtn');
const statusText = document.getElementById('status');

loginBtn.onclick = async () => {
    const user = document.getElementById('user').value;
    const pass = document.getElementById('pass').value;

    if (!user || !pass) {
        statusText.textContent = "⚠️ Please enter credentials";
        statusText.style.color = "#d4af37";
        return;
    }

    statusText.textContent = "Authenticating...";

    try {
        const formData = new FormData();
        formData.append('username', user);
        formData.append('password', pass);

        const res = await fetch('/login', {
            method: 'POST',
            body: formData
        });

        // This is where 'data' is defined!
        const data = await res.json();

        if (res.ok && data.success) {
            statusText.textContent = "✅ Access Granted. Redirecting...";
            statusText.style.color = "#4CAF50";
            setTimeout(() => {
                window.location.href = "/frontend/dashboard.html";
            }, 1000);
        } else {
            statusText.textContent = "❌ Invalid Username or Password";
            statusText.style.color = "#ff4d4d";
        }
    } catch (err) {
        console.error("Login Error:", err);
        statusText.textContent = "❌ Connection to Server Failed";
        statusText.style.color = "#ff4d4d";
    }
};