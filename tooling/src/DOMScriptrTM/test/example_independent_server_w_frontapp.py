"""A deliberately framework-ordinary Flask app used by DOMScriptr E2E tests.

Flask is a test/example dependency only. The DOMScriptr runtime never imports it.
"""

from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
from threading import Lock, Thread
from typing import Iterator

from flask import Flask, jsonify, make_response, request
from werkzeug.serving import make_server


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>DOMScriptr fixture</title>
  <style>
    body { font-family: sans-serif; max-width: 48rem; margin: 2rem auto; }
    #messages { min-height: 2rem; }
  </style>
</head>
<body>
  <h1>DOMScriptr fixture</h1>
  <div id="connection">connecting</div>
  <div id="whoami">anonymous</div>

  <label>Username <input id="username" aria-label="Username"></label>
  <button id="login">Login</button>

  <label>Message <input id="message" aria-label="Message"></label>
  <button id="send">Send</button>
  <button id="increment">Increment</button>
  <output id="counter">0</output>

  <ul id="messages"></ul>
  <div id="delayed-slot"></div>

<script>
window.app = {
  connected: false,
  errors: [],
  user: "anonymous",
  messages: [],
  count: 0,
  delayedClicks: 0,
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: {"Content-Type": "application/json", ...(options.headers || {})},
    ...options,
  });
  if (!response.ok) throw new Error(`${response.status} ${path}`);
  return await response.json();
}

function renderMessages(items) {
  window.app.messages = items;
  const list = document.getElementById("messages");
  list.replaceChildren(...items.map(item => {
    const li = document.createElement("li");
    li.className = "message";
    li.dataset.user = item.user;
    li.textContent = `${item.user}: ${item.text}`;
    return li;
  }));
}

async function refreshIdentity() {
  const me = await api("/api/me");
  window.app.user = me.user;
  window.app.count = me.count;
  document.getElementById("whoami").textContent = me.user;
  document.getElementById("counter").textContent = String(me.count);
}

async function refreshMessages() {
  renderMessages(await api("/api/messages"));
}

async function refreshAll() {
  await Promise.all([refreshIdentity(), refreshMessages()]);
  window.app.connected = true;
  document.getElementById("connection").textContent = "connected";
}

function guarded(fn) {
  return async (...args) => {
    try { return await fn(...args); }
    catch (error) {
      window.app.errors.push(String(error));
      throw error;
    }
  };
}

document.getElementById("login").addEventListener("click", guarded(async () => {
  const name = document.getElementById("username").value;
  await api("/api/login", {method: "POST", body: JSON.stringify({name})});
  await refreshIdentity();
}));

document.getElementById("send").addEventListener("click", guarded(async () => {
  const text = document.getElementById("message").value;
  await api("/api/messages", {method: "POST", body: JSON.stringify({text})});
  document.getElementById("message").value = "";
  await refreshMessages();
}));

document.getElementById("increment").addEventListener("click", guarded(async () => {
  const state = await api("/api/count", {method: "POST", body: "{}"});
  window.app.count = state.count;
  document.getElementById("counter").textContent = String(state.count);
}));

setTimeout(() => {
  const button = document.createElement("button");
  button.id = "delayed-action";
  button.textContent = "Delayed Action";
  button.addEventListener("click", () => { window.app.delayedClicks += 1; });
  document.getElementById("delayed-slot").appendChild(button);
}, 80);

refreshAll().catch(error => window.app.errors.push(String(error)));
setInterval(() => refreshMessages().catch(error => window.app.errors.push(String(error))), 25);
</script>
</body>
</html>
"""

SETTINGS_HTML = r"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Settings</title></head>
<body>
  <h1>Settings</h1>
  <div id="settings-user"></div>
  <button id="save">Save</button>
<script>
window.settingsSaved = 0;
fetch("/api/me", {credentials: "same-origin"})
  .then(r => r.json())
  .then(me => { document.getElementById("settings-user").textContent = me.user; });
document.getElementById("save").addEventListener("click", () => {
  window.settingsSaved += 1;
});
</script>
</body>
</html>
"""


def create_app() -> Flask:
    app = Flask(__name__)
    lock = Lock()
    messages: list[dict[str, str]] = []
    counts: defaultdict[str, int] = defaultdict(int)

    def current_user() -> str:
        return request.cookies.get("domscriptr-user", "anonymous")

    @app.get("/")
    def index():
        return INDEX_HTML

    @app.get("/settings")
    def settings():
        return SETTINGS_HTML

    @app.get("/api/me")
    def me():
        user = current_user()
        with lock:
            count = counts[user]
        return jsonify(user=user, count=count)

    @app.post("/api/login")
    def login():
        body = request.get_json(force=True)
        name = str(body.get("name", "")).strip()
        if not name:
            return jsonify(error="name required"), 400
        response = make_response(jsonify(user=name))
        response.set_cookie("domscriptr-user", name, samesite="Lax")
        return response

    @app.route("/api/messages", methods=["GET", "POST"])
    def api_messages():
        if request.method == "POST":
            body = request.get_json(force=True)
            text = str(body.get("text", ""))
            with lock:
                messages.append({"user": current_user(), "text": text})
        with lock:
            return jsonify(list(messages))

    @app.post("/api/count")
    def increment_count():
        user = current_user()
        with lock:
            counts[user] += 1
            count = counts[user]
        return jsonify(user=user, count=count)

    return app


@contextmanager
def flask_server() -> Iterator[dict[str, str]]:
    """Start Flask/Werkzeug on an OS-assigned port and yield only when bound."""
    app = create_app()
    httpd = make_server("127.0.0.1", 0, app, threaded=True)
    thread = Thread(target=httpd.serve_forever, name="domscriptr-flask", daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{httpd.server_port}"
    try:
        yield {"web": url}
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)
        if thread.is_alive():
            raise RuntimeError("Flask test server thread did not stop")
