ฃfrom datetime import datetime
from zoneinfo import ZoneInfo
import os
import io
import base64
import urllib.parse
import html as html_lib
import streamlit as st
import pandas as pd
import qrcode
import streamlit.components.v1 as components
from PIL import Image
from database import (
    init_db, add_or_update_item, delete_inventory_item, get_all_inventory, delete_all_inventory,
    set_menu_price, get_menu_list, get_all_categories, delete_menu_item, delete_all_menu_items,
    add_sale_log, get_all_sales, get_sales_by_category, delete_all_sales,
    add_transaction, get_all_transactions, delete_transaction, get_monthly_expense_by_category, delete_all_transactions,
    create_order, get_active_orders, get_active_drink_orders, get_active_table_numbers,
    get_order_items, get_active_order_items_by_table,
    update_order_status, update_drink_status, delete_order, delete_all_orders, delete_orders_by_table,
    create_staff_call, get_pending_staff_calls, acknowledge_staff_call,
    get_active_order_board, get_active_order_items_all_tables, complete_order,
    OrderRejected, NOTE_MAX_LENGTH, clean_note, fmt_ts,
    get_menu_availability, set_menu_available, set_menus_available,
)
from qr_security import is_safe_table_label, verify_order_params, build_order_url

BANGKOK_TZ = ZoneInfo("Asia/Bangkok")

def now_bangkok():
    return datetime.now(BANGKOK_TZ)

ZONE_LABELS = {
    "ramen": "🍜 ราเมง (อาลาคาร์ท)",
    "buffet_izakaya": "🍢 บุฟเฟ่อาหาร Izakaya",
    "vip_nabe_buffet": "🍲 VIP นาเบะ - บุฟเฟ่",
    "vip_nabe_alacarte": "🍢 VIP นาเบะ - อาลาคาร์ท",
}
UNIVERSAL_ZONE = "all"

QR_ZONE_OPTIONS = {
    "": "— ไม่ระบุโซน (เห็นเมนูทั้งหมด) —",
    "ramen": ZONE_LABELS["ramen"],
    "buffet_izakaya": ZONE_LABELS["buffet_izakaya"],
    "vip": "🛋️ ห้อง VIP (นาเบะ — ให้ลูกค้าเลือกบุฟเฟ่/อาลาคาร์ทเอง)",
}
VIP_MODE_OPTIONS = {
    "vip_nabe_buffet": "🍲 บุฟเฟ่นาเบะ",
    "vip_nabe_alacarte": "🍢 นาเบะ อาลาคาร์ท",
}

SKEWER_FRIED_ORDER_LIMIT = 5
SKEWER_FRIED_CATEGORIES = {"บุฟเฟ่ / Buffet - ปิ้งย่างเสีบไม้", "บุฟเฟ่ / Buffet - ของทอด"}
MAX_QTY_PER_ITEM = 30
MAX_LINES_PER_ORDER = 40

DRINK_CATEGORY_KEYWORDS = [
    "เบียร์", "beer", "ไวน์", "wine", "สาเก", "sake", "โซจู", "soju",
    "ค็อกเทл", "cocktail", "spirit", "เครื่องดื่ม", "mixer", "drink",
]

def _is_drink_category(cat):
    import unicodedata as _ud
    low = _ud.normalize("NFC", str(cat)).lower()
    return any(_ud.normalize("NFC", kw).lower() in low for kw in DRINK_CATEGORY_KEYWORDS)

def render_delete_all_button(label, confirm_key, button_key, delete_fn, success_message="ลบข้อมูลทั้งหมดเรียบร้อยแล้วครับ"):
    with st.expander(f"🗑️ {label} (ลบถาวร กู้คืนไม่ได้)"):
        st.warning(f"⚠️ การกดปุ่มนี้จะ{label}ทั้งหมดในระบบทันที ไม่สามารถกู้คืนได้ กรุณาตรวจสอบให้แน่ใจก่อนกด")
        confirmed = st.checkbox("ฉันเข้าใจและยืนยันว่าต้องการลบข้อมูลทั้งหมด", key=confirm_key)
        if st.button(f"🗑️ {label}เดี๋ยวนี้", key=button_key, disabled=not confirmed, type="primary"):
            delete_fn()
            st.success(success_message)
            st.rerun()

def _zone_list(zones_value):
    if not zones_value or (isinstance(zones_value, float) and pd.isna(zones_value)):
        return []
    return [z.strip() for z in str(zones_value).split(",") if z.strip()]

def _menu_in_zone(zones_value, zone_key):
    zl = _zone_list(zones_value)
    if not zl:
        return True
    return zone_key in zl or UNIVERSAL_ZONE in zl

RESTAURANT_NAME = "YANAGI"
LOGO_EMOJI = "🍽️"
LOGO_PATH = "logo.png"
BACKGROUND_PATH = "background.jpg"
APP_BASE_URL = "https://yanagi-restaurant-manager-mkxtzbrcydnej88qoxmufi.streamlit.app"

CONTACT_INFO = {
    "default": {
        "name": "Sushi Yanagi",
        "line": "yanagi",
        "fb_url": "https://web.facebook.com/Sushiyanagith",
        "tel": "061 331 6464",
    },
    "tonchinkan": {
        "name": "Tonchinkan Ramen",
        "line": None,
        "fb_url": "https://web.facebook.com/tonchinkancri",
        "tel": "061 331 6464",
    },
}

STAFF_CALL_BEEP_B64 = "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\r\n"


st.set_page_config(page_title=f"ระบบจัดการร้านอาหาร - {RESTAURANT_NAME}", page_icon=LOGO_EMOJI, layout="wide")

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

DB_SCHEMA_VERSION = "v4"

