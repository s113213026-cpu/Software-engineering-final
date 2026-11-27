import re
from collections import defaultdict
from datetime import date, datetime

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from auth import admin_required, login_required, verify_form_token
from db import get_db

bp = Blueprint("bookings", __name__, url_prefix="/bookings")
bp.before_request(verify_form_token)

ITEM_CHOICES = ("鑰匙", "簡報筆", "筆電", "轉接頭")
WEEKDAYS = ("週一", "週二", "週三", "週四", "週五", "週六", "週日")
TIME_PATTERN = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]")
ADMIN_ACTIONS = {
    "approve": "已核准借用申請。",
    "reject": "已退回借用申請。",
    "pickup": "已登記領用。",
    "return": "已確認歸還。",
}


def parse_date(value):
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def open_rooms(connection):
    return connection.execute(
        "SELECT id, code, name FROM rooms WHERE is_active = 1 ORDER BY code"
    ).fetchall()


def selected_room_id(rooms, requested_id):
    if requested_id is not None:
        return next((room["id"] for room in rooms if room["id"] == requested_id), None)
    return rooms[0]["id"] if rooms else None


def has_conflict(connection, room_id, starts_at, ends_at, pending_for=None):
    return connection.execute(
        """SELECT 1 FROM bookings
           WHERE room_id = ? AND starts_at < ? AND ends_at > ?
             AND (status = '已核准' OR (status = '待審核' AND user_id = ?))
           LIMIT 1""",
        (room_id, ends_at, starts_at, pending_for),
    ).fetchone() is not None


def course_slots(connection, room_id, day):
    return connection.execute(
        """SELECT time(starts_at) AS start_time, time(ends_at) AS end_time, status
           FROM course_preferences
           WHERE room_id = ?
             AND status IN ('待確認', '已確認', '衝堂衝突')
             AND time(starts_at) < time(ends_at)
             AND (
                (length(starts_at) <= 8 AND length(ends_at) <= 8 AND day_of_week = ?)
                OR (length(starts_at) > 8 AND length(ends_at) > 8
                    AND date(starts_at) = ? AND date(ends_at) = ?)
             )
           ORDER BY start_time, end_time, id""",
        (room_id, day.isoweekday(), day.isoformat(), day.isoformat()),
    ).fetchall()


def has_confirmed_course_conflict(connection, room_id, starts_at, ends_at):
    start = datetime.fromisoformat(starts_at)
    end = datetime.fromisoformat(ends_at)
    start_time = start.time().isoformat()
    end_time = end.time().isoformat()
    return any(
        course["status"] == "已確認"
        and course["start_time"] < end_time
        and course["end_time"] > start_time
        for course in course_slots(connection, room_id, start.date())
    )


@bp.get("/")
@login_required
def index():
    connection = get_db()
    rooms = open_rooms(connection)
    room_id = selected_room_id(rooms, request.args.get("room_id", type=int))
    today = date.today()
    selected_date = parse_date(request.args.get("date", "")) or today
    first = selected_date.toordinal() - selected_date.weekday()
    last = min(first + 6, date.max.toordinal())
    week = [date.fromordinal(day) for day in range(first, last + 1)]
    previous_week = date.fromordinal(first - 7) if first > 7 else None
    next_week = date.fromordinal(last + 1) if last < date.max.toordinal() else None

    by_day = defaultdict(list)
    if room_id is not None:
        entries = connection.execute(
            """SELECT booking_date, starts_at, ends_at, status, is_picked_up, is_returned,
                      0 AS is_course
               FROM bookings
               WHERE room_id = ? AND booking_date BETWEEN ? AND ?
                 AND status IN ('待審核', '已核准')
               ORDER BY starts_at, id""",
            (room_id, week[0].isoformat(), week[-1].isoformat()),
        )
        for entry in entries:
            by_day[entry["booking_date"]].append(entry)
        for day in week:
            day_key = day.isoformat()
            by_day[day_key].extend(
                {
                    "starts_at": f"{day_key} {course['start_time']}",
                    "ends_at": f"{day_key} {course['end_time']}",
                    "status": course["status"],
                    "is_course": True,
                }
                for course in course_slots(connection, room_id, day)
            )

    bookings = connection.execute(
        """SELECT bookings.*, rooms.code, rooms.name AS room_name
           FROM bookings JOIN rooms ON rooms.id = bookings.room_id
           WHERE bookings.user_id = ?
           ORDER BY bookings.starts_at DESC, bookings.id DESC""",
        (g.user["id"],),
    ).fetchall()

    return render_template(
        "bookings.html", rooms=rooms, room_id=room_id, today=today,
        selected_date=selected_date, week=week, weekdays=WEEKDAYS, by_day=by_day,
        previous_week=previous_week, next_week=next_week, bookings=bookings,
    )


@bp.route("/new", methods=["GET", "POST"])
@login_required
def create_booking():
    connection = get_db()
    rooms = open_rooms(connection)
    if request.method == "GET":
        selected_date = parse_date(request.args.get("date", "")) or date.today()
        form = {
            "room_id": selected_room_id(rooms, request.args.get("room_id", type=int)),
            "date": selected_date.isoformat(),
            "start": "", "end": "", "reason": "", "items": set(),
        }
        return render_template("booking_form.html", rooms=rooms, form=form, item_choices=ITEM_CHOICES)

    form = {
        "room_id": request.form.get("room_id", type=int),
        "date": request.form.get("date", ""),
        "start": request.form.get("start", ""),
        "end": request.form.get("end", ""),
        "reason": request.form.get("reason", "").strip(),
        "items": set(request.form.getlist("items")),
    }
    error = validate_application(form, rooms)
    status_code = 400
    if error is None:
        error = save_application(connection, form, g.user["id"])
        if error is None:
            flash("借用申請已送出，請等候管理員審核。", "success")
            return redirect(url_for(".index", room_id=form["room_id"], date=form["date"]))
        status_code = 409

    return render_template(
        "booking_form.html", rooms=rooms, form=form, item_choices=ITEM_CHOICES, error=error,
    ), status_code


