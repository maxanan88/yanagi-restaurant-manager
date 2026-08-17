import sqlite3

def get_connection():
    conn = sqlite3.connect("restaurant.db")
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # ตารางรายรับ-รายจ่าย
    cursor. execute("""
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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            menu_name TEXT NOT NULL,
            item_name REAL NOT NULL,
            quantity_used REAL NOT NULL
        )
    """)
    conn.commit()
    conn.close()
def add_transaction(date, type, category, amount, note):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO transactions (date, type, category, amount, note)
        VALUES (?, ?, ?, ?, ?)
    """, (date, type, category, amount, note))
    conn.commit()
    conn.close()
import pandas as pd

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
def add_or_update_item(item_name, quantity, unit, low_stock_threshold):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO inventory (item_name, quantity, unit, low_stock_threshold)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(item_name) DO UPDATE SET
            quantity = quantity + excluded.quantity
    """, (item_name, quantity, unit, low_stock_threshold))
    conn.commit()
    conn.close()

def get_all_inventory():
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM inventory ORDER BY item_name", conn)
    conn.close()
    return df 
def add_transaction(date, type, category, amount, note):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO transactions (date, type, category, amount, note)
        VALUES (?, ?, ?, ?, ?)
    """, (date, type, category, amount, note))
    conn.commit()
    conn.close()
def get_all_recipes():
    conn = get_connection()
    
    df = pd.read_sql_query(
        "SELECT * FROM inventory ORDER BY item_name",
        conn
    )
    
    conn.close()
    return df
def sell_menu(menu_name, qty_sold):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT item_name, quantity_used FROM recipes WHERE menu_name = ?", (menu_name,))
    ingredients = cursor.fetchall()

    for item_name, qty_per_dish in ingredients:
        total_uesd = qty_per_dish * qty_sold
        cursor.execute(
            "UPDATE inventory SET quantity = quantity - ? WHERE item_name = ?",
        )

    conn.commit()
    conn.close()
def add_recipe_item(menu_name, item_name, quantity_used):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO recipes (menu_name, item_name, quantity_used)
        VALUES (?, ?, ?)
    """, (menu_name, item_name, quantity_used))
    conn.commit()
    conn.close()