@st.cache_resource
def _init_db_once(_schema_version):
    init_db()
    return True

_init_db_once(DB_SCHEMA_VERSION)

def _row_available(row):
    value = row.get("is_available") if hasattr(row, "get") else None
    if value is None or pd.isna(value):
        return True
    return int(value) != 0

def render_menu_availability_panel(kind):
    want_drink = kind == "drink"
    title = "🚫 จัดการเมนูหมด (เครื่องดื่ม)" if want_drink else "🚫 จัดการเมนูหมด (อาหาร)"
    with st.expander(title):
        menu_status_df = get_menu_availability()
        if not menu_status_df.empty:
            menu_status_df = menu_status_df[
                menu_status_df["category"].apply(lambda c: bool(_is_drink_category(c)) == want_drink)
            ]
        if menu_status_df.empty:
            st.info("ยังไม่มีเมนูในหมวดนี้")
            return

        sold_out_df = menu_status_df[menu_status_df["is_available"] == 0]
        if sold_out_df.empty:
            st.success("ตอนนี้ไม่มีเมนูที่หมด")
        else:
            st.warning(f"ตอนนี้หมด {len(sold_out_df)} เมนู: " + " , ".join(sold_out_df["menu_name"].tolist()))
            if st.button("✅ เปิดขายทุกเมนูที่หมดอีกครั้ง", key=f"avail_reset_all_{kind}"):
                set_menus_available(sold_out_df["menu_name"].tolist(), True)
                st.rerun()

        search_text = st.text_input("🔎 ค้นหาเมนู", key=f"avail_search_{kind}", placeholder="พิมพ์บางส่วนของชื่อเมนู").strip().lower()
        shown_df = menu_status_df
        if search_text:
            shown_df = menu_status_df[menu_status_df["menu_name"].str.lower().str.contains(search_text, regex=False)]
        if shown_df.empty:
            st.caption("ไม่พบเมนูที่ค้นหา")
        for category, group_df in shown_df.groupby("category", sort=False):
            st.markdown(f"**{category}**")
            for _, item in group_df.iterrows():
                is_on = int(item["is_available"]) != 0
                col_name, col_btn = st.columns([4, 2])
                with col_name:
                    st.markdown(item["menu_name"] if is_on else f"~~{item['menu_name']}~~ :red[**หมด**]")
                with col_btn:
                    if st.button(
                        "🚫 ตั้งเป็นหมด" if is_on else "✅ เปิดขายอีกครั้ง",
                        key=f"avail_{kind}_{item['menu_name']}", use_container_width=True,
                    ):
                        set_menu_available(item["menu_name"], not is_on)
                        st.rerun()

def complete_food_order(order_id, table_no):
    return complete_order(order_id, "food", _is_drink_category)

def complete_drink_order(order_id, table_no):
    return complete_order(order_id, "drink", _is_drink_category)

def _group_board(board_df, want_drink):
    if board_df.empty:
        return []
    board_df = board_df.copy()
    board_df["_is_drink"] = board_df["category"].apply(_is_drink_category)
    board_df = board_df[board_df["_is_drink"] == want_drink]
    grouped = []
    for order_id, group in board_df.groupby("order_id", sort=False):
        first = group.iloc[0]
        order = {
            "id": int(order_id),
            "table_no": first["table_no"],
            "created_at": fmt_ts(first["created_at"]),
            "status": first["status"],
            "zone": first["zone"] if first["zone"] else "",
        }
        items = group[["menu_name", "qty", "price", "note"]].reset_index(drop=True)
        items["note"] = items["note"].fillna("")
        grouped.append((order, items))
    return grouped

def _order_caption(order):
    zone_label = ZONE_LABELS.get(order.get("zone") or "", "")
    text = f"สั่งเข้ามาเมื่อ {order['created_at']}"
    if zone_label:
        text += f" — โซน {zone_label}"
    return text + " — เรียงจากคิวที่มาก่อนไปหลังเสมอ"

def _qr_secret():
    try:
        value = st.secrets.get("qr_secret")
    except Exception:
        return None
    return str(value) if value else None

def _qr_enforced():
    try:
        return bool(st.secrets.get("qr_enforce", True))
    except Exception:
        return True

QR_SECRET_MISSING_MESSAGE = (
    "ยังไม่ได้ตั้งค่า qr_secret ใน Streamlit Secrets — ตั้งค่าก่อนจึงจะสร้าง QR ที่ป้องกันการแก้เลขโต๊ะได้"
)

