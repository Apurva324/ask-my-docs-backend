const API_URL = "https://askdocs.duckdns.org";
let token = localStorage.getItem("token");
let currentSessionId = null;
let currentDocId = null;

// ── Init ──────────────────────────────────────────────────────────────────────
window.onload = () => {
    if (token) {
        showSection("dashboard-section");
        loadDocuments();
    } else {
        showSection("auth-section");
    }
};

// ── Helpers ───────────────────────────────────────────────────────────────────
function showSection(id) {
    document.querySelectorAll(".section").forEach(s => s.style.display = "none");
    document.getElementById(id).style.display = "block";
}

function showTab(tab) {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    document.getElementById("login-form").style.display = tab === "login" ? "block" : "none";
    document.getElementById("register-form").style.display = tab === "register" ? "block" : "none";
    event.target.classList.add("active");
}

function setError(msg) {
    document.getElementById("auth-error").textContent = msg;
}

function setStatus(msg, color = "#888") {
    const el = document.getElementById("upload-status");
    el.textContent = msg;
    el.style.color = color;
}

// ── Auth ──────────────────────────────────────────────────────────────────────
async function register() {
    const email = document.getElementById("reg-email").value;
    const password = document.getElementById("reg-password").value;

    try {
        const res = await fetch(`${API_URL}/auth/register`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail);

        token = data.access_token;
        localStorage.setItem("token", token);
        showSection("dashboard-section");
        loadDocuments();
    } catch (err) {
        setError(err.message);
    }
}

async function login() {
    const email = document.getElementById("login-email").value;
    const password = document.getElementById("login-password").value;

    try {
        const res = await fetch(`${API_URL}/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: `username=${encodeURIComponent(email)}&password=${encodeURIComponent(password)}`
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail);

        token = data.access_token;
        localStorage.setItem("token", token);
        showSection("dashboard-section");
        loadDocuments();
    } catch (err) {
        setError(err.message);
    }
}

function logout() {
    localStorage.removeItem("token");
    token = null;
    showSection("auth-section");
}

// ── Documents ─────────────────────────────────────────────────────────────────
async function loadDocuments() {
    try {
        const res = await fetch(`${API_URL}/documents/`, {
            headers: { "Authorization": `Bearer ${token}` }
        });
        const docs = await res.json();
        renderDocuments(docs);
    } catch (err) {
        document.getElementById("documents-list").innerHTML =
            '<p class="error">Failed to load documents</p>';
    }
}

function renderDocuments(docs) {
    const container = document.getElementById("documents-list");
    if (docs.length === 0) {
        container.innerHTML = '<p class="loading">No documents yet. Upload a PDF to get started.</p>';
        return;
    }

    container.innerHTML = docs.map(doc => `
        <div class="doc-card" onclick="openChat(${doc.id}, '${doc.filename}', '${doc.status}')">
            <div class="doc-info">
                <h4>📄 ${doc.filename}</h4>
                <span class="doc-status ${doc.status}">${doc.status}</span>
            </div>
            <button class="doc-delete" onclick="deleteDocument(event, ${doc.id})">🗑</button>
        </div>
    `).join("");
}

async function uploadFile(input) {
    const file = input.files[0];
    if (!file) return;

    setStatus("Uploading...", "#fbbf24");

    const formData = new FormData();
    formData.append("file", file);

    try {
        const res = await fetch(`${API_URL}/documents/upload`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${token}` },
            body: formData
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail);

        setStatus("Uploaded! Indexing in background...", "#4ade80");
        loadDocuments();

        // Poll status every 5 seconds
        const poll = setInterval(async () => {
            const statusRes = await fetch(`${API_URL}/documents/${data.id}`, {
                headers: { "Authorization": `Bearer ${token}` }
            });
            const statusData = await statusRes.json();
            if (statusData.status === "indexed") {
                setStatus("✅ Document indexed and ready!", "#4ade80");
                clearInterval(poll);
                loadDocuments();
            } else if (statusData.status === "failed") {
                setStatus("❌ Indexing failed", "#ef4444");
                clearInterval(poll);
            }
        }, 5000);

    } catch (err) {
        setStatus(err.message, "#ef4444");
    }
}

async function deleteDocument(event, docId) {
    event.stopPropagation();
    if (!confirm("Delete this document?")) return;

    try {
        await fetch(`${API_URL}/documents/${docId}`, {
            method: "DELETE",
            headers: { "Authorization": `Bearer ${token}` }
        });
        loadDocuments();
    } catch (err) {
        alert("Failed to delete document");
    }
}

// ── Chat ──────────────────────────────────────────────────────────────────────
async function openChat(docId, filename, status) {
    if (status !== "indexed") {
        alert("Document is still being indexed. Please wait.");
        return;
    }

    currentDocId = docId;
    document.getElementById("chat-doc-name").textContent = `📄 ${filename}`;
    document.getElementById("chat-messages").innerHTML = `
        <div class="message assistant">
            👋 Hi! Ask me anything about <strong>${filename}</strong>.
        </div>
    `;

    try {
        const res = await fetch(`${API_URL}/chat/sessions/${docId}`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${token}` }
        });
        const data = await res.json();
        currentSessionId = data.id;
        showSection("chat-section");
    } catch (err) {
        alert("Failed to create chat session");
    }
}

async function sendMessage() {
    const input = document.getElementById("chat-input");
    const question = input.value.trim();
    if (!question || !currentSessionId) return;

    input.value = "";

    // Add user message
    addMessage(question, "user");

    // Add streaming assistant message
    const msgEl = addMessage("", "assistant streaming");

    try {
        const res = await fetch(`${API_URL}/chat/ask/${currentSessionId}`, {
            method: "POST",
            headers: {
                "Authorization": `Bearer ${token}`,
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ question })
        });

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let fullText = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value);
            fullText += chunk;
            msgEl.textContent = fullText;
            msgEl.scrollIntoView({ behavior: "smooth" });
        }

        msgEl.classList.remove("streaming");

    } catch (err) {
        msgEl.textContent = "❌ Failed to get answer. Please try again.";
        msgEl.classList.remove("streaming");
    }
}

function addMessage(text, className) {
    const container = document.getElementById("chat-messages");
    const msg = document.createElement("div");
    msg.className = `message ${className}`;
    msg.textContent = text;
    container.appendChild(msg);
    msg.scrollIntoView({ behavior: "smooth" });
    return msg;
}

function backToDashboard() {
    currentSessionId = null;
    currentDocId = null;
    showSection("dashboard-section");
    loadDocuments();
}