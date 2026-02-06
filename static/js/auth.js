function getUserFromToken() {
    const token = localStorage.getItem("access_token");
    if (!token) return null;

    try {
        const payload = JSON.parse(atob(token.split(".")[1]));
        return payload;
    } catch {
        return null;
    }
}

function hideAdminMenuIfNeeded() {
    const user = getUserFromToken();
    const adminLink = document.getElementById("adminSettingsLink");

    if (!user || user.role !== "admin") {
        if (adminLink) adminLink.style.display = "none";
    }
}

async function logoutUser() {
    const accessToken = localStorage.getItem("access_token");
    const refreshToken = localStorage.getItem("refresh_token");

    try {
        if (accessToken && refreshToken) {
            await fetch("http://127.0.0.1:5002/api/auth/logout", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": "Bearer " + accessToken
                },
                body: JSON.stringify({
                    refresh_token: refreshToken
                })
            });
        }
    } catch (e) {
        console.warn("Logout API failed, clearing session locally");
    }

    // 🔥 CLEAR TOKENS
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");

    // 🔁 REDIRECT TO LOGIN
    window.location.href = "/login";
}
