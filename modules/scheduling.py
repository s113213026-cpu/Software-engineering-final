from flask import Blueprint, flash, g, redirect, render_template, request, url_for, abort, jsonify
from auth import login_required
from db import get_db

bp = Blueprint("scheduling", __name__, url_prefix="/scheduling")


def time_to_minutes(time_str):
    """將 '09:30' 或 '09:30:00' 轉為自 00:00 起算的分鐘數 (整數)"""
    if not time_str:
        return None
    try:
        parts = time_str.strip().split(":")
        hours = int(parts[0])
        minutes = int(parts[1])
        return hours * 60 + minutes
    except (ValueError, IndexError):
        return None


def validate_course_schedule(starts_at, ends_at):
    """
    防呆驗證排課時段合法性：
    1. 格式必須能解析為時間
    2. 結束時間必須嚴格晚於開始時間 (禁止倒置、相同、跨日)
    3. 必須在管院合法排課區間內 (08:00 ~ 22:00)
    4. 單堂課長度限制 (30 分鐘 ~ 6 小時)
    回傳: (is_valid, error_message)
    """
    start_m = time_to_minutes(starts_at)
    end_m = time_to_minutes(ends_at)

    if start_m is None or end_m is None:
        return False, "時間格式有誤，請輸入正確的時間（如 09:00）。"

    if end_m <= start_m:
        return False, "結束時間必須晚於開始時間（不得倒置、相同或跨日）。"

    min_allowed = 8 * 60    # 08:00 (480 分鐘)
    max_allowed = 22 * 60   # 22:00 (1320 分鐘)

    if start_m < min_allowed:
        return False, "課程開始時間不得早於每日開放時間 08:00。"

    if end_m > max_allowed:
        return False, "課程結束時間不得晚於每日開放時間 22:00。"

    duration = end_m - start_m
    if duration < 30:
        return False, "單堂課程時長至少需為 30 分鐘。"

    if duration > 360:
        return False, "單堂課程時長不得超過 6 小時。"

    return True, ""


def detect_conflicts(courses):
    """
    精確檢查課程清單中是否有時間衝突：
    1. 同一間教室在同一星期時段重疊 (教室衝突)
    2. 同一位老師在同一星期時段重疊 (教師衝堂)
    
    使用轉成分鐘整數的重疊公式：max(start1, start2) < min(end1, end2)
    邊界案例測試結果：
      - 09:00-10:00 與 10:00-11:00：max(10:00)=10:00, min(10:00)=10:00 -> 10:00 < 10:00 為 False (首尾相接合法，不衝突)
      - 09:00-10:30 與 10:00-11:00：max(10:00) < min(10:30) 為 True (重疊衝突)
      - 09:00-11:00 與 09:30-10:00：max(09:30) < min(10:00) 為 True (包含重疊衝突)
    """
    conflict_ids = set()
    conflict_details = []

    # 預先解析每堂課的時間分鐘數
    parsed = []
    for c in courses:
        s_m = time_to_minutes(c["starts_at"])
        e_m = time_to_minutes(c["ends_at"])
        parsed.append({
            "course": c,
            "start_m": s_m,
            "end_m": e_m
        })

    n = len(parsed)
    for i in range(n):
        for j in range(i + 1, n):
            p1 = parsed[i]
            p2 = parsed[j]
            c1 = p1["course"]
            c2 = p2["course"]

            # 必須是同一個星期幾
            if c1["day_of_week"] != c2["day_of_week"]:
                continue

            if p1["start_m"] is None or p1["end_m"] is None or p2["start_m"] is None or p2["end_m"] is None:
                continue

            # 嚴格區間交疊判定
            if max(p1["start_m"], p2["start_m"]) < min(p1["end_m"], p2["end_m"]):
                # 衝突 1: 同教室衝突 (兩門課都選了同一間實體教室)
                if c1["room_id"] and c2["room_id"] and c1["room_id"] == c2["room_id"]:
                    conflict_ids.add(c1["id"])
                    conflict_ids.add(c2["id"])
                    conflict_details.append({
                        "type": "教室衝突",
                        "desc": f"週{c1['day_of_week']} [{c1['room_code']}] 教室撞期：{c1['course_name']} ({c1['starts_at']}-{c1['ends_at']}) 與 {c2['course_name']} ({c2['starts_at']}-{c2['ends_at']})"
                    })

                # 衝突 2: 同老師衝堂 (同一位老師分身乏術)
                if c1["user_id"] == c2["user_id"]:
                    conflict_ids.add(c1["id"])
                    conflict_ids.add(c2["id"])
                    conflict_details.append({
                        "type": "教師衝堂",
                        "desc": f"週{c1['day_of_week']} [{c1['teacher_name']}] 老師撞期：{c1['course_name']} ({c1['starts_at']}-{c1['ends_at']}) 與 {c2['course_name']} ({c2['starts_at']}-{c2['ends_at']})"
                    })

    return conflict_ids, conflict_details


