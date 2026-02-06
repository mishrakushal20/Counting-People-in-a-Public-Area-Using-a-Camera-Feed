console.log("route-guard.js loaded");

function getTokenPayload() {
    const token = localStorage.getItem("access_token");
    if (!token) return null;

    try {
        return JSON.parse(atob(token.split(".")[1]));
    } catch {
        return null;
    }
}

function requireAuth() {
    console.log("requireAuth running");

    const user = getTokenPayload();
    if (!user) {
        console.log("No token → redirect to login");
        window.location.href = "/login";
    }
}

function requireAdmin() {
    const user = getTokenPayload();
    if (!user || user.role !== "admin") {
        window.location.href = "/dashboard";
    }
}

