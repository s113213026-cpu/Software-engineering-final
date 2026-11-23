from flask import Blueprint, g, render_template

from auth import login_required
from db import get_db

bp = Blueprint("bookings", __name__, url_prefix="/bookings")


@bp.get("/")
@login_required
def index():
    bookings = get_db().execute(
        """SELECT rooms.code, bookings.starts_at, bookings.ends_at, bookings.status
           FROM bookings JOIN rooms ON rooms.id = bookings.room_id
           WHERE bookings.user_id = ? ORDER BY bookings.starts_at""",
        (g.user["id"],),
    ).fetchall()
    return render_template("bookings.html", bookings=bookings)
