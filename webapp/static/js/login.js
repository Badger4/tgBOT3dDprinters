/**
 * 3D Farm Manager - Login Page Logic
 */

function togglePassVisibility() {
    const input = document.getElementById("password-input");
    const icon = document.getElementById("pass-icon");
    if (input.type === "password") {
        input.type = "text";
        icon.className = "fa-solid fa-eye-slash";
    } else {
        input.type = "password";
        icon.className = "fa-solid fa-eye";
    }
}

async function handleLogin(e) {
    e.preventDefault();
    const alertEl = document.getElementById("login-alert");
    const btnEl = document.getElementById("login-btn");
    const passInput = document.getElementById("password-input");
    const password = passInput.value.trim();

    alertEl.style.display = "none";
    btnEl.disabled = true;
    btnEl.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-2"></i> Перевірка...';

    try {
        const res = await fetch("/api/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ password })
        });

        const data = await res.json();
        if (res.ok && data.status === "ok") {
            if (data.token) {
                localStorage.setItem("3d_farm_session", data.token);
            }
            window.location.href = "/webapp";
        } else {
            alertEl.textContent = "⚠️ " + (data.error || "Невірний пароль доступу!");
            alertEl.style.display = "block";
        }
    } catch (err) {
        console.error("Login error:", err);
        alertEl.textContent = "⚠️ Помилка зв'язку із сервером.";
        alertEl.style.display = "block";
    } finally {
        btnEl.disabled = false;
        btnEl.innerHTML = '<i class="fa-solid fa-right-to-bracket me-2"></i> Увійти в систему';
    }
}

// Check if session already active
(async () => {
    try {
        const res = await fetch("/api/auth/session");
        const data = await res.json();
        if (data.authenticated) {
            window.location.href = "/webapp";
        }
    } catch (e) {}
})();