@bp.get("/")
@login_required
def index():
    db = get_db()
    is_admin = (g.user["role"] == "admin")
    
    rooms = db.execute("SELECT id, code, name FROM rooms WHERE is_active = 1 ORDER BY code").fetchall()
    teachers = db.execute("SELECT id, name, username FROM users WHERE role IN ('teacher', 'admin')").fetchall()

    # 查詢全院所有課程以計算衝突
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
    try:
        day_of_week = int(request.form.get("day_of_week", 1))
    except ValueError:
        day_of_week = 1
    starts_at = request.form.get("starts_at", "").strip()
    ends_at = request.form.get("ends_at", "").strip()

    if not course_name or not starts_at or not ends_at:
        flash("請完整填寫課程名稱與時段！", "error")
        return redirect(url_for("scheduling.index"))

    # 防呆驗證
    is_valid, err_msg = validate_course_schedule(starts_at, ends_at)
    if not is_valid:
        flash(f"排課失敗：{err_msg}", "error")
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

    flash("課程志願登記成功！", "success")
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
    try:
        day_of_week = int(request.form.get("day_of_week", 1))
    except ValueError:
        day_of_week = 1
    starts_at = request.form.get("starts_at", "").strip()
    ends_at = request.form.get("ends_at", "").strip()

    if not course_name or not starts_at or not ends_at:
        flash("請完整填寫課程名稱與時段！", "error")
        return redirect(url_for("scheduling.index"))

    # 防呆驗證
    is_valid, err_msg = validate_course_schedule(starts_at, ends_at)
    if not is_valid:
        flash(f"修改失敗：{err_msg}", "error")
        return redirect(url_for("scheduling.index"))

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

    flash("課程資料已成功更新！", "success")
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

    flash("課程已成功刪除。", "success")
    return redirect(url_for("scheduling.index"))


# 取得日曆事件 API (供 FullCalendar 載入排課事件)
@bp.get("/api/events")
@login_required
def api_events():
    db = get_db()
    all_courses = db.execute(
        """SELECT c.id, c.user_id, c.room_id, c.course_name, 
                  c.day_of_week, c.starts_at, c.ends_at,
                  r.code AS room_code, u.name AS teacher_name
           FROM course_preferences c
           LEFT JOIN rooms r ON r.id = c.room_id
           LEFT JOIN users u ON u.id = c.user_id"""
    ).fetchall()

    conflict_ids, _ = detect_conflicts(all_courses)

    events = []
    for c in all_courses:
        is_conflict = c["id"] in conflict_ids
        events.append({
            "id": str(c["id"]),
            "title": f"{c['course_name']} ({c['teacher_name']} - {c['room_code'] or '未排教室'})",
            # FullCalendar 的 daysOfWeek: 0為週日, 1為週一, ..., 5為週五, 6為週六
            "daysOfWeek": [c["day_of_week"] % 7],
            "startTime": c["starts_at"],
            "endTime": c["ends_at"],
            # 衝突課程以紅色呈現，正常課程以深藍色呈現
            "backgroundColor": "#dc3545" if is_conflict else "#1a73e8",
            "borderColor": "#b02a37" if is_conflict else "#1557b0",
            "textColor": "#ffffff",
        })

    return jsonify(events)


# 管理員滑鼠 Drag & Drop 拖曳調課更新 API
@bp.post("/api/update_time")
@login_required
def api_update_time():
    if g.user["role"] != "admin":
        return jsonify({"success": False, "message": "僅管理員具備拖曳排課權限"}), 403

    data = request.get_json(silent=True) or {}
    course_id = data.get("course_id")
    day_of_week = data.get("day_of_week")
    starts_at = data.get("starts_at")
    ends_at = data.get("ends_at")

    if not course_id or not day_of_week or not starts_at or not ends_at:
        return jsonify({"success": False, "message": "參數不完整"}), 400

    # 拖曳調課時同樣進行嚴格防呆驗證
    is_valid, err_msg = validate_course_schedule(starts_at, ends_at)
    if not is_valid:
        return jsonify({"success": False, "message": err_msg}), 400

    db = get_db()
    with db:
        db.execute(
            """UPDATE course_preferences 
               SET day_of_week = ?, starts_at = ?, ends_at = ?
               WHERE id = ?""",
            (day_of_week, starts_at, ends_at, course_id),
        )

    return jsonify({"success": True})
