from datetime import datetime
import streamlit as st
import pandas as pd
import libsql

# ---------------- เชื่อมต่อฐานข้อมูล Turso (Cloud) ----------------
# เปลี่ยนจาก SQLite ไฟล์ในเครื่อง (หายทุกครั้งที่แอป redeploy/restart บน Streamlit Cloud)
# มาเป็นฐานข้อมูลบนคลาวด์ผ่าน Turso แทน ข้อมูลจะอยู่ถาวรไม่หายแล้ว
# ต้องตั้งค่า Secrets ใน Streamlit Cloud ก่อน (ดูคำแนะนำที่ให้ไว้):
#   [turso]
#   url = "libsql://xxxxx.turso.io"
#   auth_token = "xxxxxxxxxx"


def get_connection():
    turso_url = st.secrets["turso"]["url"]
    turso_token = st.secrets["turso"]["auth_token"]
    return libsql.connect(database=turso_url, auth_token=turso_token)


def init_db():
    conn = get_connection()

    # ตารางรายรับ-รายจ่าย
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            type TEXT NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            note TEXT
        )
    """)

    # ตารางวัตถุดิบคงคลัง
    conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT NOT NULL UNIQUE,
            quantity REAL NOT NULL,
            unit TEXT NOT NULL,
            low_stock_threshold REAL DEFAULT 0
        )
    """)

    # ตารางสูตรอาหาร (เมนูนึงใช้วัตถุดิบหลายอย่าง) — เก็บโครงสร้างไว้เผื่อใช้ในอนาคต
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            menu_name TEXT NOT NULL,
            item_name TEXT NOT NULL,
            quantity_used REAL NOT NULL
        )
    """)

    # ตารางราคาขายต่อเมนู (มีหมวดหมู่ + รูปภาพ + คำอธิบาย + แนะนำ + กลุ่มไซส์)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS menu_prices (
            menu_name TEXT PRIMARY KEY,
            price REAL NOT NULL,
            category TEXT NOT NULL DEFAULT 'อื่นๆ',
            image BLOB,
            description TEXT,
            is_recommended INTEGER NOT NULL DEFAULT 0,
            size_group TEXT,
            size_label TEXT,
            time_from TEXT,
            time_to TEXT,
            days_available TEXT
        )
    """)

    # เผื่อฐานข้อมูลเก่าที่สร้างไว้ก่อนมีคอลัมน์เหล่านี้ ให้เติมให้อัตโนมัติ
    existing_columns = [row[1] for row in conn.execute("PRAGMA table_info(menu_prices)").fetchall()]
    if "category" not in existing_columns:
        conn.execute("ALTER TABLE menu_prices ADD COLUMN category TEXT NOT NULL DEFAULT 'อื่นๆ'")
    if "image" not in existing_columns:
        conn.execute("ALTER TABLE menu_prices ADD COLUMN image BLOB")
    if "description" not in existing_columns:
        conn.execute("ALTER TABLE menu_prices ADD COLUMN description TEXT")
    if "is_recommended" not in existing_columns:
        conn.execute("ALTER TABLE menu_prices ADD COLUMN is_recommended INTEGER NOT NULL DEFAULT 0")
    if "size_group" not in existing_columns:
        conn.execute("ALTER TABLE menu_prices ADD COLUMN size_group TEXT")
    if "size_label" not in existing_columns:
        conn.execute("ALTER TABLE menu_prices ADD COLUMN size_label TEXT")
    if "time_from" not in existing_columns:
        conn.execute("ALTER TABLE menu_prices ADD COLUMN time_from TEXT")
    if "time_to" not in existing_columns:
        conn.execute("ALTER TABLE menu_prices ADD COLUMN time_to TEXT")
    if "days_available" not in existing_columns:
        conn.execute("ALTER TABLE menu_prices ADD COLUMN days_available TEXT")

    # ตารางบันทึกการขายแยกรายเมนู
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sales_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            menu_name TEXT NOT NULL,
            qty_sold INTEGER NOT NULL,
            total_price REAL NOT NULL
        )
    """)

    # ตารางออเดอร์จากลูกค้า (สแกน QR สั่งอาหาร)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_no TEXT NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'รอทำ'
        )
    """)

    # ตารางรายการอาหารในแต่ละออเดอร์
    conn.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            menu_name TEXT NOT NULL,
            qty INTEGER NOT NULL,
            price REAL NOT NULL
        )
    """)

    # ตารางเรียกพนักงาน (ปุ่มกดเรียกจากห้อง VIP)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS staff_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
        )
    """)

    conn.commit()
    conn.close()


