const API_URL = "https://askdocs.duckdns.org/api";
let token = localStorage.getItem("token");
let currentSessionId = null;
let currentDocId = null;
let isStreaming = false;

// ── Init ──────────────────────────────────────────────────────────────────────
window.addEventListener("DOMContentLoaded", () => {
    initTabs();
    initUpload();
    initPasswordToggles();
    initAuthForms();
    initChatInput();
    initNavButtons();

    if (token) {
        showSection("dashboard-section");
        loadDocuments();
        displayUserInfo();
    } else {
        showSection("auth-section");
    }
});

// ── Section Management ────────────────────────────────────────────────────────
function showSection(id) {
    document.querySelectorAll(".section").forEach(s => {
        s.classList.remove("active");
    });
    // Small delay so animation triggers properly
    requestAnimationFrame(() => {
        document.getElementById(id).classList.add("active");
    });
}

// ── Toast Notifications ──────────────────────────────────────────────────────
function showToast(message, type = "info", duration = 4000) {
    const container = document.getElementById("toast-container");
    const icons = { success: "✅", error: "❌", warning: "⚠️", info: "ℹ️" };

    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span class="toast-icon">${icons[type]}</span>
        <span>${message}</span>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.add("leaving");
        toast.addEventListener("animationend", () => toast.remove());
    }, duration);
}

// ── Tabs ──────────────────────────────────────────────────────────────────────
function initTabs() {
    const tabs = document.querySelectorAll(".tab");
    tabs.forEach(tab => {
        tab.addEventListener("click", () => {
            const target = tab.dataset.tab;

            // Update tab active states
            tabs.forEach(t => t.classList.remove("active"));
            tab.classList.add("active");

            // Move slider
            const slider = document.getElementById("tab-slider");
            slider.classList.toggle("register", target === "register");

            // Toggle forms
            document.getElementById("login-form").classList.toggle("active", target === "login");
            document.getElementById("register-form").classList.toggle("active", target === "register");

            // Clear error
            document.getElementById("auth-error").textContent = "";
        });
    });
}

// ── Password Toggles ─────────────────────────────────────────────────────────
function initPasswordToggles() {
    document.querySelectorAll(".password-toggle").forEach(btn => {
        btn.addEventListener("click", () => {
            const input = document.getElementById(btn.dataset.target);
            const isPassword = input.type === "password";
            input.type = isPassword ? "text" : "password";
            btn.textContent = isPassword ? "🙈" : "👁️";
        });
    });
}

// ── Auth Forms ───────────────────────────────────────────────────────────────
function initAuthForms() {
    document.getElementById("login-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        await login();
    });

    document.getElementById("register-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        await register();
    });
}

function setButtonLoading(btnId, loading) {
    const btn = document.getElementById(btnId);
    btn.classList.toggle("loading", loading);
    btn.disabled = loading;
}

function setAuthError(msg) {
    const el = document.getElementById("auth-error");
    el.textContent = msg;
}

