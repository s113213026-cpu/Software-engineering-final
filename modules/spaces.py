from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

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
