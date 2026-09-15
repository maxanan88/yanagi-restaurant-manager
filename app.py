from datetime import datetime
import os
import io
import base64
import urllib.parse
import streamlit as st
import pandas as pd
import qrcode
import streamlit.components.v1 as components
from PIL import Image
from database import (
    init_db, add_or_update_item, delete_inventory_item, get_all_inventory,
    set_menu_price, get_menu_list, get_all_categories, delete_menu_item,
    add_sale_log, get_all_sales, get_sales_by_category,
    add_transaction, get_all_transactions, delete_transaction, get_monthly_expense_by_category,
    create_order, get_active_orders, get_order_items, get_active_order_items_by_table, update_order_status
)

# ---------------- ตั้งค่าร้าน (แก้ตรงนี้ให้เป็นร้านของพี่ได้เลย) ----------------
RESTAURANT_NAME = "YANAGI"
LOGO_EMOJI = "🍽️"
LOGO_PATH = "logo.png"  # ถ้ามีไฟล์รูปโลโก้จริง วางไว้โฟลเดอร์เดียวกับ app.py แล้วตั้งชื่อ logo.png
BACKGROUND_PATH = "background.jpg"  # ถ้ามีรูปพื้นหลัง วางไว้โฟลเดอร์เดียวกับ app.py แล้วตั้งชื่อ background.jpg (หรือ .png ก็ได้ แค่แก้นามสกุลตรงนี้)

# URL จริงของแอปตัวนี้ (ตั้งไว้ล่วงหน้า จะได้ไม่ต้องพิมพ์เองทุกครั้งตอนสร้าง QR)
APP_BASE_URL = "https://yanagi-restaurant-manager-mkxtzbrcydnej88qoxmufi.streamlit.app"

st.set_page_config(page_title=f"ระบบจัดการร้านอาหาร - {RESTAURANT_NAME}", page_icon=LOGO_EMOJI, layout="wide")


# ---------------- ธีมสี + ฟอนต์ + รูปพื้นหลัง (แดง-ทอง ตามโลโก้ YANAGI) ----------------
def _file_to_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


_background_css = f"""
    .stApp {{
        background-color: #FAF8F5;
        background-image:
            radial-gradient(circle at 0 100%, transparent 24px, rgba(166,25,46,0.07) 25px, rgba(166,25,46,0.07) 27px, transparent 28px),
            radial-gradient(circle at 50% 100%, transparent 24px, rgba(166,25,46,0.07) 25px, rgba(166,25,46,0.07) 27px, transparent 28px),
            radial-gradient(circle at 100% 100%, transparent 24px, rgba(166,25,46,0.07) 25px, rgba(166,25,46,0.07) 27px, transparent 28px);
        background-size: 60px 30px;
    }}
"""
if os.path.exists(BACKGROUND_PATH):
    _bg_ext = BACKGROUND_PATH.split(".")[-1]
    _bg_b64 = _file_to_base64(BACKGROUND_PATH)
    _background_css = f"""
        .stApp {{
            background-image: linear-gradient(rgba(250, 248, 245, 0.90), rgba(250, 248, 245, 0.90)), url("data:image/{_bg_ext};base64,{_bg_b64}");
            background-size: cover;
            background-position: center;
            background-attachment: fixed;
        }}
    """

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Serif+Thai:wght@500;600;700&family=Noto+Sans+Thai:wght@400;500;600&display=swap');

html, body, [class*="css"], .stMarkdown, .stTextInput, .stNumberInput, .stSelectbox {{
    font-family: 'Noto Sans Thai', sans-serif !important;
}}

h1, h2, h3, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {{
    font-family: 'Noto Serif Thai', serif !important;
    color: #241F1D !important;
    letter-spacing: 0.3px;
}}

.stApp {{
    background-color: #FAF8F5;
}}
{_background_css}

[data-testid="stSidebar"] {{
    background-color: #F5EDE8;
    border-right: 1px solid #E3D5CB;
}}

[data-testid="stSidebar"] h3 {{
    color: #A6192E !important;
}}

[data-testid="stSidebar"] p, [data-testid="stSidebar"] label, [data-testid="stSidebar"] span {{
    color: #4A3F38 !important;
}}

.stButton>button {{
    background-color: #A6192E;
    color: #FAF8F5;
    border: 1px solid #A6192E;
    border-radius: 6px;
    font-family: 'Noto Sans Thai', sans-serif;
    transition: all 0.15s ease;
}}
.stButton>button:hover {{
    background-color: #FAF8F5;
    color: #A6192E;
    border-color: #A6192E;
}}

[data-testid="stMetricValue"] {{
    color: #A6192E !important;
}}

[data-testid="stMetricLabel"] {{
    color: #6B5F58 !important;
}}

div[data-testid="stExpander"] {{
    background-color: #FFFFFF;
    border: 1px solid #E3D5CB;
    border-radius: 8px;
}}

div[data-testid="stVerticalBlockBorderWrapper"] {{
    border-color: #E3D5CB !important;
    border-radius: 10px !important;
    background-color: #FFFFFF;
}}

.stDataFrame {{
    border: 1px solid #E3D5CB;
    border-radius: 8px;
}}

hr {{
    border-color: #E3D5CB !important;
}}