# ---------------- Transactions (รายรับ-รายจ่าย) ----------------

def add_transaction(trans_date, trans_type, category, amount, note):
    conn = get_connection()
    conn.execute("""
        INSERT INTO transactions (date, type, category, amount, note)
        VALUES (?, ?, ?, ?, ?)
    """, (trans_date, trans_type, category, amount, note))
    conn.commit()
    conn.close()


def get_all_transactions():
    conn = get_connection()
    rows = conn.execute("SELECT id, date, type, category, amount, note FROM transactions ORDER BY date DESC").fetchall()
    conn.close()
    return pd.DataFrame(rows, columns=["id", "date", "type", "category", "amount", "note"])


def delete_transaction(transaction_id):
    conn = get_connection()
    conn.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
    conn.commit()
    conn.close()


def get_monthly_expense_by_category():
    """สรุปรายจ่ายรวมรายเดือน แยกตามหมวดหมู่ค่าใช้จ่าย (เอาไว้เทียบเดือนต่อเดือน เช่น ค่าวัตถุดิบขึ้นไหม)"""
    conn = get_connection()
    rows = conn.execute("""
        SELECT strftime('%Y-%m', date) AS month, category, SUM(amount) AS total
        FROM transactions
        WHERE type = 'รายจ่าย'
        GROUP BY month, category
        ORDER BY month
    """).fetchall()
    conn.close()
    return pd.DataFrame(rows, columns=["month", "category", "total"])


# ---------------- Inventory (วัตถุดิบคงคลัง) ----------------

def add_or_update_item(item_name, quantity, unit, low_stock_threshold, mode="add"):
    """
    mode="add"  -> เพิ่มจำนวนเข้าไปจากของเดิม (ใช้ตอนของเข้าใหม่)
    mode="set"  -> ตั้งยอดใหม่ทับของเดิมเลย (ใช้ตอนนับสต็อกจริงแล้วปรับให้ตรง)
    """
    conn = get_connection()
    if mode == "set":
        conn.execute("""
            INSERT INTO inventory (item_name, quantity, unit, low_stock_threshold)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(item_name) DO UPDATE SET
                quantity = excluded.quantity,
                unit = excluded.unit,
                low_stock_threshold = excluded.low_stock_threshold
        """, (item_name, quantity, unit, low_stock_threshold))
    else:
        conn.execute("""
            INSERT INTO inventory (item_name, quantity, unit, low_stock_threshold)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(item_name) DO UPDATE SET
                quantity = quantity + excluded.quantity,
                unit = excluded.unit,
                low_stock_threshold = excluded.low_stock_threshold
        """, (item_name, quantity, unit, low_stock_threshold))
    conn.commit()
    conn.close()


def delete_inventory_item(item_name):
    conn = get_connection()
    conn.execute("DELETE FROM inventory WHERE item_name = ?", (item_name,))
    conn.commit()
    conn.close()


def get_all_inventory():
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, item_name, quantity, unit, low_stock_threshold FROM inventory ORDER BY item_name"
    ).fetchall()
    conn.close()
    return pd.DataFrame(rows, columns=["id", "item_name", "quantity", "unit", "low_stock_threshold"])


# ---------------- Recipes (สูตรอาหาร) — เก็บไว้เผื่อใช้ในอนาคต ----------------

def add_recipe_item(menu_name, item_name, quantity_used):
    conn = get_connection()
    conn.execute("""
        INSERT INTO recipes (menu_name, item_name, quantity_used)
        VALUES (?, ?, ?)
    """, (menu_name, item_name, quantity_used))
    conn.commit()
    conn.close()


def get_all_recipes():
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, menu_name, item_name, quantity_used FROM recipes ORDER BY menu_name"
    ).fetchall()
    conn.close()
    return pd.DataFrame(rows, columns=["id", "menu_name", "item_name", "quantity_used"])


def delete_recipe_item(recipe_id):
    conn = get_connection()
    conn.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))
    conn.commit()
    conn.close()


