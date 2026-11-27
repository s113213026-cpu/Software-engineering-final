import secrets
from functools import wraps

from flask import Blueprint, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_db

bp = Blueprint("auth", __name__)


@bp.before_app_request
def load_user():
    g.user = None
    user_id = session.get("user_id")
    if user_id is not None:
        g.user = get_db().execute(
            "SELECT id, username, name, role, status, email FROM users WHERE id = ?", (user_id,)
        ).fetchone()


def login_required(view):
    @wraps(view)
    def protected_view(**kwargs):
        if g.user is None:
            destination = request.full_path if request.query_string else request.path
            return redirect(url_for("auth.login", next=destination))
        return view(**kwargs)

    return protected_view


def admin_required(view):
    @wraps(view)
    def protected_view(**kwargs):
        if g.user is None:
            return redirect(url_for("auth.login", next=request.path))
        if g.user["role"] != "admin":
            abort(403)
        return view(**kwargs)

    return protected_view


def teacher_required(view):
    @wraps(view)
    def protected_view(**kwargs):
        if g.user is None:
            return redirect(url_for("auth.login", next=request.path))
        if g.user["role"] not in ("teacher", "admin"):
            abort(403)
        return view(**kwargs)

    return protected_view


@bp.app_template_global()
def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


@bp.before_request
def verify_form_token():
    if request.method == "POST":
        expected = session.get("csrf_token")
        received = request.form.get("csrf_token", "")
        if not expected or not secrets.compare_digest(expected.encode(), received.encode()):
            abort(400)


@bp.route("/login", methods=["GET", "POST"])
def login():
    next_url = request.args.get("next") or request.args.get("page")
    if (
        not next_url
        or not next_url.startswith("/")
        or next_url.startswith("//")
        or "\\" in next_url
        or any(char in next_url for char in "\t\r\n")
    ):
        next_url = url_for("home")
    if g.user is not None:
        return redirect(next_url)

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = get_db().execute(
            "SELECT id, username, password_hash, role, status FROM users WHERE username = ?", (username,)
        ).fetchone()

        if user is None or not check_password_hash(user["password_hash"], password):
            error = "帳號或密碼有誤。"
        elif user["status"] == "pending":
            error = "此帳號仍在審核中，請待管理員審核開通後再行登入。"
        elif user["status"] == "rejected":
            error = "此帳號未通過審核或已被停用，如有疑問請洽管院管理員。"
        else:
            session.clear()
            session["user_id"] = user["id"]
            return redirect(next_url)

    return render_template("login.html", error=error)


@bp.route("/register", methods=["GET", "POST"])
def register():
    if g.user is not None:
        return redirect(url_for("home"))

    error = None
    success = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        name = request.form.get("name", "").strip()
        role = request.form.get("role", "user")
        email = request.form.get("email", "").strip()

        if not username or not password or not name:
            error = "請填寫所有必填欄位（帳號、密碼、姓名）。"
        elif len(password) < 4:
            error = "密碼長度至少需 4 個字元。"
        elif role not in ("user", "teacher"):
            error = "請選擇合法的角色（學生或教師）。"
        else:
            db = get_db()
            existing = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
            if existing is not None:
                error = f"帳號「{username}」已被註冊，請換一個帳號。"
            else:
                # 註冊預設為待審核 (pending)
                with db:
                    db.execute(
                        """INSERT INTO users (username, password_hash, name, role, status, email)
                           VALUES (?, ?, ?, ?, 'pending', ?)""",
                        (username, generate_password_hash(password), name, role, email),
                    )
                success = "註冊成功！您的帳號已提交管理員審核，審核通過後即可登入。"

    return render_template("register.html", error=error, success=success)


@bp.route("/admin/users", methods=["GET", "POST"])
@admin_required
def admin_users():
    db = get_db()
    if request.method == "POST":
        action = request.form.get("action")
        target_user_id = request.form.get("user_id")

        if action == "approve":
            with db:
                db.execute("UPDATE users SET status = 'approved' WHERE id = ?", (target_user_id,))
        elif action == "reject":
            with db:
                db.execute("UPDATE users SET status = 'rejected' WHERE id = ?", (target_user_id,))
        elif action == "change_role":
            new_role = request.form.get("new_role")
            if new_role in ("admin", "teacher", "user"):
                with db:
                    db.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, target_user_id))
        return redirect(url_for("auth.admin_users"))

    users = db.execute(
        "SELECT id, username, name, role, status, email, created_at FROM users ORDER BY created_at DESC"
    ).fetchall()
    return render_template("admin_users.html", users=users)


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))
