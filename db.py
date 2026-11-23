import sqlite3
from pathlib import Path

from flask import current_app, g
from werkzeug.security import generate_password_hash


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_error):
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def init_app(app):
    app.teardown_appcontext(close_db)
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)

    with app.app_context():
        connection = get_db()
        schema = Path(__file__).with_name("schema.sql")
        connection.executescript(schema.read_text(encoding="utf-8"))

        # 初始化預設角色帳號 (管理員、教師、學生)，方便三位組員直接登入與測試各自模組
        preset_users = [
            ("admin", "admin1234", "系統管理員", "admin", "approved", "admin@ncnu.edu.tw"),
            ("teacher", "teacher1234", "陳教授", "teacher", "approved", "teacher@ncnu.edu.tw"),
            ("demo", "demo1234", "林同學", "user", "approved", "student@ncnu.edu.tw"),
        ]

        with connection:
            for username, pwd, name, role, status, email in preset_users:
                existing = connection.execute(
                    "SELECT id FROM users WHERE username = ?", (username,)
                ).fetchone()
                if existing is None:
                    connection.execute(
                        """INSERT INTO users (username, password_hash, name, role, status, email)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (username, generate_password_hash(pwd), name, role, status, email),
                    )