# ---------------- Menu price + selling ----------------

def set_menu_price(menu_name, price, category="อื่นๆ", image_bytes=None, description=None, is_recommended=False, size_group=None, size_label=None, time_from=None, time_to=None, days_available=None):
    """
    image_bytes: ถ้าไม่ส่งมา (None) จะไม่ไปทับรูปเดิมที่เคยอัปโหลดไว้
    description: คำอธิบายเพิ่มเติม เช่น รายละเอียดส่วนประกอบในเซต (ไม่บังคับ)
    is_recommended: True ถ้าอยากติดป้ายแนะนำเมนูนี้ให้ลูกค้าเห็น
    size_group: ชื่อกลุ่มไซส์ (ไม่บังคับ) — แถวที่มี size_group เดียวกันจะถูกรวมแสดงเป็นเมนูเดียว ให้ลูกค้าเลือกไซส์เอง
    size_label: ป้ายไซส์ของแถวนี้ เช่น "ชามเล็ก" (ใส่คู่กับ size_group)
    time_from, time_to: ช่วงเวลาที่เมนูนี้จะโชว์ (รูปแบบ "HH:MM") ถ้าไม่ใส่ = โชว์ตลอดเวลา
    days_available: "ทุกวัน" / "วันธรรมดา" / "เสาร์-อาทิตย์" (ไม่ใส่ = ทุกวัน) เอาไว้คู่กับ time_from/time_to
        ใช้กับราคาที่เปลี่ยนตามวัน/เวลา เช่น บุฟเฟ่วันธรรมดาเปิด 14:00 vs เสาร์-อาทิตย์เปิด 12:00
        ระบบเช็คจากวันเวลาจริงอัตโนมัติ ลูกค้าเลือกเองไม่ได้
    """
    conn = get_connection()
    conn.execute("""
        INSERT INTO menu_prices (menu_name, price, category, image, description, is_recommended, size_group, size_label, time_from, time_to, days_available)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(menu_name) DO UPDATE SET
            price = excluded.price,
            category = excluded.category,
            image = COALESCE(excluded.image, menu_prices.image),
            description = excluded.description,
            is_recommended = excluded.is_recommended,
            size_group = excluded.size_group,
            size_label = excluded.size_label,
            time_from = excluded.time_from,
            time_to = excluded.time_to,
            days_available = excluded.days_available
    """, (menu_name, price, category, image_bytes, description, 1 if is_recommended else 0, size_group, size_label, time_from, time_to, days_available))
    conn.commit()
    conn.close()


def get_all_categories():
    conn = get_connection()
    rows = conn.execute("SELECT DISTINCT category FROM menu_prices ORDER BY category").fetchall()
    conn.close()
    return [row[0] for row in rows]


def delete_menu_item(menu_name):
    conn = get_connection()
    conn.execute("DELETE FROM menu_prices WHERE menu_name = ?", (menu_name,))
    conn.commit()
    conn.close()


# ---------------- Sales log (สำหรับหน้ารายงาน) ----------------

def add_sale_log(sale_date, menu_name, qty_sold, total_price):
    conn = get_connection()
    conn.execute("""
        INSERT INTO sales_log (date, menu_name, qty_sold, total_price)
        VALUES (?, ?, ?, ?)
    """, (sale_date, menu_name, qty_sold, total_price))
    conn.commit()
    conn.close()


def get_all_sales():
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, date, menu_name, qty_sold, total_price FROM sales_log ORDER BY date DESC"
    ).fetchall()
    conn.close()
    return pd.DataFrame(rows, columns=["id", "date", "menu_name", "qty_sold", "total_price"])


def get_sales_by_category():
    """สรุปยอดขายแยกตามหมวดหมู่เมนู รายเดือน (เอาไว้ดูว่าราเมง/บุฟเฟ่/อาลาคาร์ท ฯลฯ ขายได้เท่าไหร่ เทียบเป็น % ได้)"""
    conn = get_connection()
    rows = conn.execute("""
        SELECT strftime('%Y-%m', sl.date) AS month, mp.category AS category,
               SUM(sl.qty_sold) AS qty, SUM(sl.total_price) AS revenue
        FROM sales_log sl
        LEFT JOIN menu_prices mp ON sl.menu_name = mp.menu_name
        GROUP BY month, category
        ORDER BY month
    """).fetchall()
    conn.close()
    return pd.DataFrame(rows, columns=["month", "category", "qty", "revenue"])


