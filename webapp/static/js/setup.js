/**
 * 3D Farm Manager - Setup Wizard Page Logic
 */

async function handleSetup(e) {
    e.preventDefault();
    const alertEl = document.getElementById("setup-alert");
    const btnEl = document.getElementById("setup-btn");

    const admin_password = document.getElementById("admin-pass-input").value.trim();
    const telegram_bot_token = document.getElementById("bot-token-input").value.trim();
    const admin_chat_id = document.getElementById("admin-chat-id-input").value.trim();
    const electricity_cost = document.getElementById("electricity-cost-input").value.trim();

    if (!admin_password) {
        alertEl.textContent = "⚠️ Пароль адміністратора є обов'язковим!";
        alertEl.style.display = "block";
        return;
    }

    alertEl.style.display = "none";
    btnEl.disabled = true;
    btnEl.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-2"></i> Збереження...';

    try {
        const res = await fetch("/api/setup", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                admin_password,
                telegram_bot_token,
                admin_chat_id,
                electricity_cost
            })
        });

        const data = await res.json();
        if (res.ok && data.status === "ok") {
            if (data.token) {
                localStorage.setItem("3d_farm_session", data.token);
            }
            alert("🎉 Система успішно налаштована!");
            window.location.href = "/webapp";
        } else {
            alertEl.textContent = "⚠️ " + (data.error || "Помилка збереження налаштувань!");
            alertEl.style.display = "block";
        }
    } catch (err) {
        console.error("Setup error:", err);
        alertEl.textContent = "⚠️ Помилка зв'язку із сервером.";
        alertEl.style.display = "block";
    } finally {
        btnEl.disabled = false;
        btnEl.innerHTML = '<i class="fa-solid fa-check me-2"></i> Завершити Налаштування та Увійти';
    }
}
