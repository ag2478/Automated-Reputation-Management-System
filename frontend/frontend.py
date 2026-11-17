# ARMS front end: serves the pages and sends register/login forms to the back end through RabbitMQ.
# nginx (port 7812) forwards requests here (port 8080).
# Milestone 4: runs on 2 front-end nodes. It uses hostnames only and fails over across the RabbitMQ cluster.

import json
import os
import socket
import uuid
import pika
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# RabbitMQ cluster nodes (same list as rmq_agent.py); the first one that answers is used.
CLUSTER_HOSTS = ["ag2478-dev", "ag2478-test", "ag2478-prod", "aks55-dev", "ojo-dev", "jxo-dev"]
RABBIT_USER = os.getenv("RABBITMQ_USER", "repo_user")
RABBIT_PASS = os.getenv("RABBITMQ_PASS", "repo_pass")
BIND = os.getenv("FRONTEND_BIND", "0.0.0.0")   # 0.0.0.0 so nginx on the other front-end node can reach it
PORT = int(os.getenv("FRONTEND_PORT", "8080"))
NODE = socket.gethostname()                      # shown in the footer, proves which node served the page

STYLE = """<style>
*{box-sizing:border-box}body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#f4f6fb;color:#1c2333}
a{color:#2f5bea;text-decoration:none}
nav{display:flex;justify-content:space-between;align-items:center;padding:16px 32px;background:#fff;border-bottom:1px solid #e3e7f0}
.logo{font-weight:800;font-size:20px;color:#1c2333}.logo span{color:#2f5bea}
nav .links a{margin-left:20px;font-weight:600}
.btn{display:inline-block;background:#2f5bea;color:#fff;border:0;border-radius:8px;padding:12px 22px;font-weight:700;font-size:15px;cursor:pointer}
.btn.ghost{background:#fff;color:#2f5bea;border:1px solid #2f5bea}
.hero{max-width:960px;margin:0 auto;padding:72px 24px 40px;text-align:center}
.hero h1{font-size:42px;margin:0 0 16px}.hero p{font-size:18px;color:#4a5470;max-width:640px;margin:0 auto 28px}
.cards{max-width:960px;margin:0 auto;padding:0 24px 56px;display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:20px}
.card{background:#fff;border:1px solid #e3e7f0;border-radius:12px;padding:24px}
.card h3{margin:0 0 8px}.card p{margin:0;color:#4a5470}
.box{max-width:420px;margin:56px auto;background:#fff;border:1px solid #e3e7f0;border-radius:12px;padding:32px}
.box h1{margin:0 0 20px;font-size:26px}
label{display:block;font-weight:600;font-size:14px;margin:14px 0 6px}
input{width:100%;padding:11px 12px;border:1px solid #cdd3e1;border-radius:8px;font-size:15px}
.box .btn{width:100%;margin-top:22px}
#msg{min-height:22px;margin:14px 0 0;font-weight:600}.err{color:#c62828}.ok{color:#2e7d32}
.small{font-size:14px;color:#4a5470;text-align:center;margin-top:16px}
footer{text-align:center;color:#8a93ab;font-size:13px;padding:24px}
</style>"""

NAV = """<nav><a class="logo" href="/">AR<span>MS</span></a><div class="links">
<a href="/">Home</a><a href="/login">Log in</a><a class="btn" href="/register">Get started</a></div></nav>"""

FORM_SCRIPT = """<script>
form.onsubmit = async (e) => {
  e.preventDefault();
  msg.className = ""; msg.textContent = "Working...";
  const data = Object.fromEntries(new FormData(form));
  try {
    const answer = await (await fetch("/api/" + form.dataset.action, {method: "POST", body: JSON.stringify(data)})).json();
    if (answer.ok && form.dataset.action == "login") { sessionStorage.username = data.username; location = "/welcome"; return; }
    msg.className = answer.ok ? "ok" : "err"; msg.textContent = answer.message;
  } catch (err) { msg.className = "err"; msg.textContent = "Could not reach the server"; }
};</script>"""


def page(title, body):
    return (f"<!DOCTYPE html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{title} | ARMS</title>{STYLE}</head><body>{NAV}{body}"
            f"<footer>ARMS: Automated Reputation Management System · IT 490 Group 8 · served by front-end node <b>{NODE}</b></footer>"
            f"</body></html>")


