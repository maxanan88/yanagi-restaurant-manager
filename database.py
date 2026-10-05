from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import math
import threading
import unicodedata
import streamlit as st
import pandas as pd
import libsql

# เวลาไทยจริง (ห้ามใช้ datetime.now() เฉยๆ เพราะเซิร์ฟเวอร์ Streamlit Cloud รันเวลา UTC
# ถ้าไม่ล็อก timezone ตรงนี้ เวลาออเดอร์/เวลาเรียกพนักงานจะเพี้ยนไป 7 ชั่วโมงจากเวลาไทยจริง)
BANGKOK_TZ = ZoneInfo("Asia/Bangkok")


# รูปแบบเวลาที่เก็บในฐานข้อมูลและโชว์ให้ครัว: 2026-10-04 23:02:49 (ไม่มีไมโครวินาที ไม่มี +07:00)
# เก็บเป็นเวลาไทยล้วนๆ ด้วย เพราะ SQLite strftime() จะแปลง "+07:00" เป็น UTC ทำให้ยอดขายช่วง 00:00-06:59
# ของวันที่ 1 ถูกนับเป็นเดือนก่อนหน้าในรายงานรายเดือน
TS_FORMAT = "%Y-%m-%d %H:%M:%S"


def now_bangkok():
    return datetime.now(BANGKOK_TZ)


def now_bangkok_str():
    return now_bangkok().strftime(TS_FORMAT)


def fmt_ts(value):
    """ตัดเวลาให้เหลือ YYYY-MM-DD HH:MM:SS (รองรับแถวเก่าที่ยังมี .025878+07:00 ติดมา)"""
    if value is None:
        return ""
    return str(value).replace("T", " ")[:19]

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
            days_available TEXT,
            zones TEXT
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
    if "zones" not in existing_columns:
        # zones: รายชื่อโซนที่เมนูนี้ขายได้ คั่นด้วยจุลภาค เช่น "ramen,buffet_izakaya"
        # ใส่ "all" ได้ถ้าอยากให้โชว์ทุกโซนอัตโนมัติ (ใช้กับเครื่องดื่มทั่วไป)
        conn.execute("ALTER TABLE menu_prices ADD COLUMN zones TEXT")

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
    # status = สถานะฝั่งครัว (อาหาร), drink_status = สถานะฝั่งแคชเชียร์ (เครื่องดื่ม) แยกกันคนละคิว
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_no TEXT NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'รอทำ',
            drink_status TEXT NOT NULL DEFAULT 'รอทำ'
        )
    """)
    orders_columns = [row[1] for row in conn.execute("PRAGMA table_info(orders)").fetchall()]
    if "drink_status" not in orders_columns:
        conn.execute("ALTER TABLE orders ADD COLUMN drink_status TEXT NOT NULL DEFAULT 'รอทำ'")

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

    # ---- v4: โซนของออเดอร์ + หมายเหตุรายรายการ + index สำหรับ query หน้าครัว ----
    orders_columns = [row[1] for row in conn.execute("PRAGMA table_info(orders)").fetchall()]
    if "zone" not in orders_columns:
        conn.execute("ALTER TABLE orders ADD COLUMN zone TEXT")
    order_items_columns = [row[1] for row in conn.execute("PRAGMA table_info(order_items)").fetchall()]
    if "note" not in order_items_columns:
        conn.execute("ALTER TABLE order_items ADD COLUMN note TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_drink_status ON orders(drink_status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_table_created ON orders(table_no, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_staff_calls_room ON staff_calls(room_name, status)")

    # ทำความสะอาดเวลาเก่าที่มีไมโครวินาที/+07:00 (idempotent: แถวที่สะอาดแล้วจะไม่ถูกแตะ)
    # ค่าเดิมเป็นเวลาไทยอยู่แล้ว การตัดเหลือ 19 ตัวอักษรจึงไม่เปลี่ยนความหมายของเวลา
    for _table, _column in (("orders", "created_at"), ("staff_calls", "created_at"), ("sales_log", "date")):
        conn.execute(
            f"UPDATE {_table} SET {_column} = substr(replace({_column}, 'T', ' '), 1, 19) WHERE length({_column}) > 19"
        )

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


def delete_all_transactions():
    """ลบรายการรับ-จ่ายทางการเงินทั้งหมดทีเดียว (ลบถาวร กู้คืนไม่ได้)"""
    conn = get_connection()
    conn.execute("DELETE FROM transactions")
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


def delete_all_inventory():
    """ลบวัตถุดิบในสต็อกทั้งหมดทีเดียว (ลบถาวร กู้คืนไม่ได้)"""
    conn = get_connection()
    conn.execute("DELETE FROM inventory")
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

def set_menu_price(menu_name, price, category="อื่นๆ", image_bytes=None, description=None, is_recommended=False, size_group=None, size_label=None, time_from=None, time_to=None, days_available=None, zones=None):
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
    zones: string คั่นด้วยจุลภาค ของ zone key ที่เมนูนี้ขายได้ เช่น "ramen,buffet_izakaya"
        ค่าที่ใช้ได้: ramen / buffet_izakaya / vip_nabe_buffet / vip_nabe_alacarte / all (all = โชว์ทุกโซน)
        ถ้าไม่ใส่ (None) = โชว์ทุกโซนเหมือนกัน (เผื่อเมนูเก่าที่ยังไม่ได้ตั้งโซน จะได้ไม่หายไปจากระบบ)
    """
    conn = get_connection()
    # กัน bug ข้อความไทยเหมือนกันเป๊ะตาเห็นแต่ Unicode composition ต่างกัน (พิมพ์จากมือถือ/คัดลอกจากคนละที่มา)
    # ทำให้ระบบเทียบ/ค้นข้อความไม่เจอ ทั้งที่จริงคือคำเดียวกัน — ล็อกให้เป็นรูปแบบเดียวกันเสมอตอนบันทึก
    menu_name = unicodedata.normalize("NFC", str(menu_name)) if menu_name else menu_name
    category = unicodedata.normalize("NFC", str(category)) if category else category
    conn.execute("""
        INSERT INTO menu_prices (menu_name, price, category, image, description, is_recommended, size_group, size_label, time_from, time_to, days_available, zones)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            days_available = excluded.days_available,
            zones = excluded.zones
    """, (menu_name, price, category, image_bytes, description, 1 if is_recommended else 0, size_group, size_label, time_from, time_to, days_available, zones))
    conn.commit()
    conn.close()
    get_menu_list.clear()  # ล้างแคชเมนู ให้เห็นการแก้ไขทันที ไม่ต้องรอ 15 วิ


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
    get_menu_list.clear()