def validate_application(form, rooms):
    if not any(room["id"] == form["room_id"] for room in rooms):
        return "請選擇開放借用的空間。"
    if parse_date(form["date"]) is None:
        return "請輸入有效的借用日期。"
    if not TIME_PATTERN.fullmatch(form["start"]) or not TIME_PATTERN.fullmatch(form["end"]):
        return "請輸入有效的開始與結束時間。"
    if form["start"] >= form["end"]:
        return "結束時間必須晚於開始時間，且須在同一天。"
    if form["items"].difference(ITEM_CHOICES):
        return "請從清單中選擇要借用的物品。"
    if len(form["reason"]) > 300:
        return "借用事由請控制在 300 字以內。"
    return None


def save_application(connection, form, user_id):
    booking_date = form["date"]
    starts_at = f"{booking_date} {form['start']}"
    ends_at = f"{booking_date} {form['end']}"
    room_id = form["room_id"]
    items = ", ".join(item for item in ITEM_CHOICES if item in form["items"])

    with connection:
        connection.execute("BEGIN IMMEDIATE")
        if connection.execute(
            "SELECT 1 FROM rooms WHERE id = ? AND is_active = 1", (room_id,)
        ).fetchone() is None:
            return "該空間目前未開放借用，請改選其他空間。"
        if has_conflict(connection, room_id, starts_at, ends_at, pending_for=user_id):
            return "這個時段已有核准的借用，或你已有重疊的待審核申請。"
        if has_confirmed_course_conflict(connection, room_id, starts_at, ends_at):
            return "這個時段已有確認排課，請改選教室或時段。"
        connection.execute(
            """INSERT INTO bookings
               (user_id, room_id, booking_date, starts_at, ends_at, borrowed_items, reason)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, room_id, booking_date, starts_at, ends_at, items, form["reason"]),
        )
    return None


@bp.get("/admin")
@admin_required
def admin_index():
    bookings = get_db().execute(
        """SELECT bookings.*, rooms.code, rooms.name AS room_name,
                  users.name AS applicant_name, users.username
           FROM bookings
           JOIN rooms ON rooms.id = bookings.room_id
           JOIN users ON users.id = bookings.user_id
           ORDER BY (bookings.status = '待審核') DESC, bookings.starts_at DESC, bookings.id DESC"""
    ).fetchall()
    return render_template("booking_admin.html", bookings=bookings)


@bp.post("/admin/<int(min=1,max=9223372036854775807):booking_id>")
@admin_required
def admin_action(booking_id):
    action = request.form.get("action")
    if action not in ADMIN_ACTIONS:
        abort(400)

    connection = get_db()
    # Hold the write lock from the conflict check until the status change commits.
    with connection:
        connection.execute("BEGIN IMMEDIATE")
        booking = connection.execute(
            """SELECT bookings.*, rooms.is_active FROM bookings
               JOIN rooms ON rooms.id = bookings.room_id WHERE bookings.id = ?""",
            (booking_id,),
        ).fetchone()
        if booking is None:
            abort(404)

        if action in ("approve", "reject"):
            comment = request.form.get("comment", "").strip()
            error = review_booking(connection, booking, action, comment)
        else:
            error = record_handoff(connection, booking, action, g.user["username"])

    flash(error or ADMIN_ACTIONS[action], "error" if error else "success")
    return redirect(url_for(".admin_index"))


def review_booking(connection, booking, action, comment):
    if booking["status"] != "待審核":
        return "只有待審核的申請可以核准或退件。"
    if len(comment) > 300:
        return "審核意見請控制在 300 字以內。"
    if action == "approve":
        if not booking["is_active"]:
            return "該空間目前未開放借用。"
        if has_conflict(connection, booking["room_id"], booking["starts_at"], booking["ends_at"]):
            return "所選教室已有重疊的核准借用，請退件或確認其他申請。"
        if has_confirmed_course_conflict(connection, booking["room_id"], booking["starts_at"], booking["ends_at"]):
            return "所選教室已有重疊的確認排課，無法核准這筆申請。"

    status = "已核准" if action == "approve" else "已退件"
    connection.execute(
        "UPDATE bookings SET status = ?, review_comment = ? WHERE id = ?",
        (status, comment, booking["id"]),
    )
    return None


def record_handoff(connection, booking, action, admin_username):
    if booking["status"] != "已核准" or booking["is_returned"]:
        return "這筆借用目前無法登記領用或歸還。"

    if action == "pickup":
        if booking["is_picked_up"]:
            return "這筆借用已登記領用。"
        connection.execute(
            """UPDATE bookings SET is_picked_up = 1, picked_up_at = datetime('now', 'localtime'),
                      picked_up_by = ? WHERE id = ?""",
            (admin_username, booking["id"]),
        )
    else:
        if not booking["is_picked_up"]:
            return "請先登記領用，才能確認歸還。"
        connection.execute(
            """UPDATE bookings SET is_returned = 1, returned_at = datetime('now', 'localtime'),
                      returned_by = ? WHERE id = ?""",
            (admin_username, booking["id"]),
        )
    return None