async function register() {
    const email = document.getElementById("reg-email").value.trim();
    const password = document.getElementById("reg-password").value;

    if (!email || !password) {
        setAuthError("Please fill in all fields");
        return;
    }

    setButtonLoading("register-btn", true);
    setAuthError("");

    try {
        const res = await fetch(`${API_URL}/auth/register`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Registration failed");

        token = data.access_token;
        localStorage.setItem("token", token);
        showToast("Account created successfully!", "success");
        showSection("dashboard-section");
        loadDocuments();
        displayUserInfo();
    } catch (err) {
        setAuthError(err.message);
    } finally {
        setButtonLoading("register-btn", false);
    }
}

async function login() {
    const email = document.getElementById("login-email").value.trim();
    const password = document.getElementById("login-password").value;

    if (!email || !password) {
        setAuthError("Please fill in all fields");
        return;
    }

    setButtonLoading("login-btn", true);
    setAuthError("");

    try {
        const res = await fetch(`${API_URL}/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: `username=${encodeURIComponent(email)}&password=${encodeURIComponent(password)}`
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Login failed");

        token = data.access_token;
        localStorage.setItem("token", token);
        showToast("Welcome back!", "success");
        showSection("dashboard-section");
        loadDocuments();
        displayUserInfo();
    } catch (err) {
        setAuthError(err.message);
    } finally {
        setButtonLoading("login-btn", false);
    }
}

function logout() {
    localStorage.removeItem("token");
    token = null;
    currentSessionId = null;
    currentDocId = null;
    showSection("auth-section");
    showToast("Logged out", "info");
}

function displayUserInfo() {
    try {
        // Decode JWT payload to get email
        const payload = JSON.parse(atob(token.split(".")[1]));
        const email = payload.email || "user";
        document.getElementById("user-email-display").textContent = email;
        document.getElementById("user-avatar").textContent = email.charAt(0).toUpperCase();
    } catch {
        document.getElementById("user-email-display").textContent = "user";
    }
}

// ── Navigation Buttons ───────────────────────────────────────────────────────
function initNavButtons() {
    document.getElementById("logout-btn").addEventListener("click", logout);
    document.getElementById("chat-logout-btn").addEventListener("click", logout);
    document.getElementById("back-btn").addEventListener("click", backToDashboard);
}

// ── Upload ────────────────────────────────────────────────────────────────────
function initUpload() {
    const area = document.getElementById("upload-area");
    const input = document.getElementById("file-input");

    // Click to upload
    area.addEventListener("click", () => input.click());
    input.addEventListener("change", () => {
        if (input.files[0]) uploadFile(input.files[0]);
    });

    // Drag and drop
    area.addEventListener("dragover", (e) => {
        e.preventDefault();
        area.classList.add("drag-over");
    });

    area.addEventListener("dragleave", (e) => {
        e.preventDefault();
        area.classList.remove("drag-over");
    });

    area.addEventListener("drop", (e) => {
        e.preventDefault();
        area.classList.remove("drag-over");
        const file = e.dataTransfer.files[0];
        if (file) {
            if (!file.name.endsWith(".pdf")) {
                showToast("Only PDF files are supported", "error");
                return;
            }
            uploadFile(file);
        }
    });
}

function setUploadStatus(text, type) {
    const status = document.getElementById("upload-status");
    const icon = document.getElementById("upload-status-icon");
    const textEl = document.getElementById("upload-status-text");

    const icons = { success: "✅", warning: "⏳", error: "❌" };

    status.className = `upload-status visible ${type}`;
    icon.textContent = icons[type] || "";
    textEl.textContent = text;
}

function hideUploadStatus() {
    document.getElementById("upload-status").classList.remove("visible");
}

async function uploadFile(file) {
    setUploadStatus("Uploading...", "warning");

    const formData = new FormData();
    formData.append("file", file);

    try {
        const res = await fetch(`${API_URL}/documents/upload`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${token}` },
            body: formData
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Upload failed");

        setUploadStatus("Uploaded! Indexing in background...", "success");
        showToast(`"${file.name}" uploaded successfully`, "success");
        loadDocuments();

        // Poll indexing status
        const poll = setInterval(async () => {
            try {
                const statusRes = await fetch(`${API_URL}/documents/${data.id}`, {
                    headers: { "Authorization": `Bearer ${token}` }
                });
                const statusData = await statusRes.json();
                if (statusData.status === "indexed") {
                    setUploadStatus("Document indexed and ready!", "success");
                    showToast(`"${file.name}" is ready to chat!`, "success");
                    clearInterval(poll);
                    loadDocuments();
                    setTimeout(hideUploadStatus, 5000);
                } else if (statusData.status === "failed") {
                    setUploadStatus("Indexing failed", "error");
                    showToast("Document indexing failed", "error");
                    clearInterval(poll);
                }
            } catch {
                clearInterval(poll);
            }
        }, 5000);

    } catch (err) {
        setUploadStatus(err.message, "error");
        showToast(err.message, "error");
    }

    // Reset file input
    document.getElementById("file-input").value = "";
}

// ── Documents ─────────────────────────────────────────────────────────────────
async function loadDocuments() {
    const container = document.getElementById("documents-list");

    try {
        const res = await fetch(`${API_URL}/documents/`, {
            headers: { "Authorization": `Bearer ${token}` }
        });
        if (!res.ok) throw new Error("Failed to load");
        const docs = await res.json();
        renderDocuments(docs);
    } catch {
        container.innerHTML = `
            <div class="documents-empty">
                <span class="empty-icon">⚠️</span>
                <p>Failed to load documents.<br>Please try again.</p>
            </div>
        `;
    }
}

function renderDocuments(docs) {
    const container = document.getElementById("documents-list");

    if (docs.length === 0) {
        container.innerHTML = `
            <div class="documents-empty">
                <span class="empty-icon">📂</span>
                <p>No documents yet.<br>Upload a PDF to get started!</p>
            </div>
        `;
        return;
    }

    container.innerHTML = docs.map((doc, i) => {
        const statusDot = doc.status === "processing"
            ? '<span class="status-dot"></span>'
            : '';
        const statusLabel = doc.status === "indexed" ? "✓ Ready"
            : doc.status === "processing" ? "Indexing"
            : "Failed";

        return `
            <div class="doc-card" onclick="openChat(${doc.id}, '${escapeHtml(doc.filename)}', '${doc.status}')"
                 style="animation-delay: ${i * 60}ms" title="Click to chat with this document">
                <span class="doc-icon">📄</span>
                <div class="doc-info">
                    <h4>${escapeHtml(doc.filename)}</h4>
                    <span class="doc-status ${doc.status}">${statusDot}${statusLabel}</span>
                </div>
                <button class="btn-icon" onclick="confirmDelete(event, ${doc.id}, '${escapeHtml(doc.filename)}')" title="Delete document">
                    🗑️
                </button>
            </div>
        `;
    }).join("");
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

// ── Delete Confirmation ──────────────────────────────────────────────────────
function confirmDelete(event, docId, filename) {
    event.stopPropagation();

    const overlay = document.createElement("div");
    overlay.className = "modal-overlay";
    overlay.innerHTML = `
        <div class="modal-box">
            <h3>Delete Document</h3>
            <p>Are you sure you want to delete "<strong>${filename}</strong>"? This action cannot be undone.</p>
            <div class="modal-actions">
                <button class="btn-secondary" id="modal-cancel">Cancel</button>
                <button class="btn-danger" id="modal-confirm">Delete</button>
            </div>
        </div>
    `;

    document.body.appendChild(overlay);

    overlay.querySelector("#modal-cancel").addEventListener("click", () => overlay.remove());
    overlay.addEventListener("click", (e) => {
        if (e.target === overlay) overlay.remove();
    });
    overlay.querySelector("#modal-confirm").addEventListener("click", async () => {
        overlay.remove();
        await deleteDocument(docId, filename);
    });
}

async function deleteDocument(docId, filename) {
    try {
        const res = await fetch(`${API_URL}/documents/${docId}`, {
            method: "DELETE",
            headers: { "Authorization": `Bearer ${token}` }
        });
        if (!res.ok) throw new Error("Delete failed");
        showToast(`"${filename}" deleted`, "info");
        loadDocuments();
    } catch {
        showToast("Failed to delete document", "error");
    }
}

// ── Chat ──────────────────────────────────────────────────────────────────────
function initChatInput() {
    const input = document.getElementById("chat-input");
    const sendBtn = document.getElementById("chat-send-btn");

    // Enable/disable send button based on input
    input.addEventListener("input", () => {
        sendBtn.disabled = !input.value.trim() || isStreaming;
    });

    // Enter to send
    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey && !e.ctrlKey) {
            e.preventDefault();
            if (input.value.trim() && !isStreaming) sendMessage();
        }
    });

    sendBtn.addEventListener("click", () => {
        if (input.value.trim() && !isStreaming) sendMessage();
    });
}