p, span, label, .stMarkdown, .stCaption {{
    color: #4A3F38;
}}
</style>
""", unsafe_allow_html=True)



@st.cache_resource
def _init_db_once():
    init_db()
    return True


_init_db_once()


def complete_order(order_id, table_no):
    """ตอนกด 'เสร็จแล้ว' ในหน้าครัว: บันทึกลงรายงานยอดขายเท่านั้น (สต็อกจัดการแยกต่างหาก)"""
    items_df = get_order_items(order_id)
    sale_time = str(datetime.now())
    for _, item in items_df.iterrows():
        line_total = item["qty"] * item["price"]
        add_sale_log(sale_time, item["menu_name"], int(item["qty"]), line_total)
    update_order_status(order_id, "เสร็จแล้ว")


def print_kitchen_ticket(order_row, items_df):
    """เปิดหน้าต่างพิมพ์ (ผ่านเบราว์เซอร์) เป็นใบสั่งอาหารขนาดกระดาษม้วน 80mm ให้ครัว
    หมายเหตุ: เครื่องพิมพ์ใบเสร็จต้องติดตั้งเป็นเครื่องพิมพ์ปกติบนเครื่องที่เปิดหน้านี้อยู่ก่อน"""
    rows_html = "".join(
        f"<tr><td>{r['menu_name']}</td><td style='text-align:right; white-space:nowrap'>x{int(r['qty'])}</td></tr>"
        for _, r in items_df.iterrows()
    )
    html = f"""
    <html>
    <head>
    <style>
        @media print {{
            @page {{ size: 80mm auto; margin: 2mm; }}
        }}
        body {{ font-family: sans-serif; width: 74mm; margin: 0 auto; font-size: 15px; }}
        h2 {{ text-align: center; margin: 4px 0; }}
        .meta {{ font-size: 13px; margin-bottom: 6px; text-align: center; }}
        hr {{ border: none; border-top: 1px dashed #000; margin: 6px 0; }}
        table {{ width: 100%; border-collapse: collapse; }}
        td {{ padding: 3px 0; border-bottom: 1px dashed #000; font-size: 15px; }}
    </style>
    </head>
    <body onload="window.print()">
        <h2>{RESTAURANT_NAME}</h2>
        <div class="meta">ใบสั่งอาหาร (ครัว)</div>
        <hr>
        <div class="meta" style="text-align:left; font-size:15px; font-weight:bold">
            โต๊ะ {order_row['table_no']} — ออเดอร์ #{order_row['id']}
        </div>
        <div class="meta" style="text-align:left">{order_row['created_at']}</div>
        <hr>
        <table>{rows_html}</table>
    </body>
    </html>
    """
    components.html(html, height=0, width=0)


# ================= หน้าสั่งอาหารสำหรับลูกค้า (ไม่ต้อง login) =================
query_params = st.query_params
if query_params.get("page") == "order":
    st.title(f"{LOGO_EMOJI} สั่งอาหาร - {RESTAURANT_NAME}")

    prefill_table = query_params.get("table", "")
    zone_filter = query_params.get("zone", "").strip()
    # หมวดเครื่องดื่มทั่วไป ให้เห็นได้ทุกโซนเสมอ (ไม่ผูกกับโซนไหนโซนหนึ่ง)
    # ยกเว้น "บุฟเฟ่เบียร์" ซึ่งขึ้นต้นด้วยคำว่า "บุฟเฟ่" อยู่แล้ว เลยกรองเข้าโซนบุฟเฟ่ให้เองโดยอัตโนมัติ
    UNIVERSAL_CATEGORIES = ["น้ำ", "เหล้า", "เบียร์", "ไวน์", "สปาร์กลิ้ง"]
    menu_df = get_menu_list()

    if menu_df.empty:
        st.info("ร้านยังไม่ได้เปิดรับออเดอร์ในขณะนี้ครับ")
    else:
        display_menu_df = menu_df
        if zone_filter:
            is_universal_drink = menu_df["category"].fillna("").apply(
                lambda c: any(c.startswith(u) for u in UNIVERSAL_CATEGORIES)
            )
            zoned_df = menu_df[
                menu_df["category"].fillna("").str.startswith(zone_filter)
                | is_universal_drink
            ]
            if not zoned_df.empty:
                display_menu_df = zoned_df
            else:
                st.info(f"ยังไม่พบเมนูในโซน '{zone_filter}' — แสดงเมนูทั้งหมดแทนครับ")

        with st.form("customer_order_form"):
            table_no = st.text_input("หมายเลขโต๊ะ", value=prefill_table)
            st.write("เลือกเมนูที่ต้องการสั่ง:")

            qty_inputs = {}
            # แบ่งเมนูเป็นหมวดหมู่ ให้ลูกค้าหาง่ายขึ้น
            for category_name, group_df in display_menu_df.groupby("category"):
                st.markdown(f"**🍽️ {category_name}**")
                for _, row in group_df.iterrows():
                    col_img, col_info = st.columns([1, 3])
                    with col_img:
                        if "image" in row and row["image"] is not None:
                            st.image(row["image"], width=110)
                        else:
                            st.markdown(
                                "<div style='font-size:44px; text-align:center'>🍽️</div>",
                                unsafe_allow_html=True,
                            )
                    with col_info:
                        qty_inputs[row["menu_name"]] = st.number_input(
                            f"{row['menu_name']} ({row['price']:,.0f} บาท)",
                            min_value=0, step=1, key=f"cust_qty_{row['menu_name']}"
                        )

            submitted_order = st.form_submit_button("🛒 สั่งอาหาร")

            if submitted_order:
                items = [
                    (name, qty, float(menu_df[menu_df["menu_name"] == name]["price"].iloc[0]))
                    for name, qty in qty_inputs.items() if qty > 0
                ]
                if not table_no:
                    st.error("กรุณากรอกหมายเลขโต๊ะ")
                elif not items:
                    st.error("กรุณาเลือกอย่างน้อย 1 เมนู")
                else:
                    create_order(table_no, items)
                    total = sum(qty * price for _, qty, price in items)
                    st.success(f"สั่งอาหารเรียบร้อย! รวม {total:,.0f} บาท ทางร้านกำลังเตรียมให้ครับ 🙏")

    st.stop()

# ================= ระบบ login (สำหรับพนักงาน/เจ้าของร้าน) =================
# รายชื่อผู้ใช้ + บทบาท อ่านจาก Streamlit Secrets เป็นหลัก (ปลอดภัยกว่าฝังในโค้ด)
# วิธีตั้งค่า: ในเครื่อง ใช้ไฟล์ .streamlit/secrets.toml
#            บน Streamlit Cloud ตั้งค่าใน Settings > Secrets ของแอป
# รูปแบบใน secrets.toml:
#   [[users]]
#   username = "MSAN"
#   password = "8899M"
#   role = "owner"       # เห็นทุกเมนู
#
#   [[users]]
#   username = "kitchen1"
#   password = "1234"
#   role = "staff"       # เห็นแค่หน้าครัว
#
#   [[users]]
#   username = "cashier1"
#   password = "5678"
#   role = "cashier"     # เห็นแค่หน้าสรุปยอดต่อโต๊ะ (ดูอย่างเดียว ไม่มีปุ่มกด)
DEFAULT_USERS = [
    {"username": "MSAN", "password": "8899M", "role": "owner"},
    {"username": "kitchen1", "password": "1234", "role": "staff"},
    {"username": "cashier1", "password": "5678", "role": "cashier"},
]
USERS = st.secrets.get("users", DEFAULT_USERS)

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🔒 เข้าสู่ระบบ")

    with st.form("login_form"):
        input_username = st.text_input("ชื่อผู้ใช้")
        input_password = st.text_input("รหัสผ่าน", type="password")
        login_submitted = st.form_submit_button("เข้าสู่ระบบ")

        if login_submitted:
            matched_user = next(
                (u for u in USERS if u["username"] == input_username and u["password"] == input_password),
                None
            )
            if matched_user:
                st.session_state.logged_in = True
                st.session_state.role = matched_user["role"]
                st.rerun()
            else:
                st.error("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
    st.stop()

USER_ROLE = st.session_state.get("role", "staff")

# หน้าที่แต่ละบทบาทเห็นได้
# (บิล/ใบกำกับภาษี/VAT ยังฝากให้ Pakey จัดการเหมือนเดิม แต่เพิ่มหน้าการเงินสำหรับบันทึกรายจ่าย
#  และดูเทรนด์ต้นทุนให้ Manager เพราะเป็นข้อมูลภายในที่ไม่เกี่ยวกับใบเสร็จลูกค้า)
OWNER_PAGES = [
    "🏠 หน้าหลัก",
    "📦 สต็อกวัตถุดิบ",
    "🍽️ เมนูอาหาร",
    "📊 รายงานยอดขาย",
    "💰 การเงิน",
    "👨‍🍳 ครัว (ออเดอร์)",
    "🧾 สรุปยอดต่อโต๊ะ",
    "📱 QR สั่งอาหาร",
]
STAFF_PAGES = [
    "👨‍🍳 ครัว (ออเดอร์)",
]
CASHIER_PAGES = [
    "🧾 สรุปยอดต่อโต๊ะ",
]

if USER_ROLE == "owner":
    ROLE_PAGES = OWNER_PAGES
elif USER_ROLE == "cashier":
    ROLE_PAGES = CASHIER_PAGES
else:
    ROLE_PAGES = STAFF_PAGES

# ---------------- Sidebar: โลโก้ + ชื่อร้าน + เมนูนำทาง ----------------
with st.sidebar:
    if os.path.exists(LOGO_PATH):
        st.image(LOGO_PATH, width=90)
    else:
        st.markdown(f"<div style='font-size:60px; text-align:center'>{LOGO_EMOJI}</div>", unsafe_allow_html=True)

    st.markdown(f"<h3 style='text-align:center'>{RESTAURANT_NAME}</h3>", unsafe_allow_html=True)
    role_label = {"owner": "Manager", "cashier": "แคชเชียร์", "staff": "พนักงานครัว"}.get(USER_ROLE, "พนักงาน")
    st.caption(f"👤 เข้าสู่ระบบในบทบาท: {role_label}")
    st.divider()

    page = st.radio(
        "เมนู",
        ROLE_PAGES,
        label_visibility="collapsed",
    )

    st.divider()
    if st.button("🚪 ออกจากระบบ"):
        st.session_state.logged_in = False
        st.session_state.role = None
        st.rerun()

# ================= หน้า: หน้าหลัก (แดชบอร์ด) =================
if page == "🏠 หน้าหลัก":
    st.title(f"{LOGO_EMOJI} {RESTAURANT_NAME}")
    st.caption("👋 สวัสดีครับ วันนี้ร้านเรามีอะไรบ้าง")

    _dashboard_inventory = get_all_inventory()

    col_a, col_b = st.columns(2)

    with col_a:
        if not _dashboard_inventory.empty:
            _low = _dashboard_inventory[
                _dashboard_inventory["quantity"] <= _dashboard_inventory["low_stock_threshold"]
            ]
            st.metric("📦 ของใกล้หมด", f"{len(_low)} รายการ")
            if not _low.empty:
                st.caption(" • ".join(_low["item_name"].tolist()))
        else:
            st.metric("📦 ของใกล้หมด", "0 รายการ")

    with col_b:
        active_orders_count = len(get_active_orders())
        st.metric("🧾 ออเดอร์ที่ยังไม่เสร็จ", f"{active_orders_count} ออเดอร์")
        if active_orders_count > 0:
            st.caption("ไปที่เมนู 👨‍🍳 ครัว (ออเดอร์) เพื่อดูรายละเอียด")

# ================= หน้า: สต็อกวัตถุดิบ =================
elif page == "📦 สต็อกวัตถุดิบ":
    st.header("📦 จัดการวัตถุดิบคงคลัง")

    update_mode_label = st.radio(
        "โหมดการกรอก",
        ["➕ เพิ่มของเข้าสต็อก (ของเข้าใหม่ บวกเพิ่มจากของเดิม)", "✏️ ปรับยอดให้ตรง (นับสต็อกจริงแล้วตั้งค่าใหม่ทับของเดิม)"],
        help="เลือก 'เพิ่มของเข้าสต็อก' เวลาซื้อของเข้ามาเติม หรือเลือก 'ปรับยอดให้ตรง' เวลานับสต็อกจริงแล้วอยากตั้งตัวเลขให้ตรงกับที่นับได้",
    )
    update_mode = "set" if update_mode_label.startswith("✏️") else "add"
    quantity_field_label = "จำนวนที่นับได้จริง (ยอดใหม่ทั้งหมด)" if update_mode == "set" else "จำนวนที่เพิ่มเข้ามา"

    with st.form("inventory_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            item_name = st.text_input("ชื่อวัตถุดิบ")
            quantity = st.number_input(quantity_field_label, min_value=0.0, step=1.0)
        with col2:
            unit = st.text_input("หน่วย (เช่น กก., ฟอง, ลิตร)")
            threshold = st.number_input("จุดแจ้งเตือนของใกล้หมด", min_value=0.0, step=1.0)

        submitted_item = st.form_submit_button("📥 บันทึกวัตถุดิบ")
        if submitted_item:
            if item_name and unit:
                add_or_update_item(item_name, quantity, unit, threshold, mode=update_mode)
                st.success(f"อัปเดตวัตถุดิบ '{item_name}' เรียบร้อยแล้ว! ✅")
                st.rerun()
            else:
                st.error("กรุณากรอกชื่อวัตถุดิบและหน่วยให้ครบ")

    inventory_df = get_all_inventory()
    if inventory_df.empty:
        st.info("ยังไม่มีวัตถุดิบในระบบ")
    else:
        low_stock = inventory_df[inventory_df["quantity"] <= inventory_df["low_stock_threshold"]]
        if not low_stock.empty:
            st.warning("⚠️ วัตถุดิบใกล้หมด!")
            for _, row in low_stock.iterrows():
                st.error(f"🔴 {row['item_name']} เหลือ {row['quantity']} {row['unit']}")

        st.subheader("📋 รายการวัตถุดิบทั้งหมด")
        st.dataframe(inventory_df, use_container_width=True)

        st.subheader("🗑️ ลบวัตถุดิบ")
        selected_item_to_delete = st.selectbox(
            "เลือกวัตถุดิบที่จะลบ", inventory_df["item_name"].unique(), key="delete_inventory_select"
        )
        if st.button("🗑️ ลบวัตถุดิบนี้"):
            delete_inventory_item(selected_item_to_delete)
            st.success(f"ลบวัตถุดิบ '{selected_item_to_delete}' เรียบร้อยแล้ว! ✅")
            st.rerun()

# ================= หน้า: เมนูอาหาร =================
elif page == "🍽️ เมนูอาหาร":
    st.header("🍽️ จัดการเมนูอาหาร")

    existing_categories = get_all_categories()
    default_categories = ["บุฟเฟ่", "อาลาคาร์ท", "ราเมง", "น้ำ", "เหล้า", "เบียร์", "บุฟเฟ่เบียร์", "ไวน์", "สปาร์กลิ้ง"]
    combined_categories = existing_categories + [c for c in default_categories if c not in existing_categories]
    category_options = combined_categories + ["+ เพิ่มหมวดหมู่ใหม่"]

    with st.form("menu_form", clear_on_submit=True):
        menu_name = st.text_input("ชื่อเมนู")

        category_choice = st.selectbox("หมวดหมู่เมนู", category_options)
        new_category_input = ""
        if category_choice == "+ เพิ่มหมวดหมู่ใหม่":
            new_category_input = st.text_input("พิมพ์ชื่อหมวดหมู่ใหม่ (เช่น อาหารจานหลัก, เครื่องดื่ม, ของหวาน)")

        price = st.number_input("ราคาขาย (บาท)", min_value=0.0, step=1.0)

        uploaded_image = st.file_uploader(
            "รูปเมนู (ไม่บังคับ — ถ้าไม่อัปโหลดใหม่ จะใช้รูปเดิมที่เคยอัปโหลดไว้)",
            type=["png", "jpg", "jpeg"],
        )

        submitted_menu = st.form_submit_button("➕ เพิ่ม/อัปเดตเมนู")
        if submitted_menu:
            final_category = new_category_input.strip() if category_choice == "+ เพิ่มหมวดหมู่ใหม่" else category_choice
            if menu_name and final_category:
                image_bytes = None
                if uploaded_image is not None:
                    img = Image.open(uploaded_image)
                    img.thumbnail((600, 600))  # ย่อรูปให้ไม่ใหญ่เกินไป โหลดเร็วขึ้น
                    img_buf = io.BytesIO()
                    img.convert("RGB").save(img_buf, format="JPEG", quality=85)
                    image_bytes = img_buf.getvalue()
                set_menu_price(menu_name, price, final_category, image_bytes)
                st.success(f"บันทึกเมนู '{menu_name}' (หมวด {final_category}) เรียบร้อยแล้ว! ✅")
                st.rerun()
            else:
                st.error("กรุณากรอกชื่อเมนูและหมวดหมู่ให้ครบ")

    st.divider()
    with st.expander("📥 นำเข้าเมนูจำนวนมาก (เหมาะกับตอนมีเมนูเยอะๆ เช่น 100 รายการ)"):
        st.markdown("**ขั้นตอนที่ 1: นำเข้าชื่อเมนู + หมวดหมู่ + ราคา จากไฟล์ Excel/CSV**")

        template_df = pd.DataFrame({
            "ชื่อเมนู": ["ราเมงหมูชาชู", "ไวน์แดงแก้ว"],
            "หมวดหมู่": ["ราเมง", "ไวน์"],
            "ราคา": [180, 150],
        })
        template_buf = io.BytesIO()
        template_df.to_csv(template_buf, index=False, encoding="utf-8-sig")
        st.download_button(
            "⬇️ ดาวน์โหลดไฟล์ตัวอย่าง (CSV)",
            data=template_buf.getvalue(),
            file_name="ตัวอย่างเมนู.csv",
            mime="text/csv",
        )
        st.caption("เปิดไฟล์นี้ด้วย Excel แล้วพิมพ์รายการเมนูทั้งหมดต่อจากตัวอย่างได้เลย (คอลัมน์ต้องชื่อ ชื่อเมนู, หมวดหมู่, ราคา เป๊ะๆ) แล้วค่อยอัปโหลดกลับเข้ามา จะเซฟเป็น .csv หรือ .xlsx ก็ได้")

        bulk_menu_file = st.file_uploader(
            "อัปโหลดไฟล์เมนู (.csv หรือ .xlsx)",
            type=["csv", "xlsx"],
            key="bulk_menu_file",
        )
        if bulk_menu_file is not None:
            try:
                if bulk_menu_file.name.endswith(".csv"):
                    bulk_df = pd.read_csv(bulk_menu_file)
                else:
                    bulk_df = pd.read_excel(bulk_menu_file)

                required_cols = {"ชื่อเมนู", "หมวดหมู่", "ราคา"}
                if not required_cols.issubset(set(bulk_df.columns)):
                    st.error(f"ไฟล์ต้องมีคอลัมน์: {', '.join(required_cols)}")
                else:
                    st.dataframe(bulk_df, use_container_width=True)

                    dup_names = bulk_df["ชื่อเมนู"][bulk_df["ชื่อเมนู"].duplicated(keep=False)].unique()
                    if len(dup_names) > 0:
                        st.warning(
                            "⚠️ พบชื่อเมนูซ้ำกันในไฟล์นี้! เมนูที่ชื่อซ้ำกันจะถูกบันทึกทับกันเอง เหลือแค่ราคาล่าสุด "
                            "แนะนำให้แก้ชื่อให้ไม่ซ้ำก่อนนำเข้า (เช่น เติม (ซูชิ)/(ซาชิมิ) ต่อท้ายชื่อ):\n\n"
                            + "\n".join(f"- {name}" for name in dup_names)
                        )
                    if st.button("📥 นำเข้าเมนูทั้งหมดนี้"):
                        imported_count = 0
                        for _, bulk_row in bulk_df.iterrows():
                            row_name = str(bulk_row["ชื่อเมนู"]).strip()
                            row_category = str(bulk_row["หมวดหมู่"]).strip()
                            try:
                                row_price = float(bulk_row["ราคา"])
                            except (ValueError, TypeError):
                                continue
                            if row_name and row_category:
                                set_menu_price(row_name, row_price, row_category)
                                imported_count += 1
                        st.success(f"นำเข้าเมนูสำเร็จ {imported_count} รายการ ✅")
                        st.rerun()
            except Exception as e:
                st.error(f"อ่านไฟล์ไม่สำเร็จ: {e}")

        st.markdown("---")
        st.markdown("**ขั้นตอนที่ 2: อัปโหลดรูปเมนูทีละหลายไฟล์พร้อมกัน**")
        st.caption(
            "ตั้งชื่อไฟล์รูปให้ตรงกับชื่อเมนูที่นำเข้าไว้แล้วเป๊ะๆ เช่น เมนูชื่อ 'ผัดกะเพราหมู' "
            "ให้ตั้งชื่อไฟล์เป็น ผัดกะเพราหมู.jpg ระบบจะจับคู่ชื่อไฟล์กับชื่อเมนูให้อัตโนมัติ "
            "(ทำขั้นตอนที่ 1 ให้เสร็จก่อน เมนูต้องมีอยู่ในระบบแล้วถึงจะจับคู่ใส่รูปได้)"
        )

        bulk_images = st.file_uploader(
            "เลือกรูปเมนูได้หลายไฟล์พร้อมกัน",
            type=["png", "jpg", "jpeg"],
            accept_multiple_files=True,
            key="bulk_images",
        )
        if bulk_images:
            if st.button("📥 นำเข้ารูปเมนูทั้งหมดนี้"):
                current_menu_df = get_menu_list()
                existing_menu_names = set(current_menu_df["menu_name"])
                matched_count = 0
                unmatched_files = []
                for img_file in bulk_images:
                    file_menu_name = os.path.splitext(img_file.name)[0].strip()
                    if file_menu_name in existing_menu_names:
                        img = Image.open(img_file)
                        img.thumbnail((600, 600))
                        img_buf = io.BytesIO()
                        img.convert("RGB").save(img_buf, format="JPEG", quality=85)
                        matched_row = current_menu_df[current_menu_df["menu_name"] == file_menu_name].iloc[0]
                        set_menu_price(file_menu_name, matched_row["price"], matched_row["category"], img_buf.getvalue())
                        matched_count += 1
                    else:
                        unmatched_files.append(img_file.name)
                st.success(f"อัปโหลดรูปสำเร็จ {matched_count} รูป ✅")
                if unmatched_files:
                    st.warning("ไฟล์ที่ชื่อไม่ตรงกับเมนูไหนเลย (ไม่ได้นำเข้า): " + ", ".join(unmatched_files))
                st.rerun()

    menu_list_df = get_menu_list()
    if menu_list_df.empty:
        st.info("ยังไม่มีเมนูในระบบ")
    else:
        st.subheader("📋 เมนูทั้งหมด")
        st.dataframe(menu_list_df.drop(columns=["image"]), use_container_width=True)

        st.subheader("📷 รูปเมนู")
        gallery_cols = st.columns(4)
        for i, (_, row) in enumerate(menu_list_df.iterrows()):
            with gallery_cols[i % 4]:
                if row["image"] is not None:
                    st.image(row["image"], use_container_width=True)
                else:
                    st.markdown(
                        "<div style='font-size:44px; text-align:center'>🍽️</div>",
                        unsafe_allow_html=True,
                    )
                st.caption(row["menu_name"])

        st.subheader("🗑️ ลบเมนู")
        selected_menu_to_delete = st.selectbox(
            "เลือกเมนูที่จะลบ", menu_list_df["menu_name"].unique(), key="delete_menu_select"
        )
        if st.button("🗑️ ลบเมนูนี้"):
            delete_menu_item(selected_menu_to_delete)
            st.success(f"ลบเมนู '{selected_menu_to_delete}' เรียบร้อยแล้ว! ✅")
            st.rerun()

# ================= หน้า: รายงานยอดขาย =================
elif page == "📊 รายงานยอดขาย":
    st.header("📊 รายงานยอดขาย")

    sales_df = get_all_sales()

    if sales_df.empty:
        st.info("ยังไม่มีข้อมูลการขาย ลองขายเมนูสักรายการก่อนที่หน้า 🧾 ขายเมนู")
    else:
        summary = (
            sales_df.groupby("menu_name")
            .agg(total_qty=("qty_sold", "sum"), total_revenue=("total_price", "sum"))
            .sort_values("total_qty", ascending=False)
        )

        top5 = summary.head(5)

        st.subheader("🏆 เมนูขายดี Top 5 (นับจากจำนวนจาน)")
        st.bar_chart(top5["total_qty"])

        top5_display = top5.rename(columns={
            "total_qty": "จำนวนที่ขาย",
            "total_revenue": "ยอดขายรวม",
        })
        st.dataframe(top5_display, use_container_width=True)

        st.subheader("📋 ประวัติการขายทั้งหมด")
        st.dataframe(sales_df, use_container_width=True)

    st.divider()
    st.subheader("🍱 ยอดขายแยกตามหมวดหมู่")
    st.caption("ดูว่าแต่ละหมวด (ราเมง, บุฟเฟ่, อาลาคาร์ท, บุฟเฟ่เบียร์ ฯลฯ) ขายได้กี่จาน/แก้ว คิดเป็นกี่ % ของทั้งร้าน")

    cat_df = get_sales_by_category()
    if cat_df.empty:
        st.info("ยังไม่มีข้อมูลการขาย")
    else:
        cat_df["category"] = cat_df["category"].fillna("ไม่ระบุหมวด")

        month_options = sorted(cat_df["month"].dropna().unique(), reverse=True)
        selected_month = st.selectbox("เลือกเดือน", ["ทั้งหมด (ทุกเดือน)"] + list(month_options))

        if selected_month == "ทั้งหมด (ทุกเดือน)":
            month_view = cat_df.groupby("category").agg(qty=("qty", "sum"), revenue=("revenue", "sum")).reset_index()
        else:
            month_view = (
                cat_df[cat_df["month"] == selected_month]
                .groupby("category").agg(qty=("qty", "sum"), revenue=("revenue", "sum")).reset_index()
            )

        total_qty_all = month_view["qty"].sum()
        total_rev_all = month_view["revenue"].sum()
        month_view["% จำนวน"] = (month_view["qty"] / total_qty_all * 100).round(1) if total_qty_all else 0
        month_view["% ยอดขาย"] = (month_view["revenue"] / total_rev_all * 100).round(1) if total_rev_all else 0
        month_view = month_view.sort_values("revenue", ascending=False)

        col_m1, col_m2 = st.columns(2)
        with col_m1:
            st.metric("จำนวนที่ขายรวม", f"{total_qty_all:,.0f} รายการ")
        with col_m2:
            st.metric("ยอดขายรวม", f"{total_rev_all:,.0f} บาท")

        st.bar_chart(month_view.set_index("category")["revenue"])

        display_cat = month_view.rename(columns={
            "category": "หมวดหมู่", "qty": "จำนวนที่ขาย", "revenue": "ยอดขายรวม (บาท)",
        })
        st.dataframe(display_cat, use_container_width=True, hide_index=True)

        if len(month_options) > 1:
            st.subheader("📈 เทรนด์ยอดขายแต่ละหมวด (เทียบเดือนต่อเดือน)")
            trend = cat_df.pivot_table(index="month", columns="category", values="revenue", aggfunc="sum").fillna(0)
            st.line_chart(trend)

# ================= หน้า: การเงิน (เฉพาะ Manager) =================
elif page == "💰 การเงิน":
    st.header("💰 การเงิน (รายจ่ายร้าน)")
    st.caption("บันทึกค่าใช้จ่ายของร้าน เช่น ค่าวัตถุดิบ ค่าเช่า ค่าแรง เพื่อดูว่าต้นทุนแต่ละเดือนขึ้นหรือลง")

    EXPENSE_CATEGORIES = ["ค่าวัตถุดิบ", "ค่าเครื่องดื่ม/แอลกอฮอล์", "ค่าเช่าที่", "ค่าแรงพนักงาน",
                          "ค่าน้ำ-ค่าไฟ", "ค่าอุปกรณ์/ซ่อมบำรุง", "ค่าการตลาด", "อื่นๆ"]

    with st.form("expense_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            exp_date = st.date_input("วันที่")
            exp_category = st.selectbox("หมวดค่าใช้จ่าย", EXPENSE_CATEGORIES)
        with col2:
            exp_amount = st.number_input("จำนวนเงิน (บาท)", min_value=0.0, step=10.0)
            exp_note = st.text_input("บันทึกเพิ่มเติม (เช่น ซื้อจากร้านไหน)")

        submitted_exp = st.form_submit_button("💾 บันทึกรายจ่าย")
        if submitted_exp:
            if exp_amount > 0:
                add_transaction(str(exp_date), "รายจ่าย", exp_category, exp_amount, exp_note)
                st.success(f"บันทึกรายจ่าย {exp_category} {exp_amount:,.0f} บาท เรียบร้อย! ✅")
                st.rerun()
            else:
                st.error("กรุณากรอกจำนวนเงินให้มากกว่า 0")

    trans_df = get_all_transactions()
    expense_df = trans_df[trans_df["type"] == "รายจ่าย"] if not trans_df.empty else trans_df

    if expense_df.empty:
        st.info("ยังไม่มีรายการค่าใช้จ่ายในระบบ")
    else:
        monthly_df = get_monthly_expense_by_category()

        if not monthly_df.empty:
            st.divider()
            st.subheader("📈 รายจ่ายรวมแต่ละเดือน")
            total_by_month = monthly_df.groupby("month")["total"].sum()
            st.bar_chart(total_by_month)

            months_sorted = sorted(monthly_df["month"].unique())
            if len(months_sorted) >= 2:
                this_month, last_month = months_sorted[-1], months_sorted[-2]
                this_total = total_by_month.get(this_month, 0)
                last_total = total_by_month.get(last_month, 0)
                diff = this_total - last_total
                pct = (diff / last_total * 100) if last_total else 0
                st.metric(
                    f"รายจ่ายเดือน {this_month}",
                    f"{this_total:,.0f} บาท",
                    delta=f"{diff:+,.0f} บาท ({pct:+.1f}%) เทียบเดือน {last_month}",
                    delta_color="inverse",  # รายจ่ายเพิ่ม = แดง, ลด = เขียว
                )

            st.subheader("📊 เทรนด์รายจ่ายแยกตามหมวด (เทียบเดือนต่อเดือน)")
            st.caption("เอาไว้ดูว่าหมวดไหนต้นทุนพุ่งขึ้น เช่น ค่าวัตถุดิบเดือนนี้สูงกว่าเดือนที่แล้วไหม")
            pivot_exp = monthly_df.pivot_table(index="month", columns="category", values="total", aggfunc="sum").fillna(0)
            st.line_chart(pivot_exp)

        st.divider()
        st.subheader("📋 รายการค่าใช้จ่ายทั้งหมด")
        display_exp = expense_df[["id", "date", "category", "amount", "note"]].rename(columns={
            "id": "รหัส", "date": "วันที่", "category": "หมวด", "amount": "จำนวนเงิน", "note": "บันทึก",
        })
        st.dataframe(display_exp, use_container_width=True, hide_index=True)

        st.subheader("🗑️ ลบรายการค่าใช้จ่าย")
        del_id = st.selectbox("เลือกรหัสรายการที่จะลบ", expense_df["id"].tolist(), key="del_expense")
        if st.button("🗑️ ลบรายการนี้"):
            delete_transaction(del_id)
            st.success("ลบรายการเรียบร้อยแล้ว! ✅")
            st.rerun()

# ================= หน้า: ครัว (ออเดอร์จาก QR) =================
elif page == "👨‍🍳 ครัว (ออเดอร์)":
    st.header("👨‍🍳 ออเดอร์จากลูกค้า")

    if st.button("🔄 รีเฟรชออเดอร์ใหม่"):
        st.rerun()

    active_orders = get_active_orders()

    if active_orders.empty:
        st.info("ยังไม่มีออเดอร์ใหม่ตอนนี้")
    else:
        for _, order in active_orders.iterrows():
            items_df = get_order_items(order["id"])
            with st.container(border=True):
                st.subheader(f"โต๊ะ {order['table_no']} — ออเดอร์ #{order['id']} ({order['status']})")
                st.caption(order["created_at"])
                st.dataframe(items_df[["menu_name", "qty", "price"]], use_container_width=True)

                col1, col2, col3 = st.columns(3)
                with col1:
                    if order["status"] == "รอทำ":
                        if st.button("👨‍🍳 เริ่มทำ", key=f"start_{order['id']}"):
                            update_order_status(order["id"], "กำลังทำ")
                            st.rerun()
                with col2:
                    if st.button("✅ เสร็จแล้ว (บันทึกยอดขาย)", key=f"done_{order['id']}"):
                        complete_order(order["id"], order["table_no"])
                        st.success(f"ปิดออเดอร์โต๊ะ {order['table_no']} เรียบร้อย! ✅")
                        st.rerun()
                with col3:
                    if st.button("🖨️ พิมพ์ใบสั่ง", key=f"print_{order['id']}"):
                        st.session_state[f"show_print_{order['id']}"] = True

                if st.session_state.get(f"show_print_{order['id']}"):
                    print_kitchen_ticket(order, items_df)
                    st.session_state[f"show_print_{order['id']}"] = False

# ================= หน้า: สรุปยอดต่อโต๊ะ (สำหรับแคชเชียร์) =================
elif page == "🧾 สรุปยอดต่อโต๊ะ":
    st.header("🧾 สรุปยอดต่อโต๊ะ")
    st.caption("รวมทุกออเดอร์ที่ยังไม่เสร็จของโต๊ะนั้นเป็นยอดเดียว ไว้ดูตอนคีย์เข้า PakeySoft เพื่อออกใบเสร็จให้ลูกค้า")

    if st.button("🔄 รีเฟรช"):
        st.rerun()

    active_orders = get_active_orders()

    if active_orders.empty:
        st.info("ยังไม่มีโต๊ะที่มีออเดอร์ค้างอยู่ตอนนี้")
    else:
        table_numbers = sorted(active_orders["table_no"].unique(), key=str)
        for t_no in table_numbers:
            table_items_df = get_active_order_items_by_table(t_no)
            if table_items_df.empty:
                continue
            table_items_df["ยอดรวมรายการ"] = table_items_df["qty"] * table_items_df["price"]
            grouped = (
                table_items_df.groupby(["menu_name", "price"])
                .agg(qty=("qty", "sum"), รวม=("ยอดรวมรายการ", "sum"))
                .reset_index()
                .rename(columns={"menu_name": "เมนู", "price": "ราคา/หน่วย", "qty": "จำนวน"})
            )
            grand_total = grouped["รวม"].sum()

            with st.expander(f"โต๊ะ {t_no} — ยอดรวม {grand_total:,.0f} บาท", expanded=True):
                st.dataframe(grouped, use_container_width=True, hide_index=True)
                st.markdown(f"### รวมทั้งหมด: {grand_total:,.0f} บาท")

# ================= หน้า: QR สั่งอาหาร =================
elif page == "📱 QR สั่งอาหาร":
    st.header("📱 สร้าง QR โค้ดสำหรับลูกค้าสั่งอาหาร")
    st.write("ให้ลูกค้าสแกน QR นี้ที่โต๊ะ เพื่อสั่งอาหารได้เองจากมือถือ")

    base_url = st.text_input(
        "ที่อยู่เว็บของร้าน (Base URL)",
        value=APP_BASE_URL,
        help="ตั้งไว้ล่วงหน้าให้แล้วตาม URL จริงของแอป ปกติไม่ต้องแก้ เว้นแต่ย้ายไปโฮสต์ที่อื่น",
    )

    st.divider()
    st.subheader("🔲 สร้าง QR ทีละโต๊ะ")
    table_number = st.text_input("หมายเลขโต๊ะ", value="1")
    zone_input = st.text_input(
        "โซน (ไม่บังคับ — ใส่ไว้ให้ QR โต๊ะนี้เปิดมาเจอเฉพาะเมนูของโซนนั้นเลย)",
        placeholder="เช่น บุฟเฟ่ / อาลาคาร์ท / VIP",
        help="พิมพ์ให้ตรงกับตัวอักษรตอนต้นของ 'หมวดหมู่' ที่ตั้งไว้ตอนเพิ่มเมนู เช่น ถ้าหมวดหมู่คือ 'บุฟเฟ่ - ของทอด' ให้พิมพ์แค่ 'บุฟเฟ่' ตรงนี้ ปล่อยว่างไว้ถ้าอยากให้เห็นเมนูทั้งหมด",
    )

    if st.button("🔲 สร้าง QR โค้ด"):
        if not base_url:
            st.error("กรุณากรอกที่อยู่เว็บก่อน")
        else:
            order_url = f"{base_url.rstrip('/')}/?page=order&table={table_number}"
            if zone_input.strip():
                order_url += f"&zone={urllib.parse.quote(zone_input.strip())}"
            qr_img = qrcode.make(order_url)
            buf = io.BytesIO()
            qr_img.save(buf, format="PNG")

            st.image(buf.getvalue(), caption=f"QR โต๊ะ {table_number}", width=250)
            st.code(order_url)
            st.download_button(
                "⬇️ ดาวน์โหลด QR",
                data=buf.getvalue(),
                file_name=f"qr_table_{table_number}.png",
                mime="image/png",
                key="dl_single_qr",
            )

    st.divider()
    st.subheader("🔲 สร้าง QR หลายโต๊ะพร้อมกัน")
    col_a, col_b = st.columns(2)
    with col_a:
        start_table = st.number_input("โต๊ะเริ่มต้น", min_value=1, step=1, value=1)
    with col_b:
        end_table = st.number_input("โต๊ะสุดท้าย", min_value=1, step=1, value=10)
    batch_zone_input = st.text_input(
        "โซนของโต๊ะช่วงนี้ (ไม่บังคับ)",
        placeholder="เช่น บุฟเฟ่ / อาลาคาร์ท / VIP",
        key="batch_zone",
        help="ใช้ตอนโต๊ะช่วงนี้ทั้งหมดอยู่โซนเดียวกัน เช่น โต๊ะ 1-10 เป็นโซนบุฟเฟ่ทั้งหมด",
    )

    if st.button("🔲 สร้าง QR ทุกโต๊ะ"):
        if not base_url:
            st.error("กรุณากรอกที่อยู่เว็บก่อน")
        elif end_table < start_table:
            st.error("โต๊ะสุดท้ายต้องมากกว่าหรือเท่ากับโต๊ะเริ่มต้น")
        else:
            table_numbers = list(range(int(start_table), int(end_table) + 1))
            cols = st.columns(4)
            for i, t_no in enumerate(table_numbers):
                order_url = f"{base_url.rstrip('/')}/?page=order&table={t_no}"
                if batch_zone_input.strip():
                    order_url += f"&zone={urllib.parse.quote(batch_zone_input.strip())}"
                qr_img = qrcode.make(order_url)
                buf = io.BytesIO()
                qr_img.save(buf, format="PNG")
                with cols[i % 4]:
                    st.image(buf.getvalue(), caption=f"โต๊ะ {t_no}", use_container_width=True)
                    st.download_button(
                        "⬇️ ดาวน์โหลด",
                        data=buf.getvalue(),
                        file_name=f"qr_table_{t_no}.png",
                        mime="image/png",
                        key=f"dl_qr_{t_no}",
                    )
