from flask import Blueprint, g, render_template

from auth import login_required
from db import get_db

bp = Blueprint("scheduling", __name__, url_prefix="/scheduling")


@bp.get("/")
@login_required
def index():
    courses = get_db().execute(
        """SELECT course_preferences.course_name, rooms.code,
                  course_preferences.starts_at, course_preferences.ends_at
           FROM course_preferences JOIN rooms ON rooms.id = course_preferences.room_id
           WHERE course_preferences.user_id = ? ORDER BY course_preferences.starts_at""",
        (g.user["id"],),
    ).fetchall()
    return render_template("scheduling.html", courses=courses)