async function openChat(docId, filename, status) {
    if (status !== "indexed") {
        showToast("This document is still being indexed. Please wait.", "warning");
        return;
    }

    currentDocId = docId;
    document.getElementById("chat-doc-name").textContent = filename;
    document.getElementById("chat-messages").innerHTML = `
        <div class="message assistant">
            👋 Hi! Ask me anything about <strong>${escapeHtml(filename)}</strong>. Every answer will include page citations so you can verify the information.
        </div>
    `;

    try {
        const res = await fetch(`${API_URL}/chat/sessions/${docId}`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${token}` }
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Failed to create session");
        currentSessionId = data.id;
        showSection("chat-section");

        // Focus the input
        setTimeout(() => document.getElementById("chat-input").focus(), 300);
    } catch (err) {
        showToast("Failed to create chat session", "error");
    }
}

async function sendMessage() {
    const input = document.getElementById("chat-input");
    const sendBtn = document.getElementById("chat-send-btn");
    const question = input.value.trim();
    if (!question || !currentSessionId || isStreaming) return;

    input.value = "";
    sendBtn.disabled = true;
    isStreaming = true;

    // Add user message
    addMessage(question, "user");

    // Add typing indicator
    const typingEl = addTypingIndicator();

    try {
        const res = await fetch(`${API_URL}/chat/ask/${currentSessionId}`, {
            method: "POST",
            headers: {
                "Authorization": `Bearer ${token}`,
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ question })
        });

        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || "Request failed");
        }

        // Remove typing indicator, add assistant message
        typingEl.remove();
        const msgEl = addMessage("", "assistant");

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let fullText = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value);
            fullText += chunk;
            msgEl.innerHTML = renderMarkdown(fullText);
            scrollToBottom();
        }

        // Final render with full markdown
        msgEl.innerHTML = renderMarkdown(fullText);

    } catch (err) {
        typingEl.remove();
        const errorMsg = addMessage("", "assistant");
        errorMsg.innerHTML = `<span style="color: var(--error)">❌ ${escapeHtml(err.message || "Failed to get answer. Please try again.")}</span>`;
    } finally {
        isStreaming = false;
        sendBtn.disabled = !input.value.trim();
        input.focus();
    }
}

function addMessage(text, className) {
    const container = document.getElementById("chat-messages");
    const msg = document.createElement("div");
    msg.className = `message ${className}`;

    if (className.includes("user")) {
        msg.textContent = text;
    } else {
        msg.innerHTML = text ? renderMarkdown(text) : text;
    }

    container.appendChild(msg);
    scrollToBottom();
    return msg;
}

function addTypingIndicator() {
    const container = document.getElementById("chat-messages");
    const indicator = document.createElement("div");
    indicator.className = "typing-indicator";
    indicator.innerHTML = `
        <span class="typing-dot"></span>
        <span class="typing-dot"></span>
        <span class="typing-dot"></span>
    `;
    container.appendChild(indicator);
    scrollToBottom();
    return indicator;
}

function scrollToBottom() {
    const container = document.getElementById("chat-messages");
    container.scrollTo({
        top: container.scrollHeight,
        behavior: "smooth"
    });
}

// ── Markdown Rendering ───────────────────────────────────────────────────────
function renderMarkdown(text) {
    let html = escapeHtml(text);

    // Code blocks (```...```)
    html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
        return `<pre><code>${code.trim()}</code></pre>`;
    });

    // Inline code (`...`)
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

    // Bold (**...**)
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

    // Italic (*...*)
    html = html.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '<em>$1</em>');

    // Citations [Page N] or [Page N-M]
    html = html.replace(/\[Page\s+(\d+(?:\s*[-–]\s*\d+)?)\]/gi,
        '<span class="citation">📄 Page $1</span>');

    // Line breaks
    html = html.replace(/\n/g, '<br>');

    return html;
}

// ── Back to Dashboard ────────────────────────────────────────────────────────
function backToDashboard() {
    currentSessionId = null;
    currentDocId = null;
    showSection("dashboard-section");
    loadDocuments();
}