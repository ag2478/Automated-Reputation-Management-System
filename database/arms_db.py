"""arms_db.py - database helper for ARMS (register, login, logging).

Back-end usage:
    from arms_db import register_user, login_user, log_event

    result = register_user("alice", "alice@example.com", "a-long-password",
                           business_name="Alice's Cafe")
    result = login_user("alice", "a-long-password")   # username OR email works

Every function returns a plain dict, e.g. {"success": True, "message": "..."},
so it can be sent straight back through RabbitMQ as JSON.

Connection settings come from environment variables. Never hard-code the password.
    DB_PASSWORD  (required)
    DB_HOST      (default 10.211.59.206 = jxo-dev over ZeroTier)
    DB_PORT      (default 3306)
    DB_USER      (default arms_app)
    DB_NAME      (default reputation_app)

Requires: pymysql   (sudo apt install -y python3-pymysql)
"""

import hashlib
import hmac
import os
import secrets

import pymysql

ITERATIONS = 200_000


def _connect():
    return pymysql.connect(
        host=os.environ.get("DB_HOST", "10.211.59.206"),
        port=int(os.environ.get("DB_PORT", "3306")),
        user=os.environ.get("DB_USER", "arms_app"),
        password=os.environ["DB_PASSWORD"],
        database=os.environ.get("DB_NAME", "reputation_app"),
        connect_timeout=5,
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )


# ---------- passwords: only a salted hash is ever stored ----------

def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), ITERATIONS
    ).hex()
    return f"pbkdf2_sha256${ITERATIONS}${salt}${digest}"


def verify_password(password, stored):
    try:
        _, iterations, salt, digest = stored.split("$")
        check = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt.encode(), int(iterations)
        ).hex()
        return hmac.compare_digest(check, digest)
    except ValueError:
        return False


# ---------- centralized logging ----------

def log_event(source, level, message):
    """Write one row to the logs table. Never raises, so logging can't break the app."""
    try:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO logs (source, level, message) VALUES (%s, %s, %s)",
                    (source, level, message),
                )
        finally:
            conn.close()
        return True
    except Exception:
        return False


# ---------- registration ----------

def register_user(username, email, password, business_name=None):
    username = (username or "").strip()
    email = (email or "").strip().lower()

    if not username or not email or not password:
        return {"success": False, "message": "Username, email and password are required."}
    if "@" not in email:
        return {"success": False, "message": "Please enter a valid email address."}
    if len(password) < 8:
        return {"success": False, "message": "Password must be at least 8 characters."}

    try:
        conn = _connect()
    except Exception as exc:
        return {"success": False, "message": f"Database unavailable: {exc}"}

    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (username, email, password_hash, business_name) "
                "VALUES (%s, %s, %s, %s)",
                (username, email, hash_password(password), business_name),
            )
            user_id = cur.lastrowid
        log_event("database", "INFO", f"Registered user '{username}' (id {user_id})")
        return {"success": True, "message": "Registration successful.", "user_id": user_id}
    except pymysql.err.IntegrityError as exc:
        text = str(exc).lower()
        field = "email" if "email" in text else "username"
        log_event("database", "WARN", f"Registration rejected: {field} already exists")
        return {"success": False, "message": f"That {field} is already registered."}
    except Exception as exc:
        log_event("database", "ERROR", f"Registration failed: {exc}")
        return {"success": False, "message": "Registration failed."}
    finally:
        conn.close()


# ---------- login ----------

def login_user(identifier, password):
    """identifier can be the username or the email."""
    identifier = (identifier or "").strip()
    if not identifier or not password:
        return {"success": False, "message": "Username and password are required."}

    try:
        conn = _connect()
    except Exception as exc:
        return {"success": False, "message": f"Database unavailable: {exc}"}

    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id, username, email, business_name, password_hash "
                "FROM users WHERE username = %s OR email = %s",
                (identifier, identifier.lower()),
            )
            row = cur.fetchone()

        if row and verify_password(password, row["password_hash"]):
            log_event("database", "INFO", f"Login OK for '{row['username']}'")
            return {
                "success": True,
                "message": "Login successful.",
                "user": {
                    "user_id": row["user_id"],
                    "username": row["username"],
                    "email": row["email"],
                    "business_name": row["business_name"],
                },
            }

        log_event("database", "WARN", f"Login failed for '{identifier}'")
        # Same message for "no such user" and "wrong password" on purpose.
        return {"success": False, "message": "Invalid username or password."}
    except Exception as exc:
        log_event("database", "ERROR", f"Login error: {exc}")
        return {"success": False, "message": "Login failed."}
    finally:
        conn.close()


# ---------- self-test: python3 arms_db.py ----------

if __name__ == "__main__":
    import getpass

    if "DB_PASSWORD" not in os.environ:
        os.environ["DB_PASSWORD"] = getpass.getpass("arms_app password: ")

    name = "selftest_" + secrets.token_hex(3)
    mail = name + "@example.com"

    print("register         :", register_user(name, mail, "TestPassw0rd!"))
    print("register again   :", register_user(name, mail, "TestPassw0rd!"))
    print("login (correct)  :", login_user(name, "TestPassw0rd!"))
    print("login (wrong pw) :", login_user(name, "wrong-password"))

    # clean up the test row so the users table stays tidy
    conn = _connect()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM users WHERE username = %s", (name,))
    conn.close()
    print("self-test user removed.")
