from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from auth import admin_required
from db import get_db

bp = Blueprint("spaces", __name__, url_prefix="/spaces")


@bp.get("/")
def index():
    """前台免登入空間清單，支援關鍵字搜尋、樓層、類型、容納人數篩選與排序。"""
    db = get_db()

    # 取得篩選參數
    q = request.args.get("q", "").strip()
    selected_floor = request.args.get("floor", "").strip()
    selected_type = request.args.get("type", "").strip()
    min_capacity = request.args.get("capacity", "").strip()
    sort_by = request.args.get("sort", "floor_code").strip()
    view_mode = request.args.get("view", "grid").strip()

    # 動態組合 SQL 查詢條件
    conditions = ["is_active = 1"]
    params = []

    if q:
        conditions.append(
            "(code LIKE ? OR name LIKE ? OR equipment LIKE ? OR description LIKE ?)"
        )
        wildcard = f"%{q}%"
        params.extend([wildcard, wildcard, wildcard, wildcard])

    if selected_floor:
        conditions.append("floor = ?")
        params.append(selected_floor)

    if selected_type:
        conditions.append("room_type = ?")
        params.append(selected_type)

    if min_capacity and min_capacity.isdigit():
        conditions.append("capacity >= ?")
        params.append(int(min_capacity))

    where_clause = " WHERE " + " AND ".join(conditions)

    # 排序規則
    if sort_by == "capacity_desc":
        order_clause = " ORDER BY capacity DESC, code ASC"
    elif sort_by == "capacity_asc":
        order_clause = " ORDER BY capacity ASC, code ASC"
    elif sort_by == "name":
        order_clause = " ORDER BY name ASC"
    else:
        order_clause = " ORDER BY floor ASC, code ASC"

    query = f"""
        SELECT id, code, name, floor, capacity, room_type, equipment, description,
               image_url, panorama_url, floor_plan_x, floor_plan_y
        FROM rooms
        {where_clause}
        {order_clause}
    """
    rooms = db.execute(query, params).fetchall()

    # 查詢所有現有樓層與類型（供篩選列動態選項）
    all_floors = [row["floor"] for row in db.execute("SELECT DISTINCT floor FROM rooms WHERE is_active = 1 ORDER BY floor").fetchall()]
    all_types = [row["room_type"] for row in db.execute("SELECT DISTINCT room_type FROM rooms WHERE is_active = 1 ORDER BY room_type").fetchall()]

    return render_template(
        "spaces.html",
        rooms=rooms,
        all_floors=all_floors,
        all_types=all_types,
        q=q,
        selected_floor=selected_floor,
        selected_type=selected_type,
        min_capacity=min_capacity,
        sort_by=sort_by,
        view_mode=view_mode,
        total_count=len(rooms),
    )


@bp.get("/map")
def floor_map():
    """管院各樓層平面圖與互動式教室位置標示。"""
    db = get_db()
    all_floors = [r["floor"] for r in db.execute(
        "SELECT DISTINCT floor FROM rooms WHERE is_active = 1 ORDER BY floor ASC"
    ).fetchall()]

    highlight_id = request.args.get("highlight", type=int)
    selected_floor = request.args.get("floor", "").strip()

    # 若有指定 highlight 教室，自動切換至該教室所在樓層
    if highlight_id:
        target = db.execute("SELECT floor FROM rooms WHERE id = ?", (highlight_id,)).fetchone()
        if target:
            selected_floor = target["floor"]

    if not selected_floor and all_floors:
        selected_floor = all_floors[0]

    rooms = db.execute(
        """SELECT id, code, name, floor, capacity, room_type, equipment, description,
                  floor_plan_x, floor_plan_y, panorama_url
           FROM rooms
           WHERE floor = ? AND is_active = 1
           ORDER BY code ASC""",
        (selected_floor,),
    ).fetchall()

    return render_template(
        "space_map.html",
        all_floors=all_floors,
        current_floor=selected_floor,
        rooms=rooms,
        highlight_id=highlight_id,
    )