def print_kitchen_ticket(order_row, items_df, label="ใบสั่งอาหาร (ครัว)"):
    esc = html_lib.escape
    def _row(r):
        note = str(r.get("note") or "").strip() if hasattr(r, "get") else ""
        note_html = f"<div style='font-size:13px'>📝 {esc(note)}</div>" if note else ""
        return (
            f"<tr><td>{esc(str(r['menu_name']))}{note_html}</td>"
            f"<td style='text-align:right; white-space:nowrap'>x{int(r['qty'])}</td></tr>"
        )
    rows_html = "".join(_row(r) for _, r in items_df.iterrows())
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
        <h2>{esc(RESTAURANT_NAME)}</h2>
        <div class="meta">{esc(label)}</div>
        <hr>
        <div class="meta" style="text-align:left; font-size:15px; font-weight:bold">
            โต๊ะ {esc(str(order_row['table_no']))} — ออเดอร์ #{int(order_row['id'])}
        </div>
        <div class="meta" style="text-align:left">{esc(fmt_ts(order_row['created_at']))}</div>
        <hr>
        <table>{rows_html}</table>
    </body>
    </html>
    """
    components.html(html, height=0, width=0)

query_params = st.query_params
if query_params.get("page") == "order":
    st.markdown(
        """
        <style>
        header[data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"],
        [data-testid="stAppDeployButton"],
        .stAppDeployButton,
        #MainMenu,
        footer { display: none !important; visibility: hidden !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    brand_key = query_params.get("brand", "default")
    contact = CONTACT_INFO.get(brand_key, CONTACT_INFO["default"])
    zone_filter = query_params.get("zone", "").strip()
    table_no = query_params.get("table", "").strip()

    _qr_key = _qr_secret()
    if _qr_enforced():
        if not _qr_key:
            st.error("ระบบสั่งอาหารยังไม่พร้อมใช้งาน กรุณาแจ้งพนักงานครับ 🙏")
            st.stop()
        if not (is_safe_table_label(table_no)
                and verify_order_params(_qr_key, table_no, zone_filter, brand_key, query_params.get("sig", ""))):
            st.error("QR โค้ดนี้ไม่ถูกต้องหรือถูกแก้ไข กรุณาสแกน QR ที่โต๊ะอีกครั้ง หรือเรียกพนักงานครับ 🙏")
            st.stop()
    else:
        if not is_safe_table_label(table_no):
            st.error("ไม่พบหมายเลขโต๊ะ กรุณาสแกน QR ที่โต๊ะอีกครั้งครับ")
            st.stop()
        if zone_filter not in (set(QR_ZONE_OPTIONS) | set(VIP_MODE_OPTIONS)):
            zone_filter = ""
    is_vip_room = zone_filter in ("vip", "vip_nabe_buffet", "vip_nabe_alacarte")

    col_title, col_contact = st.columns([3, 1])
    with col_title:
        st.title(f"{LOGO_EMOJI} สั่งอาหาร - {RESTAURANT_NAME}")
    with col_contact:
        if is_vip_room:
            if st.button("🔔 เรียกพนักงาน", use_container_width=True, type="primary"):
                room_label = table_no or "ห้อง VIP"
                if create_staff_call(room_label):
                    st.success(f"แจ้งพนักงานแล้ว! ({room_label})")
                else:
                    st.info("แจ้งพนักงานไปแล้วครับ กรุณารอสักครู่ 🙏")
        contact_lines = [f"**📘 [{contact['name']}]({contact['fb_url']})**"]
        if contact.get("line"):
            contact_lines.append(f"💬 Line: @{contact['line']}")
        if contact.get("tel"):
            contact_lines.append(f"☎️ {contact['tel']}")
        st.markdown("<br>".join(contact_lines), unsafe_allow_html=True)

    st.caption("ราคาทั้งหมดยังไม่รวม Service Charge 10% และ VAT 7% (All prices are subject to 10% service charge and 7% VAT)")

    if st.session_state.get("order_just_placed_total") is not None:
        st.success(f"สั่งอาหารเรียบร้อย! รวม {st.session_state['order_just_placed_total']:,.0f} บาท ทางร้านกำลังเตรียมให้ครับ 🙏")
        st.session_state["order_just_placed_total"] = None

    if st.session_state.get("sold_out_notice"):
        st.warning("ขออภัยครับ เมนูต่อไปนี้เพิ่งหมด จึงยังไม่ได้ส่งออเดอร์: " + " , ".join(st.session_state["sold_out_notice"])
                   + " — กรุณาเลือกเมนูอื่นแล้วกดสั่งอีกครั้งครับ")
        st.session_state["sold_out_notice"] = None

    menu_df = get_menu_list()

    if menu_df.empty:
        st.info("ร้านยังไม่ได้เปิดรับออเดอร์ในขณะนี้ครับ")
    else:
        effective_zone = zone_filter
        if zone_filter == "vip":
            st.write("เลือกรูปแบบการทานของโต๊ะนี้:")
            vip_mode_label = st.radio(
                "เลือกรูปแบบการทาน", list(VIP_MODE_OPTIONS.values()),
                horizontal=True, label_visibility="collapsed", key="vip_mode_choice",
            )
            effective_zone = [k for k, v in VIP_MODE_OPTIONS.items() if v == vip_mode_label][0]
        elif zone_filter in VIP_MODE_OPTIONS:
            effective_zone = zone_filter

        display_menu_df = menu_df
        if effective_zone:
            zoned_df = menu_df[menu_df["zones"].apply(lambda z: _menu_in_zone(z, effective_zone))]
            if not zoned_df.empty:
                display_menu_df = zoned_df
            else:
                st.info(f"ยังไม่พบเมนูในโซนนี้ — แสดงเมนูทั้งหมดแทนครับ")

        current_time = now_bangkok().time()
        current_weekday = now_bangkok().weekday()
        is_weekend_now = current_weekday >= 5

        def _time_ok(row):
            tf, tt = row.get("time_from"), row.get("time_to")
            if not tf or not tt or pd.isna(tf) or pd.isna(tt):
                return True
            try:
                t_from = datetime.strptime(str(tf).strip(), "%H:%M").time()
                t_to = datetime.strptime(str(tt).strip(), "%H:%M").time()
                return t_from <= current_time <= t_to
            except ValueError:
                return True

        def _day_ok(row):
            d = row.get("days_available")
            if not d or pd.isna(d) or str(d).strip() in ("", "ทุกวัน"):
                return True
            d_norm = str(d).strip()
            if d_norm in ("วันธรรมดา", "จันทร์-ศุกร์"):
                return not is_weekend_now
            if d_norm in ("เสาร์-อาทิตย์", "เสาร์อาทิตย์"):
                return is_weekend_now
            return True

        display_menu_df = display_menu_df[
            display_menu_df.apply(_time_ok, axis=1) & display_menu_df.apply(_day_ok, axis=1)
        ]

        st.markdown(f"#### 🪑 โต๊ะ {html_lib.escape(table_no)}")

        import unicodedata as _unicodedata

        def _norm_text(s):
            return _unicodedata.normalize("NFC", str(s)).lower()

        _CATEGORY_PREFIXES = [
            "อาลาคาร์ท / A La Carte - ", "อาลาคาร์ท / A La Carte -", "อาลาคาร์ท / A La Carte-",
            "บุฟเฟ่ / Buffet - ", "บุฟเฟ่ / Buffet -", "บุฟเฟ่ / Buffet-",
            "เครื่องดื่ม - ", "เครื่องดื่ม -", "เครื่องดื่ม-",
        ]

        def _pretty_category(cat):
            result = str(cat).strip()
            for p in _CATEGORY_PREFIXES:
                if result.startswith(p):
                    result = result[len(p):].strip()
                    break
            return result or str(cat)

        _CATEGORY_ICONS = [
            (["ซูชิ", "ซาซิมิ", "sushi", "sashimi"], "🍣"),
            (["ราเมง", "ราเมน", "ramen"], "🍜"),
            (["ย่าง", "เสียบไม้", "yaki"], "🍢"),
            (["ทอด", "คุชิ", "fried"], "🍤"),
            (["ซุป", "soup"], "🍲"),
            (["นาเบะ", "nabe", "ชาบู"], "🍲"),
            (["เบียร์", "beer"], "🍺"),
            (["ไวน์", "wine"], "🍷"),
            (["สาเก", "sake"], "🍶"),
            (["โซจู", "soju"], "🥃"),
            (["ค็อกเทล", "cocktail"], "🍹"),
            (["เครื่องดื่ม", "mixer", "drink"], "🥤"),
            (["บุฟเฟ่", "buffet"], "🍽️"),
        ]

        def _category_icon(cat):
            low = _norm_text(cat)
            for keywords, icon in _CATEGORY_ICONS:
                if any(_norm_text(k) in low for k in keywords):
                    return icon
            return "🍴"

        def _render_note_input(qty_key, note_key, category_name):
            if _is_drink_category(category_name):
                return
            if (st.session_state.get(qty_key) or 0) > 0:
                st.text_input(
                    ":red[หมายเหตุ]", key=note_key, max_chars=NOTE_MAX_LENGTH,
                    placeholder="เช่น ไม่ใส่ผัก / ไม่เผ็ด",
                )

        def _render_item_row(row, category_name):
            col_img, col_info = st.columns([1, 3])
            with col_img:
                if "image" in row and row["image"] is not None:
                    st.image(row["image"], width=170)
                else:
                    st.markdown(
                        "<div style='font-size:44px; text-align:center'>🍽️</div>",
                        unsafe_allow_html=True,
                    )
            with col_info:
                item_label = row["menu_name"]
                if row.get("is_recommended"):
                    item_label = f"⭐ แนะนำ | {item_label}"
                if not _row_available(row):
                    st.session_state.pop(f"cust_qty_{row['menu_name']}", None)
                    st.markdown(f"~~{item_label}~~ &nbsp; :red[**หมด**]")
                else:
                    st.number_input(
                        f"{item_label} ({row['price']:,.0f} บาท)",
                        min_value=0, step=1, key=f"cust_qty_{row['menu_name']}"
                    )
                    _render_note_input(f"cust_qty_{row['menu_name']}", f"cust_note_{row['menu_name']}", category_name)
                if pd.notna(row.get("description")) and str(row.get("description")).strip():
                    st.caption(row["description"])

        def _render_category_items(category_name, group_df):
            has_size_group = group_df["size_group"].fillna("").str.strip() != ""
            standalone_items = group_df[~has_size_group]
            sized_items = group_df[has_size_group]

            for _, row in standalone_items.iterrows():
                _render_item_row(row, category_name)

            for size_group_name, variants_df in sized_items.groupby("size_group"):
                col_img, col_info = st.columns([1, 3])
                first_row = variants_df.iloc[0]
                with col_img:
                    if first_row.get("image") is not None:
                        st.image(first_row["image"], width=170)
                    else:
                        st.markdown(
                            "<div style='font-size:44px; text-align:center'>🍽️</div>",
                            unsafe_allow_html=True,
                        )
                with col_info:
                    title_label = size_group_name
                    if first_row.get("is_recommended"):
                        title_label = f"⭐ แนะนำ | {title_label}"
                    st.markdown(f"**{title_label}**")
                    size_labels = variants_df["size_label"].fillna(variants_df["menu_name"]).tolist()
                    selected_size = st.radio(
                        "เลือกไซส์", size_labels, horizontal=True,
                        key=f"size_choice_{category_name}_{size_group_name}", label_visibility="collapsed",
                    )
                    selected_row = variants_df[
                        variants_df["size_label"].fillna(variants_df["menu_name"]) == selected_size
                    ].iloc[0]
                    if not _row_available(selected_row):
                        st.session_state.pop(f"cust_qty_sized_{category_name}_{size_group_name}", None)
                        st.markdown(f"~~{selected_size}~~ &nbsp; :red[**หมด**] (เลือกไซส์อื่นได้)")
                    else:
                        st.number_input(
                            f"{selected_size} ({selected_row['price']:,.0f} บาท)",
                            min_value=0, step=1,
                            key=f"cust_qty_sized_{category_name}_{size_group_name}",
                        )
                        _render_note_input(
                            f"cust_qty_sized_{category_name}_{size_group_name}",
                            f"cust_note_sized_{category_name}_{size_group_name}",
                            category_name,
                        )
                    if pd.notna(selected_row.get("description")) and str(selected_row.get("description")).strip():
                        st.caption(selected_row["description"])

        def _collect_cart_items():
            collected = []
            for cat_name, grp_df in display_menu_df.groupby("category"):
                has_sg = grp_df["size_group"].fillna("").str.strip() != ""
                for _, r in grp_df[~has_sg].iterrows():
                    if not _row_available(r):
                        continue
                    q = st.session_state.get(f"cust_qty_{r['menu_name']}", 0)
                    if q and q > 0:
                        note = "" if _is_drink_category(cat_name) else clean_note(st.session_state.get(f"cust_note_{r['menu_name']}", ""))
                        collected.append((r["menu_name"], q, float(r["price"]), cat_name, note))
                for sg_name, variants_df in grp_df[has_sg].groupby("size_group"):
                    chosen = st.session_state.get(f"size_choice_{cat_name}_{sg_name}")
                    if chosen is None:
                        continue
                    matched = variants_df[variants_df["size_label"].fillna(variants_df["menu_name"]) == chosen]
                    if matched.empty:
                        continue
                    sel_row = matched.iloc[0]
                    if not _row_available(sel_row):
                        continue
                    q = st.session_state.get(f"cust_qty_sized_{cat_name}_{sg_name}", 0)
                    if q and q > 0:
                        note = "" if _is_drink_category(cat_name) else clean_note(st.session_state.get(f"cust_note_sized_{cat_name}_{sg_name}", ""))
                        collected.append((sel_row["menu_name"], q, float(sel_row["price"]), cat_name, note))
            return collected

        import re as _re

        def _is_package_item(name):
            return _unicodedata.normalize("NFC", str(name)).strip().startswith("บุฟเฟ่")

        def _clean_package_label(name):
            cleaned = _re.sub(r"\([^)]*(?:ก่อน|หลัง|\d{1,2}:\d{2})[^)]*\)", "", str(name)).strip()
            return cleaned or str(name)

        is_package_mask = display_menu_df["menu_name"].apply(_is_package_item)
        package_df = display_menu_df[is_package_mask]
        food_df = display_menu_df[~is_package_mask]

        if not package_df.empty:
            for _, prow in package_df.iterrows():
                with st.container(border=True):
                    st.markdown(f"#### 🍽️ {_clean_package_label(prow['menu_name'])} — {prow['price']:,.0f} บาท")
                    if not _row_available(prow):
                        st.session_state.pop(f"cust_qty_{prow['menu_name']}", None)
                        st.markdown(":red[**หมด**]")
                    else:
                        st.number_input(
                            "จำนวน (ท่าน)", min_value=0, step=1,
                            key=f"cust_qty_{prow['menu_name']}",
                        )
                        _render_note_input(f"cust_qty_{prow['menu_name']}", f"cust_note_{prow['menu_name']}", prow["category"])

        _CATEGORY_ORDER = [
            (1, ["บุฟเฟ่เบียร์", "beer buffet"]),
            (3, ["ท็อปปิ้งราเมง", "ท็อปปิ้งราเมน", "ท็อปปิ้ง"]),
            (2, ["ราเมง", "ราเมน", "ramen"]),
            (4, ["appetizer"]),
            (5, ["อาหารจานหลัก", "main"]),
            (6, ["ย่างเสียบไม้", "yaki"]),
            (7, ["คุชิคัตสึ"]),
            (8, ["ซุป", "soup"]),
            (11, ["ซูชิเซต"]),
            (9, ["ซูชิ", "sushi"]),
            (10, ["ซาซิมิ", "sashimi"]),
            (20, ["izakaya"]),
            (21, ["ปิ้งย่าง", "ปิ้งย่างเสีบไม้"]),
            (22, ["ของทอด"]),
            (900, ["mixer"]),
            (910, ["เบียร์", "beer"]),
            (920, ["ไวน์", "wine"]),
            (930, ["สาเก", "sake"]),
            (940, ["โซจู", "soju"]),
            (950, ["ค็อกเทล", "cocktail"]),
            (960, ["spirit"]),
            (970, ["เครื่องดื่ม", "drink"]),
        ]

        def _category_sort_priority(cat):
            low = _norm_text(cat)
            for priority, keywords in _CATEGORY_ORDER:
                if any(_norm_text(k) in low for k in keywords):
                    return priority
            return 500

        categories = sorted(
            food_df["category"].dropna().unique().tolist(),
            key=lambda c: (_category_sort_priority(c), c),
        )
        category_labels = {c: f"{_category_icon(c)} {_pretty_category(c)}" for c in categories}

        cat_state_key = f"order_cat::{effective_zone}"
        selected_category = st.session_state.get(cat_state_key)
        if selected_category not in categories:
            selected_category = None

        cart_preview = _collect_cart_items()
        if cart_preview:
            cart_total = sum(q * p for _, q, p, _, _ in cart_preview)
            st.info(f"🛒 ตอนนี้เลือกไว้ {len(cart_preview)} รายการ รวม {cart_total:,.0f} บาท (เลื่อนดูหมวดอื่นต่อได้ ของที่เลือกไว้จะไม่หาย)")

        if selected_category is None and len(categories) == 1:
            selected_category = categories[0]

        if not categories:
            pass
        elif selected_category is None:
            st.write("เลือกหมวดหมู่ที่ต้องการสั่ง:")
            for cat in categories:
                if st.button(category_labels[cat], key=f"catbtn_{effective_zone}_{cat}", use_container_width=True):
                    st.session_state[cat_state_key] = cat
                    st.rerun()
        else:
            if len(categories) > 1 and st.button("◀ กลับไปเลือกหมวดหมู่", key=f"back_{effective_zone}"):
                st.session_state[cat_state_key] = None
                st.rerun()
            st.markdown(f"### {category_labels[selected_category]}")
            _render_category_items(
                selected_category, food_df[food_df["category"] == selected_category]
            )

        st.divider()
        submitted_order = st.button("🛒 สั่งอาหาร", type="primary", use_container_width=True)

        if submitted_order:
            cart_items = _collect_cart_items()
            items = [(name, qty, price, _is_drink_category(cat), note) for name, qty, price, cat, note in cart_items]
            skewer_fried_qty = sum(
                qty for _name, qty, _price, cat, _note in cart_items if cat in SKEWER_FRIED_CATEGORIES
            )
            if not items:
                st.error("กรุณาเลือกอย่างน้อย 1 เมนู")
            elif any(qty > MAX_QTY_PER_ITEM for _n, qty, _p, _d, _o in items) or len(items) > MAX_LINES_PER_ORDER:
                st.error(f"จำนวนที่สั่งมากผิดปกติ (ต่อเมนูไม่เกิน {MAX_QTY_PER_ITEM} และไม่เกิน {MAX_LINES_PER_ORDER} รายการต่อรอบ) กรุณาเรียกพนักงานครับ")
            elif effective_zone == "buffet_izakaya" and skewer_fried_qty > SKEWER_FRIED_ORDER_LIMIT:
                st.error(
                    f"ของย่าง+ของทอด สั่งได้ไม่เกิน {SKEWER_FRIED_ORDER_LIMIT} ไม้ต่อรอบครับ "
                    f"(ตอนนี้เลือกไว้รวม {skewer_fried_qty} ไม้) — ลดจำนวนลงแล้วค่อยกดสั่งใหม่ได้เลย สั่งรอบต่อไปได้ไม่จำกัดครับ"
                )
            else:
                try:
                    create_order(table_no, items, zone=effective_zone or None)
                except OrderRejected as rejected:
                    if rejected.code == "cooldown":
                        st.warning(f"เพิ่งส่งออเดอร์ไปเมื่อสักครู่ครับ กรุณารออีก {rejected.retry_after} วินาที แล้วกดสั่งอีกครั้ง (ออเดอร์ก่อนหน้าส่งถึงครัวแล้ว)")
                    elif rejected.code == "sold_out":
                        get_menu_list.clear()
                        st.session_state["sold_out_notice"] = rejected.items
                        st.rerun()
                    elif rejected.code == "too_many_waiting":
                        st.warning("โต๊ะนี้มีออเดอร์รอทำอยู่หลายรายการแล้วครับ กรุณารอให้ครัวทำเสร็จก่อน หรือเรียกพนักงาน")
                    else:
                        st.error("ส่งออเดอร์ไม่สำเร็จ กรุณาลองใหม่อีกครั้งครับ")
                else:
                    total = sum(qty * price for _, qty, price, _is_drink, _note in items)
                    for name, _qty, _price, _cat, _note in cart_items:
                        st.session_state.pop(f"cust_qty_{name}", None)
                    for sg_key in list(st.session_state.keys()):
                        if sg_key.startswith("cust_qty_sized_"):
                            st.session_state[sg_key] = 0
                        elif sg_key.startswith("cust_note_"):
                            st.session_state.pop(sg_key, None)
                    st.session_state["order_just_placed_total"] = total
                    st.rerun()

    st.stop()

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

OWNER_PAGES = [
    "🏠 หน้าหลัก",
    "📦 สต็อกวัตถุดิบ",
    "🍽️ เมนูอาหาร",
    "📊 รายงานยอดขาย",
    "💰 การเงิน",
    "👨‍🍳 ครัว (ออเดอร์)",
    "🥤 แคชเชียร์ (เครื่องดื่ม)",
    "🧾 สรุปยอดต่อโต๊ะ",
    "📱 QR สั่งอาหาร",
]
STAFF_PAGES = [
    "👨‍🍳 ครัว (ออเดอร์)",
]
CASHIER_PAGES = [
    "🥤 แคชเชียร์ (เครื่องดื่ม)",
    "🧾 สรุปยอดต่อโต๊ะ",
]

if USER_ROLE == "owner":
    ROLE_PAGES = OWNER_PAGES
elif USER_ROLE == "cashier":
    ROLE_PAGES = CASHIER_PAGES
else:
    ROLE_PAGES = STAFF_PAGES

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

elif page == "📦 สต็อกวัตถุดิบ":
    st.header("📦 จัดการวัตถุดิบคงคลัง")

    update_mode_label = st.radio(
        "โหมดการกรอก",
        ["➕ เพิ่มของเข้าสต็อก (ของเข้าใหม่ บวกเพิ่มจากของเดิม)", "✏️ ปรับยอดให้ตรง (นับสต็อกจริงแล้วตั้งค่าใหม่ทับของเดิม)"],
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

        render_delete_all_button(
            "ลบวัตถุดิบทั้งหมด", "confirm_delete_all_inventory", "btn_delete_all_inventory",
            delete_all_inventory,
        )

elif page == "🍽️ เมนูอาหาร":
    st.header("🍽️ จัดการเมนูอาหาร")

    existing_categories = get_all_categories()
    default_categories = [
        "บุฟเฟ่", "อาลาคาร์ท", "ราเมง",
        "เครื่องดื่ม - น้ำ", "เครื่องดื่ม - เหล้า", "เครื่องดื่ม - เบียร์", "เครื่องดื่ม - ไวน์", "เครื่องดื่ม - สปาร์กลิ้ง",
        "เครื่องดื่ม - Sake", "เครื่องดื่ม - Soju", "เครื่องดื่ม - Cocktail", "เครื่องดื่ม - Mixer",
        "บุฟเฟ่เบียร์", "บุฟเฟ่ไวน์",
    ]
    combined_categories = existing_categories + [c for c in default_categories if c not in existing_categories]
    category_options = combined_categories + ["+ เพิ่มหมวดหมู่ใหม่"]

    with st.form("menu_form", clear_on_submit=True):
        menu_name = st.text_input("ชื่อเมนู")

        category_choice = st.selectbox("หมวดหมู่เมนู", category_options)
        new_category_input = ""
        if category_choice == "+ เพิ่มหมวดหมู่ใหม่":
            new_category_input = st.text_input("พิมพ์ชื่อหมวดหมู่ใหม่")

        price = st.number_input("ราคาขาย (บาท)", min_value=0.0, step=1.0)

        zone_choices = st.multiselect(
            "โซนที่ขายเมนูนี้ (เลือกได้หลายโซน)",
            options=list(ZONE_LABELS.keys()) + [UNIVERSAL_ZONE],
            format_func=lambda k: "🌐 ทุกโซน (เช่น เครื่องดื่มทั่วไป)" if k == UNIVERSAL_ZONE else ZONE_LABELS[k],
        )

        col_sg, col_sl = st.columns(2)
        with col_sg:
            size_group = st.text_input("ชื่อกลุ่มไซส์ (ไม่บังคับ)", placeholder="เช่น ชาชูเมน")
        with col_sl:
            size_label = st.text_input("ป้ายไซส์นี้", placeholder="เช่น ชามเล็ก")

        use_time_window = st.checkbox("⏰ เมนูนี้โชว์เฉพาะบางช่วงเวลา")
        time_from_val, time_to_val, days_available_val = None, None, None
        if use_time_window:
            col_tf, col_tt = st.columns(2)
            with col_tf:
                time_from_val = st.time_input("เวลาเริ่มโชว์เมนูนี้")
            with col_tt:
                time_to_val = st.time_input("เวลาสิ้นสุด")
            days_choice = st.selectbox("วันที่ขาย", ["ทุกวัน", "วันธรรมดา (จ-ศ)", "เสาร์-อาทิตย์"])
            days_available_val = {"ทุกวัน": "ทุกวัน", "วันธรรมดา (จ-ศ)": "วันธรรมดา", "เสาร์-อาทิตย์": "เสาร์-อาทิตย์"}[days_choice]

        description = st.text_area("คำอธิบายเพิ่มเติม (ไม่บังคับ)", height=70)
        is_recommended = st.checkbox("⭐ ติดป้ายแนะนำเมนูนี้ (Recommended)")

        uploaded_image = st.file_uploader("รูปเมนู", type=["png", "jpg", "jpeg"])

        submitted_menu = st.form_submit_button("➕ เพิ่ม/อัปเดตเมนู")
        if submitted_menu:
            final_category = new_category_input.strip() if category_choice == "+ เพิ่มหมวดหมู่ใหม่" else category_choice
            if menu_name and final_category:
                image_bytes = None
                if uploaded_image is not None:
                    img = Image.open(uploaded_image)
                    img.thumbnail((1200, 1200))
                    img_buf = io.BytesIO()
                    img.convert("RGB").save(img_buf, format="JPEG", quality=92)
                    image_bytes = img_buf.getvalue()
                set_menu_price(
                    menu_name, price, final_category, image_bytes,
                    description.strip() or None, is_recommended,
                    size_group.strip() or None, size_label.strip() or None,
                    time_from_val.strftime("%H:%M") if time_from_val else None,
                    time_to_val.strftime("%H:%M") if time_to_val else None,
                    days_available_val,
                    ",".join(zone_choices) if zone_choices else None,
                )
                st.success(f"บันทึกเมนู '{menu_name}' เรียบร้อยแล้ว! ✅")
                st.rerun()
            else:
                st.error("กรุณากรอกชื่อเมนูและหมวดหมู่ให้ครบ")

    menu_list_df = get_menu_list()
    if menu_list_df.empty:
        st.info("ยังไม่มีเมนูในระบบ")
    else:
        st.subheader("📋 เมนูทั้งหมด")
        st.dataframe(menu_list_df.drop(columns=["image"]), use_container_width=True)

        st.subheader("🗑️ ลบเมนู")
        selected_menu_to_delete = st.selectbox("เลือกเมนูที่จะลบ", menu_list_df["menu_name"].unique(), key="delete_menu_select")
        if st.button("🗑️ ลบเมนูนี้"):
            delete_menu_item(selected_menu_to_delete)
            st.success(f"ลบเมนู '{selected_menu_to_delete}' เรียบร้อยแล้ว! ✅")
            st.rerun()

elif page == "📊 รายงานยอดขาย":
    st.header("📊 รายงานยอดขาย")
    sales_df = get_all_sales()
    if sales_df.empty:
        st.info("ยังไม่มีข้อมูลการขาย")
    else:
        summary = (
            sales_df.groupby("menu_name")
            .agg(total_qty=("qty_sold", "sum"), total_revenue=("total_price", "sum"))
            .sort_values("total_qty", ascending=False)
        )
        st.subheader("🏆 เมนูขายดี Top 5")
        st.bar_chart(summary.head(5)["total_qty"])
        st.dataframe(summary, use_container_width=True)

elif page == "💰 การเงิน":
    st.header("💰 การเงิน (รายจ่ายร้าน)")
    EXPENSE_CATEGORIES = ["ค่าวัตถุดิบ", "ค่าเครื่องดื่ม/แอลกอฮอล์", "ค่าเช่าที่", "ค่าแรงพนักงาน", "ค่าน้ำ-ค่าไฟ", "ค่าอุปกรณ์/ซ่อมบำรุง", "อื่นๆ"]
    with st.form("expense_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            exp_date = st.date_input("วันที่", value=now_bangkok().date())
            exp_category = st.selectbox("หมวดค่าใช้จ่าย", EXPENSE_CATEGORIES)
        with col2:
            exp_amount = st.number_input("จำนวนเงิน (บาท)", min_value=0.0, step=10.0)
            exp_note = st.text_input("บันทึกเพิ่มเติม")
        if st.form_submit_button("💾 บันทึกรายจ่าย"):
            if exp_amount > 0:
                add_transaction(str(exp_date), "รายจ่าย", exp_category, exp_amount, exp_note)
                st.success("บันทึกรายจ่ายเรียบร้อย! ✅")
                st.rerun()

elif page == "👨‍🍳 ครัว (ออเดอร์)":
    st.header("👨‍🍳 ออเดอร์อาหารจากลูกค้า")
    st.caption("อัปเดตอัตโนมัติทุก 5 วินาที พร้อมเสียงเตือน")
    render_menu_availability_panel("food")

    @st.fragment(run_every="5s")
    def _kitchen_orders_fragment():
        food_orders = _group_board(get_active_order_board("food"), want_drink=False)
        current_ids = {order["id"] for order, _ in food_orders}
        seen_ids = st.session_state.get("kitchen_seen_order_ids")
        if seen_ids is not None and (current_ids - seen_ids):
            components.html(f'<audio autoplay><source src="data:audio/wav;base64,{STAFF_CALL_BEEP_B64}" type="audio/wav"></audio>', height=0)
        st.session_state["kitchen_seen_order_ids"] = current_ids

        if not food_orders:
            st.info("ยังไม่มีออเดอร์อาหารใหม่ตอนนี้")
            return

        for queue_no, (order, food_items) in enumerate(food_orders, start=1):
            with st.container(border=True):
                st.subheader(f"🔢 คิวที่ {queue_no} — โต๊ะ {order['table_no']} (ออเดอร์ #{order['id']}, {order['status']})")
                st.dataframe(food_items, use_container_width=True)
                col1, col2, col3 = st.columns(3)
                with col1:
                    if order["status"] == "รอทำ" and st.button("👨‍🍳 เริ่มทำ", key=f"start_{order['id']}"):
                        update_order_status(order["id"], "กำลังทำ")
                        st.rerun()
                with col2:
                    if st.button("✅ เสร็จแล้ว", key=f"done_{order['id']}"):
                        complete_food_order(order["id"], order["table_no"])
                        st.rerun()
                with col3:
                    if st.button("🖨️ พิมพ์ใบสั่ง", key=f"print_{order['id']}"):
                        print_kitchen_ticket(order, food_items)

    _kitchen_orders_fragment()

elif page == "🥤 แคชเชียร์ (เครื่องดื่ม)":
    st.header("🥤 ออเดอร์เครื่องดื่มจากลูกค้า")
    render_menu_availability_panel("drink")

    @st.fragment(run_every="5s")
    def _cashier_drink_orders_fragment():
        drink_orders = _group_board(get_active_order_board("drink"), want_drink=True)
        if not drink_orders:
            st.info("ยังไม่มีออเดอร์เครื่องดื่มใหม่ตอนนี้")
            return
        for queue_no, (order, drink_items) in enumerate(drink_orders, start=1):
            with st.container(border=True):
                st.subheader(f"🔢 คิวที่ {queue_no} — โต๊ะ {order['table_no']} (ออเดอร์ #{order['id']})")
                st.dataframe(drink_items, use_container_width=True)
                if st.button("✅ เสร็จแล้ว", key=f"drink_done_{order['id']}"):
                    complete_drink_order(order["id"], order["table_no"])
                    st.rerun()

    _cashier_drink_orders_fragment()

elif page == "🧾 สรุปยอดต่อโต๊ะ":
    st.header("🧾 สรุปยอดต่อโต๊ะ")
    all_active_items_df = get_active_order_items_all_tables()
    active_table_numbers = all_active_items_df["table_no"].unique().tolist() if not all_active_items_df.empty else []
    if not active_table_numbers:
        st.info("ยังไม่มีโต๊ะที่มีออเดอร์ค้างอยู่ตอนนี้")
    else:
        for t_no in active_table_numbers:
            table_items_df = all_active_items_df[all_active_items_df["table_no"] == t_no][["menu_name", "qty", "price"]].copy()
            grand_total = (table_items_df["qty"] * table_items_df["price"]).sum()
            with st.expander(f"โต๊ะ {t_no} — ยอดรวม {grand_total:,.0f} บาท", expanded=True):
                st.dataframe(table_items_df, use_container_width=True)

elif page == "📱 QR สั่งอาหาร":
    st.header("📱 สร้าง QR โค้ดสำหรับลูกค้าสั่งอาหาร")
    table_number = st.text_input("หมายเลขโต๊ะ", value="1")
    zone_choice_key = st.selectbox("โซนของโต๊ะนี้", list(QR_ZONE_OPTIONS.keys()), format_func=lambda k: QR_ZONE_OPTIONS[k])
    
    if st.button("🔲 สร้าง QR โค้ด"):
        if not _qr_secret():
            st.error(QR_SECRET_MISSING_MESSAGE)
        else:
            order_url = build_order_url(_qr_secret(), APP_BASE_URL, table_number, zone_choice_key, "default")
            qr_img = qrcode.make(order_url)
            buf = io.BytesIO()
            qr_img.save(buf, format="PNG")
            st.image(buf.getvalue(), caption=f"QR โต๊ะ {table_number}", width=250)
            st.code(order_url)
