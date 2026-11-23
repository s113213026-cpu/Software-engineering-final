import os
import secrets
from pathlib import Path

from flask import Flask, render_template

import auth
import db
from modules import bookings, scheduling, spaces


def create_app(config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        DATABASE=Path(app.instance_path) / "portal.sqlite3",
        SECRET_KEY=os.environ.get("PORTAL_SECRET_KEY") or secrets.token_hex(32),
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if config is not None:
        app.config.update(config)

    db.init_app(app)
    app.register_blueprint(auth.bp)
    app.register_blueprint(spaces.bp)
    app.register_blueprint(bookings.bp)
    app.register_blueprint(scheduling.bp)

    @app.get("/")
    def home():
        return render_template("home.html")

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000)