# ========================================================
# 管理員專用後台：教室資料 CRUD (增、刪、改、查)
# ========================================================

@bp.route("/admin", methods=["GET"])
@admin_required
def admin_list():
    """管理員專用教室管理清單頁面。"""
    db = get_db()
    q = request.args.get("q", "").strip()
    selected_floor = request.args.get("floor", "").strip()

    conditions = []
    params = []

    if q:
        conditions.append("(code LIKE ? OR name LIKE ? OR equipment LIKE ?)")
        wildcard = f"%{q}%"
        params.extend([wildcard, wildcard, wildcard])

    if selected_floor:
        conditions.append("floor = ?")
        params.append(selected_floor)

    where_clause = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    rooms = db.execute(
        f"""SELECT id, code, name, floor, capacity, room_type, equipment,
                   panorama_url, floor_plan_x, floor_plan_y, is_active
            FROM rooms
            {where_clause}
            ORDER BY floor ASC, code ASC""",
        params,
    ).fetchall()

    all_floors = [r["floor"] for r in db.execute("SELECT DISTINCT floor FROM rooms ORDER BY floor ASC").fetchall()]

    total_rooms = len(rooms)
    active_rooms = sum(1 for r in rooms if r["is_active"] == 1)
    pano_rooms = sum(1 for r in rooms if r["panorama_url"])

    return render_template(
        "space_admin.html",
        rooms=rooms,
        all_floors=all_floors,
        selected_floor=selected_floor,
        q=q,
        total_rooms=total_rooms,
        active_rooms=active_rooms,
        pano_rooms=pano_rooms,
    )


