import sqlite3
from datetime import datetime
import pandas as pd

DB_NAME = "restaurant.db"


def get_connection():
    return sqlite3.connect(DB_NAME)


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # ตารางรายรับ-รายจ่าย
    cursor.execute("""
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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT NOT NULL UNIQUE,
            quantity REAL NOT NULL,
            unit TEXT NOT NULL,
            low_stock_threshold REAL DEFAULT 0
        )
    """)

    # ตารางสูตรอาหาร (เมนูนึงใช้วัตถุดิบหลายอย่าง)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            menu_name TEXT NOT NULL,
            item_name TEXT NOT NULL,
            quantity_used REAL NOT NULL
        )
    """)

    # ตารางราคาขายต่อเมนู
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS menu_prices (
            menu_name TEXT PRIMARY KEY,
            price REAL NOT NULL
        )
    """)

    # ตารางบันทึกการขายแยกรายเมนู (ใช้ทำกราฟเมนูขายดี Top 5)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sales_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            menu_name TEXT NOT NULL,
            qty_sold INTEGER NOT NULL,
            total_price REAL NOT NULL
        )
    """)

    # ตารางออเดอร์จากลูกค้า (สแกน QR สั่งอาหาร)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_no TEXT NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'รอทำ'
        )
    """)

    # ตารางรายการอาหารในแต่ละออเดอร์
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            menu_name TEXT NOT NULL,
            qty INTEGER NOT NULL,
            price REAL NOT NULL
        )
    """)

    # เดิมลืม commit/close ตรงนี้ ทำให้บางทีตารางไม่ถูกสร้างจริง
    conn.commit()
    conn.close()


# ---------------- Transactions (รายรับ-รายจ่าย) ----------------

def add_transaction(trans_date, trans_type, category, amount, note):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO transactions (date, type, category, amount, note)
        VALUES (?, ?, ?, ?, ?)
    """, (trans_date, trans_type, category, amount, note))
    conn.commit()
    conn.close()


def get_all_transactions():
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM transactions ORDER BY date DESC", conn)
    conn.close()
    return df


def delete_transaction(transaction_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
    conn.commit()
    conn.close()


# ---------------- Inventory (วัตถุดิบคงคลัง) ----------------

def add_or_update_item(item_name, quantity, unit, low_stock_threshold):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO inventory (item_name, quantity, unit, low_stock_threshold)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(item_name) DO UPDATE SET
            quantity = quantity + excluded.quantity,
            unit = excluded.unit,
            low_stock_threshold = excluded.low_stock_threshold
    """, (item_name, quantity, unit, low_stock_threshold))
    conn.commit()
    conn.close()


def get_all_inventory():
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM inventory ORDER BY item_name", conn)
    conn.close()
    return df


# ---------------- Recipes (สูตรอาหาร) ----------------

def add_recipe_item(menu_name, item_name, quantity_used):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO recipes (menu_name, item_name, quantity_used)
        VALUES (?, ?, ?)
    """, (menu_name, item_name, quantity_used))
    conn.commit()
    conn.close()


def get_all_recipes():
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM recipes ORDER BY menu_name", conn)
    conn.close()
    return df


def delete_recipe_item(recipe_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))
    conn.commit()
    conn.close()


# ---------------- Menu price + selling ----------------

def set_menu_price(menu_name, price):
    conn = get_connection()
    cursor = conn.cursor()
    # เดิมสะกดผิดเป็น "ON CONFLTCT" ทำให้บันทึกสูตรอาหารไม่ได้เลย
    cursor.execute("""
        INSERT INTO menu_prices (menu_name, price)
        VALUES (?, ?)
        ON CONFLICT(menu_name) DO UPDATE SET price = excluded.price
    """, (menu_name, price))
    conn.commit()
    conn.close()


# ---------------- Sales log (สำหรับหน้ารายงาน) ----------------

def add_sale_log(sale_date, menu_name, qty_sold, total_price):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO sales_log (date, menu_name, qty_sold, total_price)
        VALUES (?, ?, ?, ?)
    """, (sale_date, menu_name, qty_sold, total_price))
    conn.commit()
    conn.close()


def get_all_sales():
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM sales_log ORDER BY date DESC", conn)
    conn.close()
    return df


def get_menu_price(menu_name):
    conn = get_connection()  # เดิมพิมพ์ผิดเป็น "con" ทำให้ error ตอนขายเมนู
    cursor = conn.cursor()
    cursor.execute("SELECT price FROM menu_prices WHERE menu_name = ?", (menu_name,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0


def sell_menu(menu_name, qty_sold):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT item_name, quantity_used FROM recipes WHERE menu_name = ?",
        (menu_name,)
    )
    ingredients = cursor.fetchall()

    for item_name, qty_per_dish in ingredients:
        total_used = qty_per_dish * qty_sold
        cursor.execute(
            "UPDATE inventory SET quantity = quantity - ? WHERE item_name = ?",
            (total_used, item_name)
        )

    conn.commit()
    conn.close()


def get_menu_list():
    """เอาไว้แสดงเมนู+ราคาให้ลูกค้าดูตอนสั่งอาหารผ่าน QR"""
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM menu_prices ORDER BY menu_name", conn)
    conn.close()
    return df


# ---------------- Orders (สั่งอาหารผ่าน QR) ----------------

def create_order(table_no, items):
    """items คือ list ของ (menu_name, qty, price)"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO orders (table_no, created_at, status) VALUES (?, ?, ?)",
        (table_no, str(datetime.now()), "รอทำ")
    )
    order_id = cursor.lastrowid

    for menu_name, qty, price in items:
        cursor.execute(
            "INSERT INTO order_items (order_id, menu_name, qty, price) VALUES (?, ?, ?, ?)",
            (order_id, menu_name, qty, price)
        )

    conn.commit()
    conn.close()


def get_active_orders():
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT * FROM orders WHERE status != 'เสร็จแล้ว' ORDER BY created_at ASC", conn
    )
    conn.close()
    return df


def get_order_items(order_id):
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT * FROM order_items WHERE order_id = ?", conn, params=(order_id,)
    )
    conn.close()
    return df


def update_order_status(order_id, status):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
    conn.commit()
    conn.close()