def delete_all_menu_items():
    """ลบเมนูทั้งหมดทีเดียว — ใช้ตอนอยากเคลียร์ของเก่าทั้งหมดก่อนนำเข้าไฟล์ CSV ชุดใหม่ทับ (ลบถาวร กู้คืนไม่ได้)"""
    conn = get_connection()
    conn.execute("DELETE FROM menu_prices")
    conn.commit()
    conn.close()
    get_menu_list.clear()


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


def delete_all_sales():
    """ลบประวัติยอดขายทั้งหมดทีเดียว (ลบถาวร กู้คืนไม่ได้ — ใช้ตอนอยากล้างข้อมูลรายงานยอดขายเริ่มนับใหม่)"""
    conn = get_connection()
    conn.execute("DELETE FROM sales_log")
    conn.commit()
    conn.close()


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


@st.cache_data(ttl=15, show_spinner=False)
def get_menu_list():
    """เอาไว้แสดงเมนู+ราคา+รูป+คำอธิบาย+แนะนำ+กลุ่มไซส์+ช่วงเวลา ให้ลูกค้าดูตอนสั่งอาหารผ่าน QR
    แคชไว้ 15 วินาที ลดเวลาโหลดหน้าเว็บ (เมนูไม่ได้เปลี่ยนบ่อยขนาดต้องเช็คทุกครั้งที่กดปุ่ม)"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT menu_name, price, category, image, description, is_recommended, size_group, size_label, time_from, time_to, days_available, zones FROM menu_prices ORDER BY menu_name"
    ).fetchall()
    conn.close()
    return pd.DataFrame(rows, columns=["menu_name", "price", "category", "image", "description", "is_recommended", "size_group", "size_label", "time_from", "time_to", "days_available", "zones"])


# ---------------- Orders (สั่งอาหารผ่าน QR) ----------------
# เส้นทาง "ออเดอร์/เรียกพนักงาน" ถูกเรียกถี่ที่สุด (หน้าครัว/แคชเชียร์รีเฟรชทุก 5 วินาที) จึงใช้ connection ร่วมกัน
# ผ่าน st.cache_resource แทนการเปิดใหม่ทุกฟังก์ชัน ส่วนหน้าแอดมินที่ใช้นานๆ ครั้ง (สต็อก/เมนู/การเงิน) คงเดิมไว้
# ข้างบนทั้งหมด ไม่แตะ เพื่อไม่ให้ของที่ใช้งานได้จริงพัง

ORDER_WAITING = "รอทำ"
ORDER_COOKING = "กำลังทำ"
ORDER_DONE = "เสร็จแล้ว"

ORDER_COOLDOWN_SECONDS = 15          # โต๊ะเดียวกันสั่งรอบใหม่ได้ทุกกี่วินาที (กันยิงออเดอร์รัว)
MAX_WAITING_ORDERS_PER_TABLE = 6     # โต๊ะเดียวมีออเดอร์ "รอทำ" ค้างได้สูงสุดกี่ออเดอร์
STAFF_CALL_COOLDOWN_SECONDS = 30     # ห้องเดียวกดเรียกพนักงานซ้ำได้ทุกกี่วินาที (และไม่สร้างซ้ำถ้ายังไม่มีคนรับทราบ)
NOTE_MAX_LENGTH = 100                # ความยาวหมายเหตุสูงสุดต่อรายการ

_DB_LOCK = threading.RLock()


class OrderRejected(Exception):
    """ออเดอร์ถูกปฏิเสธด้วยเหตุผลทางธุรกิจ (ไม่ใช่ error ของระบบ) code: empty / cooldown / too_many_waiting"""

    def __init__(self, code, retry_after=0):
        super().__init__(code)
        self.code = code
        self.retry_after = retry_after


@st.cache_resource(show_spinner=False)
def _shared_connection():
    return get_connection()


def _run(fn):
    """รันงานฐานข้อมูลเป็น transaction เดียวบน connection ร่วม
    - ล็อกกัน thread ของ Streamlit หลาย session ใช้ connection เดียวพร้อมกันแล้ว transaction ปนกัน
    - ถ้า connection หมดอายุ/หลุด (Turso ปิด stream ที่ว่างนาน) จะเชื่อมต่อใหม่แล้วลองอีกครั้ง 1 รอบ
    - OrderRejected ไม่ใช่ error ของระบบ จึงไม่ retry"""
    with _DB_LOCK:
        last_error = None
        for _attempt in range(2):
            conn = _shared_connection()
            try:
                result = fn(conn)
                conn.commit()
                return result
            except OrderRejected:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise
            except Exception as exc:
                last_error = exc
                try:
                    conn.rollback()
                except Exception:
                    pass
                _shared_connection.clear()
        raise last_error


def clean_note(note):
    """หมายเหตุจากลูกค้า: ตัดอักขระควบคุม ยุบช่องว่าง จำกัดความยาว (กันรกหน้าครัว/ใบสั่งพิมพ์)"""
    if not note:
        return ""
    text = "".join(ch for ch in str(note) if ch >= " " and ch != "\x7f")
    return " ".join(text.split())[:NOTE_MAX_LENGTH]


def _status_column(kind):
    if kind == "food":
        return "status"
    if kind == "drink":
        return "drink_status"
    raise ValueError("kind must be 'food' or 'drink'")


def create_order(table_no, items, zone=None):
    """
    items: list ของ (menu_name, qty, price, is_drink) หรือ (menu_name, qty, price, is_drink, note)
    is_drink ใช้ตัดสินสถานะเริ่มต้น: ถ้าออเดอร์ไม่มีเครื่องดื่มเลย drink_status จะเป็น "เสร็จแล้ว" ทันที (และเช่นกันฝั่งอาหาร)

    กันสแปมที่ระดับฐานข้อมูล (ไม่ใช่แค่ session ของเบราว์เซอร์ ซึ่งเปิดแท็บใหม่ก็หลบได้):
      - โต๊ะเดียวกันสั่งซ้ำภายใน ORDER_COOLDOWN_SECONDS วินาที -> OrderRejected("cooldown")
      - โต๊ะเดียวกันมีออเดอร์รอทำค้างเกิน MAX_WAITING_ORDERS_PER_TABLE -> OrderRejected("too_many_waiting")
    การเช็คกับการ INSERT อยู่ในคำสั่งเดียว (INSERT ... SELECT ... WHERE NOT EXISTS) จึงไม่มีช่องให้สองคำขอลอดพร้อมกัน
    """
    table_no = str(table_no).strip()
    clean_items = []
    for item in items or []:
        menu_name, qty, price, is_drink = item[0], int(item[1]), float(item[2]), bool(item[3])
        note = clean_note(item[4]) if len(item) > 4 else ""
        if qty > 0:
            clean_items.append((menu_name, qty, price, is_drink, note))
    if not table_no or not clean_items:
        raise OrderRejected("empty")

    has_food = any(not is_drink for _, _, _, is_drink, _ in clean_items)
    has_drink = any(is_drink for _, _, _, is_drink, _ in clean_items)
    initial_status = ORDER_WAITING if has_food else ORDER_DONE
    initial_drink_status = ORDER_WAITING if has_drink else ORDER_DONE

    now = now_bangkok()
    now_str = now.strftime(TS_FORMAT)
    cutoff = (now - timedelta(seconds=ORDER_COOLDOWN_SECONDS)).strftime(TS_FORMAT)

    def _tx(conn):
        inserted = conn.execute(
            """
            INSERT INTO orders (table_no, created_at, status, drink_status, zone)
            SELECT ?, ?, ?, ?, ?
            WHERE NOT EXISTS (SELECT 1 FROM orders WHERE table_no = ? AND created_at > ?)
              AND (SELECT COUNT(*) FROM orders WHERE table_no = ? AND (status = ? OR drink_status = ?)) < ?
            RETURNING id
            """,
            (table_no, now_str, initial_status, initial_drink_status, zone or None,
             table_no, cutoff,
             table_no, ORDER_WAITING, ORDER_WAITING, MAX_WAITING_ORDERS_PER_TABLE),
        ).fetchall()

        if not inserted:
            last = conn.execute("SELECT MAX(created_at) FROM orders WHERE table_no = ?", (table_no,)).fetchone()[0]
            if last and str(last)[:19] > cutoff:
                elapsed = (now.replace(tzinfo=None) - datetime.strptime(str(last)[:19], TS_FORMAT)).total_seconds()
                raise OrderRejected("cooldown", max(1, math.ceil(ORDER_COOLDOWN_SECONDS - elapsed)))
            raise OrderRejected("too_many_waiting")

        order_id = inserted[0][0]
        placeholders = ",".join(["(?, ?, ?, ?, ?)"] * len(clean_items))
        params = []
        for menu_name, qty, price, _is_drink, note in clean_items:
            params.extend([order_id, menu_name, qty, price, note or None])
        conn.execute(
            f"INSERT INTO order_items (order_id, menu_name, qty, price, note) VALUES {placeholders}",
            tuple(params),
        )
        return order_id

    return _run(_tx)


_BOARD_COLUMNS = ["order_id", "table_no", "created_at", "status", "zone", "menu_name", "qty", "price", "note", "category"]


def get_active_order_board(kind):
    """ออเดอร์ที่ยังไม่เสร็จพร้อมรายการทั้งหมดใน query เดียว (JOIN) — แทนการวน get_order_items() ทีละออเดอร์ (N+1)
    kind="food" -> ฝั่งครัว (status) | kind="drink" -> ฝั่งแคชเชียร์ (drink_status)
    คอลัมน์ status ในผลลัพธ์คือสถานะของฝั่งที่ขอ การแยกอาหาร/เครื่องดื่มทำฝั่งแอปด้วย category เหมือนเดิม"""
    column = _status_column(kind)

    def _q(conn):
        return conn.execute(
            f"""
            SELECT o.id, o.table_no, o.created_at, o.{column}, o.zone,
                   oi.menu_name, oi.qty, oi.price, oi.note, mp.category
            FROM orders o
            JOIN order_items oi ON oi.order_id = o.id
            LEFT JOIN menu_prices mp ON mp.menu_name = oi.menu_name
            WHERE o.{column} != ?
            ORDER BY o.created_at ASC, o.id ASC, oi.id ASC
            """,
            (ORDER_DONE,),
        ).fetchall()

    return pd.DataFrame(_run(_q), columns=_BOARD_COLUMNS)


def get_active_orders():
    """ออเดอร์ที่ฝั่งครัว (อาหาร) ยังไม่เสร็จ — ใช้นับในหน้าหลัก"""
    def _q(conn):
        return conn.execute(
            "SELECT id, table_no, created_at, status FROM orders WHERE status != ? ORDER BY created_at ASC, id ASC",
            (ORDER_DONE,),
        ).fetchall()
    return pd.DataFrame(_run(_q), columns=["id", "table_no", "created_at", "status"])


def get_active_drink_orders():
    """ออเดอร์ที่ฝั่งแคชเชียร์ (เครื่องดื่ม) ยังไม่เสร็จ"""
    def _q(conn):
        return conn.execute(
            "SELECT id, table_no, created_at, drink_status FROM orders WHERE drink_status != ? ORDER BY created_at ASC, id ASC",
            (ORDER_DONE,),
        ).fetchall()
    return pd.DataFrame(_run(_q), columns=["id", "table_no", "created_at", "drink_status"])


def get_active_table_numbers():
    """โต๊ะที่ยังมีออเดอร์ค้างอยู่ (อาหารหรือเครื่องดื่มอย่างใดอย่างหนึ่งยังไม่เสร็จ)"""
    def _q(conn):
        return conn.execute(
            "SELECT DISTINCT table_no FROM orders WHERE status != ? OR drink_status != ?",
            (ORDER_DONE, ORDER_DONE),
        ).fetchall()
    return [r[0] for r in _run(_q)]


def get_order_items(order_id):
    """คืนรายการสินค้าของออเดอร์ พร้อมหมวดหมู่และหมายเหตุ"""
    def _q(conn):
        return conn.execute(
            """
            SELECT oi.id, oi.order_id, oi.menu_name, oi.qty, oi.price, mp.category, oi.note
            FROM order_items oi
            LEFT JOIN menu_prices mp ON oi.menu_name = mp.menu_name
            WHERE oi.order_id = ?
            ORDER BY oi.id
            """,
            (order_id,),
        ).fetchall()
    return pd.DataFrame(_run(_q), columns=["id", "order_id", "menu_name", "qty", "price", "category", "note"])


def get_active_order_items_all_tables():
    """รายการของทุกโต๊ะที่ยังมีออเดอร์ค้าง ใน query เดียว (แทนการ query ทีละโต๊ะ) เอาไว้ทำหน้าสรุปยอดต่อโต๊ะ"""
    def _q(conn):
        return conn.execute(
            """
            SELECT o.table_no, oi.menu_name, oi.qty, oi.price
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.id
            WHERE o.status != ? OR o.drink_status != ?
            """,
            (ORDER_DONE, ORDER_DONE),
        ).fetchall()
    return pd.DataFrame(_run(_q), columns=["table_no", "menu_name", "qty", "price"])


def get_active_order_items_by_table(table_no):
    """รวมรายการจากทุกออเดอร์ที่ยังไม่เสร็จของโต๊ะนั้น (คงไว้เผื่อโค้ดเดิมเรียกใช้)"""
    def _q(conn):
        return conn.execute(
            """
            SELECT oi.menu_name, oi.qty, oi.price
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.id
            WHERE o.table_no = ? AND (o.status != ? OR o.drink_status != ?)
            """,
            (table_no, ORDER_DONE, ORDER_DONE),
        ).fetchall()
    return pd.DataFrame(_run(_q), columns=["menu_name", "qty", "price"])


def _update_status(kind, order_id, status):
    """เปลี่ยนสถานะได้เฉพาะออเดอร์ที่ยังไม่ปิด — กันหน้าจอเก่า/อีกเครื่องกด "เริ่มทำ" ดันออเดอร์ที่เสร็จแล้วกลับมา
    (ถ้าถอยสถานะได้ ปุ่ม "เสร็จแล้ว" จะบันทึกยอดขายซ้ำอีกรอบ)"""
    column = _status_column(kind)

    def _tx(conn):
        rows = conn.execute(
            f"UPDATE orders SET {column} = ? WHERE id = ? AND {column} != ? RETURNING id",
            (status, order_id, ORDER_DONE),
        ).fetchall()
        return len(rows) > 0

    return _run(_tx)


def update_order_status(order_id, status):
    return _update_status("food", order_id, status)


def update_drink_status(order_id, status):
    return _update_status("drink", order_id, status)


def complete_order(order_id, kind, is_drink_category_fn):
    """ปิดออเดอร์ฝั่งอาหาร/เครื่องดื่ม พร้อมบันทึกยอดขาย ใน transaction เดียว และบันทึก "ครั้งเดียว" เท่านั้น
    ลำดับ: UPDATE ... WHERE status != 'เสร็จแล้ว' ก่อน (จองสิทธิ์ปิดออเดอร์) แล้วค่อยเขียน sales_log
    ถ้าสองเครื่องกดพร้อมกัน/กดซ้ำ จะมีแค่คำสั่งเดียวที่ UPDATE ได้จริง ที่เหลือได้ False และไม่เขียนยอดซ้ำ
    คืนค่า True = ปิดออเดอร์ครั้งนี้สำเร็จ, False = ออเดอร์ถูกปิดไปแล้ว (หรือไม่มีอยู่)"""
    column = _status_column(kind)
    want_drink = kind == "drink"
    sale_time = now_bangkok_str()

    def _tx(conn):
        claimed = conn.execute(
            f"UPDATE orders SET {column} = ? WHERE id = ? AND {column} != ? RETURNING id",
            (ORDER_DONE, order_id, ORDER_DONE),
        ).fetchall()
        if not claimed:
            return False

        rows = conn.execute(
            """
            SELECT oi.menu_name, oi.qty, oi.price, mp.category
            FROM order_items oi
            LEFT JOIN menu_prices mp ON oi.menu_name = mp.menu_name
            WHERE oi.order_id = ?
            """,
            (order_id,),
        ).fetchall()
        sales = [
            (sale_time, menu_name, int(qty), qty * price)
            for menu_name, qty, price, category in rows
            if bool(is_drink_category_fn(category)) == want_drink
        ]
        if sales:
            placeholders = ",".join(["(?, ?, ?, ?)"] * len(sales))
            params = tuple(value for sale in sales for value in sale)
            conn.execute(
                f"INSERT INTO sales_log (date, menu_name, qty_sold, total_price) VALUES {placeholders}",
                params,
            )
        return True

    return _run(_tx)


def delete_order(order_id):
    """ลบออเดอร์นี้ทั้งอัน (ใช้ลบออเดอร์ทดสอบ หรือออเดอร์ที่สั่งผิด/ซ้ำ) — ลบถาวร กู้คืนไม่ได้"""
    def _tx(conn):
        conn.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
        conn.execute("DELETE FROM orders WHERE id = ?", (order_id,))
    _run(_tx)


def delete_orders_by_table(table_no):
    """ลบออเดอร์ทั้งหมดของโต๊ะนี้ทีเดียว (ทั้งที่เสร็จแล้วและยังไม่เสร็จ) — ลบถาวร กู้คืนไม่ได้"""
    def _tx(conn):
        conn.execute("DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE table_no = ?)", (table_no,))
        conn.execute("DELETE FROM orders WHERE table_no = ?", (table_no,))
    _run(_tx)


def delete_all_orders():
    """ลบออเดอร์ทั้งหมดทีเดียว (เอาไว้เคลียร์ข้อมูลทดสอบก่อนเปิดใช้งานจริง) — ลบถาวร กู้คืนไม่ได้"""
    def _tx(conn):
        conn.execute("DELETE FROM order_items")
        conn.execute("DELETE FROM orders")
    _run(_tx)


# ---------------- Staff calls (ปุ่มเรียกพนักงานจากห้อง VIP) ----------------

def create_staff_call(room_name):
    """คืน True ถ้าสร้างการเรียกใหม่ได้ / False ถ้าถูกกันซ้ำ
    กันซ้ำ 2 ชั้น: ห้องนี้ยังมีการเรียกที่ยังไม่มีคนรับทราบ หรือเพิ่งเรียกไปไม่ถึง STAFF_CALL_COOLDOWN_SECONDS วินาที"""
    room_name = str(room_name).strip()[:40]
    now = now_bangkok()
    cutoff = (now - timedelta(seconds=STAFF_CALL_COOLDOWN_SECONDS)).strftime(TS_FORMAT)

    def _tx(conn):
        rows = conn.execute(
            """
            INSERT INTO staff_calls (room_name, created_at, status)
            SELECT ?, ?, 'pending'
            WHERE NOT EXISTS (
                SELECT 1 FROM staff_calls WHERE room_name = ? AND (status = 'pending' OR created_at > ?)
            )
            RETURNING id
            """,
            (room_name, now.strftime(TS_FORMAT), room_name, cutoff),
        ).fetchall()
        return len(rows) > 0

    return _run(_tx)


def get_pending_staff_calls():
    def _q(conn):
        return conn.execute(
            "SELECT id, room_name, created_at, status FROM staff_calls WHERE status = 'pending' ORDER BY created_at ASC, id ASC"
        ).fetchall()
    return pd.DataFrame(_run(_q), columns=["id", "room_name", "created_at", "status"])


def acknowledge_staff_call(call_id):
    def _tx(conn):
        conn.execute("UPDATE staff_calls SET status = 'acknowledged' WHERE id = ? AND status = 'pending'", (call_id,))
    _run(_tx)