PAGES = {
    "/": page("Home", """
<section class="hero">
  <h1>Get more Google reviews, automatically.</h1>
  <p>ARMS emails your customers a personal review link and follows up for you: up to 3 friendly reminders, 2 weeks apart, until they leave a review.</p>
  <a class="btn" href="/register">Create your account</a> &nbsp; <a class="btn ghost" href="/login">Log in</a>
</section>
<section class="cards">
  <div class="card"><h3>1. Add a customer</h3><p>Enter a customer's name and email after a visit or sale.</p></div>
  <div class="card"><h3>2. ARMS reaches out</h3><p>They get your Google review link by email, with automatic follow-ups.</p></div>
  <div class="card"><h3>3. Track your reviews</h3><p>See who was contacted and who already left a review.</p></div>
</section>
<p class="small">Hello World!!!</p>"""),

    "/register": page("Register", """
<div class="box"><h1>Create your account</h1>
<form id="form" data-action="register">
  <label>Username</label><input name="username" required>
  <label>Email</label><input name="email" type="email" required>
  <label>Password</label><input name="password" type="password" required minlength="6">
  <button class="btn">Register</button></form>
<p id="msg"></p><p class="small">Already have an account? <a href="/login">Log in</a></p></div>""" + FORM_SCRIPT),

    "/login": page("Log in", """
<div class="box"><h1>Log in</h1>
<form id="form" data-action="login">
  <label>Username</label><input name="username" required>
  <label>Password</label><input name="password" type="password" required>
  <button class="btn">Log in</button></form>
<p id="msg"></p><p class="small">New to ARMS? <a href="/register">Create an account</a></p></div>""" + FORM_SCRIPT),

    "/welcome": page("Dashboard", """
<div class="box" style="max-width:640px"><h1 id="hi"></h1>
<p>You're logged in to ARMS. Customer review requests and reminder tracking are coming in the final release.</p>
<a class="btn ghost" href="/login" onclick="sessionStorage.clear()">Log out</a></div>
<script>if (!sessionStorage.username) location = "/login"; hi.textContent = "Welcome, " + sessionStorage.username;</script>"""),
}


def connect():
    # try each RabbitMQ cluster node until one answers
    for host in CLUSTER_HOSTS:
        try:
            return pika.BlockingConnection(pika.ConnectionParameters(
                host=host, credentials=pika.PlainCredentials(RABBIT_USER, RABBIT_PASS),
                socket_timeout=3, blocked_connection_timeout=5))
        except Exception:
            continue
    raise ConnectionError("no RabbitMQ node reachable")


def ask_backend(msg):
    # put the message on Olu's "fe_to_be_queue" and wait (max 10s) for the back end's answer
    connection = connect()
    channel = connection.channel()
    reply_queue = channel.queue_declare(queue="", exclusive=True).method.queue
    answers = []
    channel.basic_consume(queue=reply_queue, auto_ack=True,
                          on_message_callback=lambda ch, m, p, body: answers.append(json.loads(body)))
    channel.basic_publish(exchange="", routing_key="fe_to_be_queue", body=json.dumps(msg),
                          properties=pika.BasicProperties(reply_to=reply_queue, correlation_id=str(uuid.uuid4()), expiration="10000"))
    for _ in range(20):
        connection.process_data_events(time_limit=0.5)
        if answers:
            break
    connection.close()
    if not answers:
        return {"ok": False, "message": "The back end did not answer"}
    # Olu's back end answers {"status": "success" or "error", "message": ...}
    ok = answers[0].get("status") == "success"
    done = "Account created! You can log in now." if msg["action"] == "register" else "Logged in"
    return {"ok": ok, "message": answers[0].get("message") or (done if ok else "Something went wrong")}


class Handler(BaseHTTPRequestHandler):
    def send(self, text, status=200, kind="text/html; charset=utf-8"):
        body = text.encode()
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):    # open a page
        if self.path == "/health":   # used to check each front-end node
            return self.send(json.dumps({"node": NODE, "status": "up"}), kind="application/json")
        html = PAGES.get(self.path.split("?")[0])
        if html is None:
            return self.send(page("Not found", '<div class="box"><h1>Page not found</h1><a href="/">Go home</a></div>'), 404)
        self.send(html)

    def do_POST(self):   # form submitted
        action = self.path.split("/")[-1]
        if action not in ("register", "login"):
            return self.send(json.dumps({"ok": False, "message": "Unknown action"}), 404, "application/json")
        try:
            msg = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            msg["action"] = action
            self.send(json.dumps(ask_backend(msg)), kind="application/json")
        except Exception:
            self.send(json.dumps({"ok": False, "message": "Can't reach RabbitMQ"}), kind="application/json")


print(f"ARMS front end on {NODE}, listening on {BIND}:{PORT}")
ThreadingHTTPServer((BIND, PORT), Handler).serve_forever()