@bp.route("/admin/add", methods=["GET", "POST"])
@admin_required
def admin_add():
    """管理員新增教室。"""
    db = get_db()
    error = None

    if request.method == "POST":
        code = request.form.get("code", "").strip()
        name = request.form.get("name", "").strip()
        floor = request.form.get("floor", "").strip()
        capacity = request.form.get("capacity", "").strip()
        room_type = request.form.get("room_type", "一般教室").strip()
        equipment = request.form.get("equipment", "").strip()
        description = request.form.get("description", "").strip()
        panorama_url = request.form.get("panorama_url", "").strip()
        floor_plan_x = request.form.get("floor_plan_x", "50.0").strip()
        floor_plan_y = request.form.get("floor_plan_y", "50.0").strip()
        is_active = 1 if request.form.get("is_active") == "1" else 0

        if not code or not name or not floor or not capacity:
            error = "請填寫所有必填欄位（教室編號、空間名稱、樓層、容納人數）。"
        elif not capacity.isdigit() or int(capacity) <= 0:
            error = "容納人數必須是大於 0 的正整數。"
        else:
            existing = db.execute("SELECT id FROM rooms WHERE code = ?", (code,)).fetchone()
            if existing:
                error = f"教室編號「{code}」已經存在，請使用不同編號。"
            else:
                try:
                    fx = float(floor_plan_x)
                    fy = float(floor_plan_y)
                except ValueError:
                    fx, fy = 50.0, 50.0

                with db:
                    db.execute(
                        """INSERT INTO rooms (code, name, floor, capacity, room_type,
                                              equipment, description, panorama_url,
                                              floor_plan_x, floor_plan_y, is_active)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (code, name, floor, int(capacity), room_type, equipment, description,
                         panorama_url, fx, fy, is_active),
                    )
                flash(f"教室「{code} {name}」新增成功！", "success")
                return redirect(url_for("spaces.admin_list"))

    return render_template("space_form.html", action="add", room=None, error=error)


@bp.route("/admin/edit/<int:room_id>", methods=["GET", "POST"])
@admin_required
def admin_edit(room_id):
    """管理員編輯教室（含更新 360 照片連結與平面圖坐標）。"""
    db = get_db()
    room = db.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    if room is None:
        abort(404)

    error = None
    if request.method == "POST":
        code = request.form.get("code", "").strip()
        name = request.form.get("name", "").strip()
        floor = request.form.get("floor", "").strip()
        capacity = request.form.get("capacity", "").strip()
        room_type = request.form.get("room_type", "一般教室").strip()
        equipment = request.form.get("equipment", "").strip()
        description = request.form.get("description", "").strip()
        panorama_url = request.form.get("panorama_url", "").strip()
        floor_plan_x = request.form.get("floor_plan_x", "50.0").strip()
        floor_plan_y = request.form.get("floor_plan_y", "50.0").strip()
        is_active = 1 if request.form.get("is_active") == "1" else 0

        if not code or not name or not floor or not capacity:
            error = "請填寫所有必填欄位（教室編號、空間名稱、樓層、容納人數）。"
        elif not capacity.isdigit() or int(capacity) <= 0:
            error = "容納人數必須是大於 0 的正整數。"
        else:
            existing = db.execute("SELECT id FROM rooms WHERE code = ? AND id != ?", (code, room_id)).fetchone()
            if existing:
                error = f"教室編號「{code}」已被其他教室使用，請換一個編號。"
            else:
                try:
                    fx = float(floor_plan_x)
                    fy = float(floor_plan_y)
                except ValueError:
                    fx, fy = room["floor_plan_x"], room["floor_plan_y"]

                with db:
                    db.execute(
                        """UPDATE rooms
                           SET code = ?, name = ?, floor = ?, capacity = ?, room_type = ?,
                               equipment = ?, description = ?, panorama_url = ?,
                               floor_plan_x = ?, floor_plan_y = ?, is_active = ?
                           WHERE id = ?""",
                        (code, name, floor, int(capacity), room_type, equipment, description,
                         panorama_url, fx, fy, is_active, room_id),
                    )
                flash(f"教室「{code}」資料更新成功！", "success")
                return redirect(url_for("spaces.admin_list"))

    return render_template("space_form.html", action="edit", room=room, error=error)


@bp.post("/admin/delete/<int:room_id>")
@admin_required
def admin_delete(room_id):
    """管理員刪除教室。"""
    db = get_db()
    room = db.execute("SELECT code, name FROM rooms WHERE id = ?", (room_id,)).fetchone()
    if room:
        with db:
            db.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
        flash(f"教室「{room['code']} {room['name']}」已成功刪除。", "info")
    return redirect(url_for("spaces.admin_list"))


@bp.post("/admin/toggle/<int:room_id>")
@admin_required
def admin_toggle(room_id):
    """快速切換教室開放借用或停用維護狀態。"""
    db = get_db()
    with db:
        db.execute(
            "UPDATE rooms SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END WHERE id = ?",
            (room_id,),
        )
    return redirect(url_for("spaces.admin_list"))


@bp.get("/<int:room_id>")
def detail(room_id):
    """前台免登入教室詳細資訊頁，含 360 全景照片瀏覽器與硬體設備規格。"""
    db = get_db()
    room = db.execute(
        """SELECT id, code, name, floor, capacity, room_type, equipment, description,
                  image_url, panorama_url, floor_plan_x, floor_plan_y, is_active
           FROM rooms WHERE id = ?""",
        (room_id,),
    ).fetchone()

    if room is None:
        abort(404)

    # 查詢該空間近期的已核准預約紀錄（展現模組整合）
    upcoming_bookings = db.execute(
        """SELECT bookings.booking_date, bookings.starts_at, bookings.ends_at,
                  bookings.borrowed_items, users.name as user_name
           FROM bookings
           JOIN users ON users.id = bookings.user_id
           WHERE bookings.room_id = ? AND bookings.status = '已核准'
           ORDER BY bookings.starts_at ASC
           LIMIT 5""",
        (room_id,),
    ).fetchall()

    return render_template(
        "space_detail.html",
        room=room,
        upcoming_bookings=upcoming_bookings,
    )
