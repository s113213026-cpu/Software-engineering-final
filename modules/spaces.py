from flask import Blueprint, render_template

from db import get_db

bp = Blueprint("spaces", __name__, url_prefix="/spaces")


@bp.get("/")
def index():
    rooms = get_db().execute(
        "SELECT id, code, name, floor, capacity, room_type, equipment, description FROM rooms WHERE is_active = 1 ORDER BY floor, code"
    ).fetchall()
    return render_template("spaces.html", rooms=rooms)
