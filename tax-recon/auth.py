"""Accounts: sign up, log in, log out with Flask-Login. Users live in SQLite; passwords are stored only as
salted scrypt hashes (werkzeug.security), never in plain text.

A demo account is created at startup so judges can try the dashboard without signing up.
"""
import os
import pathlib
import secrets
import sqlite3
import time
from urllib.parse import urlparse

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import LoginManager, UserMixin, current_user, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

DEMO_EMAIL = "demo@taxrecon.app"
DEMO_PASSWORD = "audit-ledger-demo"
DEMO_NAME = "Demo CA"

bp = Blueprint("auth", __name__)
login_manager = LoginManager()
_instance = pathlib.Path(__file__).resolve().parent / "instance"
DB_PATH = pathlib.Path(os.environ.get("TAXRECON_DB", _instance / "users.sqlite3"))


# ---------------------------------------------------------------- storage

def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')))""")
    ensure_demo_account()


def ensure_demo_account():
    """Make sure the published demo login works. Runs on every start (each gunicorn worker imports the app), so it
    survives Render's free plan wiping the disk on each deploy. Safe to run concurrently: INSERT OR IGNORE lets the
    UNIQUE email decide, and the password is reset only if it no longer matches the one shown on the login page."""
    with db() as con:
        con.execute("INSERT OR IGNORE INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                    (DEMO_NAME, DEMO_EMAIL, generate_password_hash(DEMO_PASSWORD)))
        row = con.execute("SELECT id, password_hash FROM users WHERE email = ?", (DEMO_EMAIL,)).fetchone()
        if not check_password_hash(row["password_hash"], DEMO_PASSWORD):
            con.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(DEMO_PASSWORD), row["id"]))


class User(UserMixin):
    def __init__(self, row):
        self.id, self.name, self.email = str(row["id"]), row["name"], row["email"]

    @property
    def is_demo(self):
        return self.email.lower() == DEMO_EMAIL


def find_user(email):
    with db() as con:
        return con.execute("SELECT * FROM users WHERE email = ?", (email.strip(),)).fetchone()


@login_manager.user_loader
def load_user(user_id):
    with db() as con:
        row = con.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return User(row) if row else None


@login_manager.unauthorized_handler
def unauthorized():
    """Data endpoints answer 401 JSON; pages redirect to the login page and come back afterwards."""
    if request.path.startswith(("/ask", "/record", "/export", "/download", "/sample")) or request.is_json:
        return jsonify({"error": "Log in to use the dashboard."}), 401
    return redirect(url_for("auth.login", next=request.full_path))


# ---------------------------------------------------------------- security helpers

def secret_key():
    """FLASK_SECRET_KEY from the environment / .env, else one generated on first run and kept in instance/."""
    key = os.environ.get("FLASK_SECRET_KEY")
    if key:
        return key
    f = _instance / "secret_key"
    f.parent.mkdir(parents=True, exist_ok=True)
    try:  # "x" = create only if missing, so two workers starting together still end up sharing one key
        with open(f, "x", encoding="utf-8") as fh:
            fh.write(secrets.token_hex(32))
    except FileExistsError:
        pass
    for _ in range(50):  # the other worker may be mid-write
        key = f.read_text(encoding="utf-8").strip()
        if key:
            return key
        time.sleep(0.02)
    raise RuntimeError(f"Could not read the session secret from {f}")


def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


def check_csrf():
    sent = request.form.get("_csrf", "")
    if not sent or not secrets.compare_digest(sent, session.get("_csrf", "")):
        abort(400, "The form expired. Go back, reload the page and try again.")


def safe_next(target):
    """Only allow redirects back into this site."""
    if not target:
        return url_for("index") + "#dashboard"
    u = urlparse(target)
    if u.scheme or u.netloc or not target.startswith("/"):
        return url_for("index") + "#dashboard"
    return target


_failures = {}  # ip -> [timestamps of failed logins]
MAX_FAILS, WINDOW = 8, 15 * 60


def _too_many(ip):
    now = time.time()
    _failures[ip] = [t for t in _failures.get(ip, []) if now - t < WINDOW]
    return len(_failures[ip]) >= MAX_FAILS


# ---------------------------------------------------------------- routes

@bp.route("/login", methods=["GET", "POST"])
def login():
    nxt = request.values.get("next", "")
    if current_user.is_authenticated:
        return redirect(safe_next(nxt))
    email = ""
    if request.method == "POST":
        check_csrf()
        ip = request.remote_addr or "?"
        email = (request.form.get("email") or "").strip()
        password = request.form.get("password") or ""
        if _too_many(ip):
            flash("Too many failed attempts. Wait 15 minutes and try again.", "error")
        else:
            row = find_user(email) if email else None
            if row and check_password_hash(row["password_hash"], password):
                _failures.pop(ip, None)
                session.pop("_csrf", None)
                login_user(User(row), remember=bool(request.form.get("remember")))
                return redirect(safe_next(nxt))
            _failures.setdefault(ip, []).append(time.time())
            flash("That email and password don't match an account. Check them, or sign up.", "error")
    return render_template("auth.html", mode="login", email=email, nxt=nxt,
                           demo_email=DEMO_EMAIL, demo_password=DEMO_PASSWORD)


@bp.route("/signup", methods=["GET", "POST"])
def signup():
    nxt = request.values.get("next", "")
    if current_user.is_authenticated:
        return redirect(safe_next(nxt))
    form = {"name": "", "email": ""}
    if request.method == "POST":
        check_csrf()
        form = {"name": (request.form.get("name") or "").strip()[:80], "email": (request.form.get("email") or "").strip()[:200]}
        pw, pw2 = request.form.get("password") or "", request.form.get("confirm") or ""
        problems = []
        if not form["name"]:
            problems.append("Enter your name.")
        if "@" not in form["email"] or "." not in form["email"].split("@")[-1]:
            problems.append("Enter a valid email address.")
        if len(pw) < 8:
            problems.append("Use a password of at least 8 characters.")
        if pw != pw2:
            problems.append("The two passwords don't match.")
        if not problems and find_user(form["email"]):
            problems.append("An account with this email already exists. Log in instead.")
        if problems:
            for p in problems:
                flash(p, "error")
        else:
            with db() as con:
                cur = con.execute("INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                                  (form["name"], form["email"], generate_password_hash(pw)))
                row = con.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
            session.pop("_csrf", None)
            login_user(User(row))
            flash(f"Welcome, {row['name']}. Your account is ready.", "ok")
            return redirect(safe_next(nxt))
    return render_template("auth.html", mode="signup", form=form, nxt=nxt,
                           demo_email=DEMO_EMAIL, demo_password=DEMO_PASSWORD)


@bp.route("/logout", methods=["POST"])
def logout():
    check_csrf()
    logout_user()
    session.pop("_csrf", None)
    flash("You're logged out.", "ok")
    return redirect(url_for("index"))


def init_app(app):
    app.secret_key = secret_key()
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                      REMEMBER_COOKIE_HTTPONLY=True, REMEMBER_COOKIE_SAMESITE="Lax",
                      SESSION_COOKIE_SECURE=bool(os.environ.get("RENDER")),
                      REMEMBER_COOKIE_SECURE=bool(os.environ.get("RENDER")))
    init_db()
    login_manager.init_app(app)
    app.register_blueprint(bp)
    app.jinja_env.globals["csrf_token"] = csrf_token
