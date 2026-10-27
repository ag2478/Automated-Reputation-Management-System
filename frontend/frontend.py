# ARMS front end: shows the pages, sends forms to the back end through RabbitMQ.
# nginx (port 7812) forwards everything here (port 8080).

import json, uuid, pika
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RABBIT_HOST = "10.211.59.183"   # Andres's RabbitMQ

# the pages; register + login send their form to /api/register or /api/login
FORM_SCRIPT = """<p id="msg"></p><script>
form.onsubmit = async (e) => {
  e.preventDefault();
  const data = Object.fromEntries(new FormData(form));
  const answer = await (await fetch("/api/" + form.dataset.action, {method: "POST", body: JSON.stringify(data)})).json();
  if (answer.ok && form.dataset.action == "login") { sessionStorage.username = data.username; location = "/welcome"; }
  else msg.textContent = answer.message;
};</script>"""

PAGES = {
    "/": '<h1>Hello World!!!</h1><a href="/register">Register</a> | <a href="/login">Login</a>',
    "/register": '<h1>Register</h1><form id="form" data-action="register">'
                 'Username <input name="username" required><br>Email <input name="email" type="email" required><br>'
                 'Password <input name="password" type="password" required><br><button>Register</button></form>'
                 '<a href="/login">Login</a>' + FORM_SCRIPT,
    "/login": '<h1>Login</h1><form id="form" data-action="login">'
              'Username <input name="username" required><br>Password <input name="password" type="password" required><br>'
              '<button>Login</button></form><a href="/register">Register</a>' + FORM_SCRIPT,
    "/welcome": '<h1 id="hi"></h1><a href="/login" onclick="sessionStorage.clear()">Log out</a><script>'
                'if (!sessionStorage.username) location = "/login"; hi.textContent = "Welcome, " + sessionStorage.username;</script>',
}


def ask_backend(msg):
    # put the message on Olu's "fe_to_be_queue" and wait (max 10s) for the back end's answer
    connection = pika.BlockingConnection(pika.ConnectionParameters(RABBIT_HOST, credentials=pika.PlainCredentials("repo_user", "repo_pass")))
    channel = connection.channel()
    reply_queue = channel.queue_declare(queue="", exclusive=True).method.queue
    answers = []
    channel.basic_consume(queue=reply_queue, auto_ack=True, on_message_callback=lambda ch, m, p, body: answers.append(json.loads(body)))
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
    def send(self, text):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(text.encode())

    def do_GET(self):    # open a page
        self.send(PAGES.get(self.path, "Page not found"))

    def do_POST(self):   # form submitted
        msg = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        msg["action"] = self.path.split("/")[-1]      # "register" or "login"
        try:
            self.send(json.dumps(ask_backend(msg)))
        except Exception:
            self.send(json.dumps({"ok": False, "message": "Can't reach RabbitMQ"}))


ThreadingHTTPServer(("127.0.0.1", 8080), Handler).serve_forever()