def get_menu_price(menu_name):
    conn = get_connection()
    result = conn.execute("SELECT price FROM menu_prices WHERE menu_name = ?", (menu_name,)).fetchone()
    conn.close()
    return result[0] if result else 0


def sell_menu(menu_name, qty_sold):
    conn = get_connection()
    ingredients = conn.execute(
        "SELECT item_name, quantity_used FROM recipes WHERE menu_name = ?",
        (menu_name,)
    ).fetchall()

    for item_name, qty_per_dish in ingredients:
        total_used = qty_per_dish * qty_sold
        conn.execute(
            "UPDATE inventory SET quantity = quantity - ? WHERE item_name = ?",
            (total_used, item_name)
        )

    conn.commit()
    conn.close()


def get_menu_list():
    """เอาไว้แสดงเมนู+ราคา+รูป+คำอธิบาย+แนะนำ+กลุ่มไซส์+ช่วงเวลา ให้ลูกค้าดูตอนสั่งอาหารผ่าน QR"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT menu_name, price, category, image, description, is_recommended, size_group, size_label, time_from, time_to, days_available FROM menu_prices ORDER BY menu_name"
    ).fetchall()
    conn.close()
    return pd.DataFrame(rows, columns=["menu_name", "price", "category", "image", "description", "is_recommended", "size_group", "size_label", "time_from", "time_to", "days_available"])


# ---------------- Orders (สั่งอาหารผ่าน QR) ----------------

def create_order(table_no, items):
    """items คือ list ของ (menu_name, qty, price)"""
    conn = get_connection()
    conn.execute(
        "INSERT INTO orders (table_no, created_at, status) VALUES (?, ?, ?)",
        (table_no, str(datetime.now()), "รอทำ")
    )
    order_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    for menu_name, qty, price in items:
        conn.execute(
            "INSERT INTO order_items (order_id, menu_name, qty, price) VALUES (?, ?, ?, ?)",
            (order_id, menu_name, qty, price)
        )

    conn.commit()
    conn.close()


def get_active_orders():
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, table_no, created_at, status FROM orders WHERE status != 'เสร็จแล้ว' ORDER BY created_at ASC"
    ).fetchall()
    conn.close()
    return pd.DataFrame(rows, columns=["id", "table_no", "created_at", "status"])


def get_order_items(order_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, order_id, menu_name, qty, price FROM order_items WHERE order_id = ?", (order_id,)
    ).fetchall()
    conn.close()
    return pd.DataFrame(rows, columns=["id", "order_id", "menu_name", "qty", "price"])


def get_active_order_items_by_table(table_no):
    """รวมรายการอาหารจากทุกออเดอร์ที่ยังไม่เสร็จของโต๊ะนั้น (เผื่อลูกค้าสั่งหลายรอบ) เอาไว้ทำสรุปยอด"""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT oi.menu_name, oi.qty, oi.price
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.id
        WHERE o.table_no = ? AND o.status != 'เสร็จแล้ว'
        """,
        (table_no,)
    ).fetchall()
    conn.close()
    return pd.DataFrame(rows, columns=["menu_name", "qty", "price"])


def update_order_status(order_id, status):
    conn = get_connection()
    conn.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
    conn.commit()
    conn.close()


# ---------------- Staff calls (ปุ่มเรียกพนักงานจากห้อง VIP) ----------------

def create_staff_call(room_name):
    conn = get_connection()
    conn.execute(
        "INSERT INTO staff_calls (room_name, created_at, status) VALUES (?, ?, ?)",
        (room_name, str(datetime.now()), "pending")
    )
    conn.commit()
    conn.close()


def get_pending_staff_calls():
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, room_name, created_at, status FROM staff_calls WHERE status = 'pending' ORDER BY created_at ASC"
    ).fetchall()
    conn.close()
    return pd.DataFrame(rows, columns=["id", "room_name", "created_at", "status"])


def acknowledge_staff_call(call_id):
    conn = get_connection()
    conn.execute("UPDATE staff_calls SET status = 'acknowledged' WHERE id = ?", (call_id,))
    conn.commit()
    conn.close()
