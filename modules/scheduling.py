from flask import Blueprint, g, redirect, render_template, request, url_for, abort, jsonify
from auth import login_required
from db import get_db

bp = Blueprint("scheduling", __name__, url_prefix="/scheduling")


def detect_conflicts(courses):
    """
    檢查課程清單中是否有時間衝突：
    1. 同一間教室在同一星期時段重疊
    2. 同一位老師在同一星期時段重疊
    回傳: (conflict_ids_set, conflict_messages_list)
    """
    conflict_ids = set()
    conflict_details = []

    # 兩兩比較
    n = len(courses)
    for i in range(n):
        for j in range(i + 1, n):
            c1 = courses[i]
            c2 = courses[j]

            # 必須是同一個星期幾
            if c1["day_of_week"] != c2["day_of_week"]:
                continue

            # 檢查時間是否交疊: max(start1, start2) < min(end1, end2)
            if max(c1["starts_at"], c2["starts_at"]) < min(c1["ends_at"], c2["ends_at"]):
                # 衝突類型 1: 同教室衝突
                if c1["room_id"] and c2["room_id"] and c1["room_id"] == c2["room_id"]:
                    conflict_ids.add(c1["id"])
                    conflict_ids.add(c2["id"])
                    conflict_details.append({
                        "type": "教室衝突",
                        "desc": f"週{c1['day_of_week']} [{c1['room_code']}] 教室衝突：{c1['course_name']} ({c1['starts_at']}-{c1['ends_at']}) 與 {c2['course_name']} ({c2['starts_at']}-{c2['ends_at']})"
                    })

                # 衝突類型 2: 同老師衝堂
                if c1["user_id"] == c2["user_id"]:
                    conflict_ids.add(c1["id"])
                    conflict_ids.add(c2["id"])
                    conflict_details.append({
                        "type": "教師衝堂",
                        "desc": f"週{c1['day_of_week']} [{c1['teacher_name']}] 教師衝堂：{c1['course_name']} ({c1['starts_at']}-{c1['ends_at']}) 與 {c2['course_name']} ({c2['starts_at']}-{c2['ends_at']})"
                    })

    return conflict_ids, conflict_details


@bp.get("/")
@login_required
def index():
    db = get_db()
    is_admin = (g.user["role"] == "admin")
    
    rooms = db.execute("SELECT id, code, name FROM rooms WHERE is_active = 1 ORDER BY code").fetchall()
    teachers = db.execute("SELECT id, name, username FROM users WHERE role IN ('teacher', 'admin')").fetchall()

    # 查詢所有課程以進行全院衝突檢測
    all_courses = db.execute(
        """SELECT c.id, c.user_id, c.room_id, c.course_name, c.course_code, 
                  c.day_of_week, c.starts_at, c.ends_at, c.status,
                  r.code AS room_code, r.name AS room_name,
                  u.name AS teacher_name
           FROM course_preferences c
           LEFT JOIN rooms r ON r.id = c.room_id
           LEFT JOIN users u ON u.id = c.user_id
           ORDER BY c.day_of_week, c.starts_at"""
    ).fetchall()

    conflict_ids, conflict_details = detect_conflicts(all_courses)

    # 管理員看全部，老師只看自己的課
    if is_admin:
        display_courses = all_courses
    else:
        display_courses = [c for c in all_courses if c["user_id"] == g.user["id"]]

    return render_template(
        "scheduling.html",
        courses=display_courses,
        conflict_ids=conflict_ids,
        conflict_details=conflict_details,
        rooms=rooms,
        teachers=teachers,
        is_admin=is_admin,
    )


@bp.post("/add")
@login_required
def add_course():
    db = get_db()
    course_name = request.form.get("course_name", "").strip()
    room_id = request.form.get("room_id") or None
    day_of_week = int(request.form.get("day_of_week", 1))
    starts_at = request.form.get("starts_at", "").strip()
    ends_at = request.form.get("ends_at", "").strip()

    if not course_name or not starts_at or not ends_at:
        return redirect(url_for("scheduling.index"))

    target_user_id = request.form.get("teacher_id") if g.user["role"] == "admin" else g.user["id"]
    if not target_user_id:
        target_user_id = g.user["id"]

    with db:
        db.execute(
            """INSERT INTO course_preferences (user_id, room_id, course_name, day_of_week, starts_at, ends_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (target_user_id, room_id, course_name, day_of_week, starts_at, ends_at),
        )

    return redirect(url_for("scheduling.index"))


@bp.post("/edit/<int:course_id>")
@login_required
def edit_course(course_id):
    db = get_db()
    course = db.execute("SELECT user_id FROM course_preferences WHERE id = ?", (course_id,)).fetchone()
    if not course:
        abort(404)

    # 權限檢查：只有管理員，或本人老師可以修改
    if g.user["role"] != "admin" and course["user_id"] != g.user["id"]:
        abort(403)

    course_name = request.form.get("course_name", "").strip()
    room_id = request.form.get("room_id") or None
    day_of_week = int(request.form.get("day_of_week", 1))
    starts_at = request.form.get("starts_at", "").strip()
    ends_at = request.form.get("ends_at", "").strip()

    if g.user["role"] == "admin":
        target_user_id = request.form.get("teacher_id") or course["user_id"]
    else:
        target_user_id = course["user_id"]

    with db:
        db.execute(
            """UPDATE course_preferences 
               SET course_name = ?, room_id = ?, day_of_week = ?, starts_at = ?, ends_at = ?, user_id = ?
               WHERE id = ?""",
            (course_name, room_id, day_of_week, starts_at, ends_at, target_user_id, course_id),
        )

    return redirect(url_for("scheduling.index"))


@bp.post("/delete/<int:course_id>")
@login_required
def delete_course(course_id):
    db = get_db()
    course = db.execute("SELECT user_id FROM course_preferences WHERE id = ?", (course_id,)).fetchone()
    if not course:
        abort(404)

    if g.user["role"] != "admin" and course["user_id"] != g.user["id"]:
        abort(403)

    with db:
        db.execute("DELETE FROM course_preferences WHERE id = ?", (course_id,))

    return redirect(url_for("scheduling.index"))