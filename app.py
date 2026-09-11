from datetime import date, timedelta, datetime
import os
import io
import streamlit as st
import pandas as pd
import qrcode
from database import (
    init_db, add_transaction, get_all_transactions, delete_transaction,
    add_or_update_item, get_all_inventory, add_recipe_item, get_all_recipes,
    delete_recipe_item, sell_menu, set_menu_price, get_menu_price,
    add_sale_log, get_all_sales, get_menu_list, create_order,
    get_active_orders, get_order_items, update_order_status
)

# ---------------- ตั้งค่าร้าน (แก้ตรงนี้ให้เป็นร้านของพี่ได้เลย) ----------------
RESTAURANT_NAME = "YANAGI"
LOGO_EMOJI = "🍽️"
LOGO_PATH = "logo.png"  # ถ้ามีไฟล์รูปโลโก้จริง วางไว้โฟลเดอร์เดียวกับ app.py แล้วตั้งชื่อ logo.png

st.set_page_config(page_title=f"ระบบจัดการร้านอาหาร - {RESTAURANT_NAME}", page_icon=LOGO_EMOJI, layout="wide")

init_db()


def complete_order(order_id, table_no):
    """ตอนกด 'เสร็จแล้ว' ในหน้าครัว: ตัดสต็อกวัตถุดิบ + บันทึกยอดขายให้อัตโนมัติ"""
    items_df = get_order_items(order_id)
    sale_time = str(datetime.now())
    total = 0
    for _, item in items_df.iterrows():
        sell_menu(item["menu_name"], int(item["qty"]))
        line_total = item["qty"] * item["price"]
        total += line_total
        add_sale_log(sale_time, item["menu_name"], int(item["qty"]), line_total)
    add_transaction(sale_time, "income", "ขายอาหาร", total, f"ออเดอร์โต๊ะ {table_no} (สแกน QR)")
    update_order_status(order_id, "เสร็จแล้ว")


# ================= หน้าสั่งอาหารสำหรับลูกค้า (ไม่ต้อง login) =================
query_params = st.query_params
if query_params.get("page") == "order":
    st.title(f"{LOGO_EMOJI} สั่งอาหาร - {RESTAURANT_NAME}")

    prefill_table = query_params.get("table", "")
    menu_df = get_menu_list()

    if menu_df.empty:
        st.info("ร้านยังไม่ได้เปิดรับออเดอร์ในขณะนี้ครับ")
    else:
        with st.form("customer_order_form"):
            table_no = st.text_input("หมายเลขโต๊ะ", value=prefill_table)
            st.write("เลือกเมนูที่ต้องการสั่ง:")

            qty_inputs = {}
            for _, row in menu_df.iterrows():
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
# อ่านรหัสผ่านจาก Streamlit Secrets แทนการฝังไว้ในโค้ดตรงๆ (ปลอดภัยกว่า)
# วิธีตั้งค่า: ในเครื่อง ใช้ไฟล์ .streamlit/secrets.toml
#            บน Streamlit Cloud ตั้งค่าใน Settings > Secrets ของแอป
USERNAME = st.secrets.get("APP_USERNAME", "MSAN")
PASSWORD = st.secrets.get("APP_PASSWORD", "8899M")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🔒 เข้าสู่ระบบ")

    with st.form("login_form"):
        input_username = st.text_input("ชื่อผู้ใช้")
        input_password = st.text_input("รหัสผ่าน", type="password")
        login_submitted = st.form_submit_button("เข้าสู่ระบบ")

        if login_submitted:
            if input_username == USERNAME and input_password == PASSWORD:
                st.session_state.logged_in = True
                st.rerun()
            else:
                st.error("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
    st.stop()

# ---------------- Sidebar: โลโก้ + ชื่อร้าน + เมนูนำทาง ----------------
with st.sidebar:
    if os.path.exists(LOGO_PATH):
        st.image(LOGO_PATH, width=90)
    else:
        st.markdown(f"<div style='font-size:60px; text-align:center'>{LOGO_EMOJI}</div>", unsafe_allow_html=True)

    st.markdown(f"<h3 style='text-align:center'>{RESTAURANT_NAME}</h3>", unsafe_allow_html=True)
    st.divider()

    page = st.radio(
        "เมนู",
        [
            "🏠 หน้าหลัก",
            "📝 การเงิน",
            "📦 สต็อกวัตถุดิบ",
            "🍳 สูตรอาหาร",
            "🧾 ขายเมนู",
            "📊 รายงานยอดขาย",
            "👨‍🍳 ครัว (ออเดอร์)",
            "📱 QR สั่งอาหาร",
        ],
        label_visibility="collapsed",
    )

    st.divider()
    if st.button("🚪 ออกจากระบบ"):
        st.session_state.logged_in = False
        st.rerun()

# ================= หน้า: หน้าหลัก (แดชบอร์ด) =================
if page == "🏠 หน้าหลัก":
    st.title(f"{LOGO_EMOJI} {RESTAURANT_NAME}")
    st.caption("👋 สวัสดีครับ วันนี้ร้านเรามีอะไรบ้าง")

    _dashboard_df = get_all_transactions()
    _dashboard_inventory = get_all_inventory()

    col_a, col_b, col_c = st.columns(3)

    with col_a:
        if not _dashboard_df.empty:
            _dashboard_df["date"] = pd.to_datetime(_dashboard_df["date"])
            _this_month = _dashboard_df[
                (_dashboard_df["date"].dt.month == date.today().month) &
                (_dashboard_df["date"].dt.year == date.today().year)
            ]
            _income = _this_month[_this_month["type"] == "income"]["amount"].sum()
            _expense = _this_month[_this_month["type"] == "expense"]["amount"].sum()
            st.metric("💰 รายรับเดือนนี้", f"{_income:,.0f} บาท")
            st.caption(f"รายจ่าย {_expense:,.0f} บาท")
        else:
            st.metric("💰 รายรับเดือนนี้", "0 บาท")

    with col_b:
        if not _dashboard_inventory.empty:
            _low = _dashboard_inventory[
                _dashboard_inventory["quantity"] <= _dashboard_inventory["low_stock_threshold"]
            ]
            st.metric("📦 ของใกล้หมด", f"{len(_low)} รายการ")
            if not _low.empty:
                st.caption(" • ".join(_low["item_name"].tolist()))
        else:
            st.metric("📦 ของใกล้หมด", "0 รายการ")

    with col_c:
        active_orders_count = len(get_active_orders())
        st.metric("🧾 ออเดอร์ที่ยังไม่เสร็จ", f"{active_orders_count} ออเดอร์")
        if active_orders_count > 0:
            st.caption("ไปที่เมนู 👨‍🍳 ครัว (ออเดอร์) เพื่อดูรายละเอียด")

# ================= หน้า: การเงิน =================
elif page == "📝 การเงิน":
    st.header("📝 บันทึกรายรับ-รายจ่าย")

    with st.form("transaction_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            trans_date = st.date_input("วันที่", value=date.today())
            trans_type = st.selectbox(
                "ประเภท", ["income", "expense"],
                format_func=lambda x: "รายรับ" if x == "income" else "รายจ่าย"
            )
        with col2:
            category = st.text_input("หมวดหมู่ (เช่น ขายอาหาร, ค่าวัตถุดิบ)")
            amount = st.number_input("จำนวนเงิน (บาท)", min_value=0.0, step=1.0)
        note = st.text_input("หมายเหตุ (ถ้ามี)")

        submitted = st.form_submit_button("💾 บันทึกรายการ")
        if submitted:
            if category:
                add_transaction(str(datetime.now()), trans_type, category, amount, note)
                st.success("บันทึกรายการเรียบร้อยแล้ว! ✅")
                st.rerun()
            else:
                st.error("กรุณากรอกหมวดหมู่")

    st.header("📊 สรุปยอดรายรับ-รายจ่าย")
    df = get_all_transactions()

    if df.empty:
        st.info("ยังไม่มีรายการบันทึกไว้")
    else:
        df["date"] = pd.to_datetime(df["date"])

        period = st.radio(
            "เลือกช่วงเวลา", ["เดือนนี้", "สัปดาห์นี้", "ทั้งหมด", "กำหนดเอง"], horizontal=True
        )

        if period == "ทั้งหมด":
            filtered_df = df
        elif period == "เดือนนี้":
            filtered_df = df[
                (df["date"].dt.month == date.today().month) &
                (df["date"].dt.year == date.today().year)
            ]
        elif period == "สัปดาห์นี้":
            start_date = date.today() - timedelta(days=7)
            filtered_df = df[df["date"] >= pd.Timestamp(start_date)]
        else:  # กำหนดเอง
            col_start, col_end = st.columns(2)
            with col_start:
                start_date = st.date_input("วันที่เริ่มต้น", value=date.today() - timedelta(days=30))
            with col_end:
                end_date = st.date_input("วันที่สิ้นสุด", value=date.today())
            filtered_df = df[
                (df["date"] >= pd.Timestamp(start_date)) &
                (df["date"] <= pd.Timestamp(end_date))
            ]

        total_income = filtered_df[filtered_df["type"] == "income"]["amount"].sum()
        total_expense = filtered_df[filtered_df["type"] == "expense"]["amount"].sum()
        net_profit = total_income - total_expense

        c1, c2, c3 = st.columns(3)
        c1.metric("💰 รายรับรวม", f"{total_income:,.2f} บาท")
        c2.metric("💸 รายจ่ายรวม", f"{total_expense:,.2f} บาท")
        c3.metric("📈 กำไรสุทธิ", f"{net_profit:,.2f} บาท")

        chart_data = pd.DataFrame(
            {"ยอดเงิน": [total_income, total_expense]}, index=["รายรับ", "รายจ่าย"]
        )
        st.bar_chart(chart_data)

        daily_data = filtered_df.groupby(filtered_df["date"].dt.date)["amount"].sum()
        st.line_chart(daily_data)

        st.subheader("📋 ประวัติรายการ")
        st.dataframe(filtered_df, use_container_width=True)

        st.subheader("🗑️ ลบรายการ")
        df["label"] = (
            df["id"].astype(str) + " | " + df["date"].astype(str) + " | " +
            df["type"] + " | " + df["category"] + " | " + df["amount"].astype(str) + " บาท"
        )
        selected_label = st.selectbox("เลือกรายการที่ต้องการลบ", df["label"])
        selected_id = int(selected_label.split(" | ")[0])

        if st.button("🗑️ ลบรายการนี้"):
            delete_transaction(selected_id)
            st.success("ลบรายการเรียบร้อยแล้ว! ✅")
            st.rerun()

# ================= หน้า: สต็อกวัตถุดิบ =================
elif page == "📦 สต็อกวัตถุดิบ":
    st.header("📦 จัดการวัตถุดิบคงคลัง")

    with st.form("inventory_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            item_name = st.text_input("ชื่อวัตถุดิบ")
            quantity = st.number_input("จำนวนที่เพิ่ม", min_value=0.0, step=1.0)
        with col2:
            unit = st.text_input("หน่วย (เช่น กก., ฟอง, ลิตร)")
            threshold = st.number_input("จุดแจ้งเตือนของใกล้หมด", min_value=0.0, step=1.0)

        submitted_item = st.form_submit_button("📥 เพิ่ม/อัปเดตวัตถุดิบ")
        if submitted_item:
            if item_name and unit:
                add_or_update_item(item_name, quantity, unit, threshold)
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

# ================= หน้า: สูตรอาหาร =================
elif page == "🍳 สูตรอาหาร":
    st.header("🍳 จัดการสูตรอาหาร")

    with st.form("recipe_form", clear_on_submit=True):
        menu_name = st.text_input("ชื่อเมนู")
        item_name_recipe = st.text_input("ชื่อวัตถุดิบที่ใช้")
        qty_used = st.number_input("จำนวนที่ใช้ต่อจาน", min_value=0.0, step=0.1)
        price = st.number_input("ราคาขายต่อจาน (บาท)", min_value=0.0, step=1.0)

        submitted_recipe = st.form_submit_button("➕ เพิ่มวัตถุดิบเข้าสูตรอาหาร")
        if submitted_recipe:
            if menu_name and item_name_recipe:
                add_recipe_item(menu_name, item_name_recipe, qty_used)
                set_menu_price(menu_name, price)
                st.success(f"เพิ่ม '{item_name_recipe}' เข้าสูตร '{menu_name}' เรียบร้อยแล้ว! ✅")
                st.rerun()
            else:
                st.error("กรุณากรอกชื่อเมนูและวัตถุดิบให้ครบ")

    recipes_df = get_all_recipes()
    if recipes_df.empty:
        st.info("ยังไม่มีสูตรอาหารในระบบ")
    else:
        st.subheader("📋 สูตรอาหารทั้งหมด")
        st.dataframe(recipes_df, use_container_width=True)

        st.subheader("🗑️ ลบวัตถุดิบออกจากสูตร")
        recipes_df["label"] = (
            recipes_df["id"].astype(str) + " | " + recipes_df["menu_name"] +
            " ใช้ " + recipes_df["item_name"] + " (" +
            recipes_df["quantity_used"].astype(str) + ")"
        )
        selected_recipe_label = st.selectbox(
            "เลือกรายการที่ต้องการลบ", recipes_df["label"], key="delete_recipe_select"
        )
        selected_recipe_id = int(selected_recipe_label.split(" | ")[0])

        if st.button("🗑️ ลบรายการนี้ออกจากสูตร"):
            delete_recipe_item(selected_recipe_id)
            st.success("ลบรายการเรียบร้อยแล้ว! ✅")
            st.rerun()

        st.subheader("💰 แก้ไขราคาขายเมนู")
        menu_names_for_price = recipes_df["menu_name"].unique()
        selected_menu_for_price = st.selectbox(
            "เลือกเมนูที่จะแก้ไขราคา", menu_names_for_price, key="edit_price_select"
        )
        current_price = get_menu_price(selected_menu_for_price)
        new_price = st.number_input(
            "ราคาขายใหม่ (บาท)", min_value=0.0, step=1.0,
            value=float(current_price), key="edit_price_input"
        )
        if st.button("💾 อัปเดตราคาขาย"):
            set_menu_price(selected_menu_for_price, new_price)
            st.success(f"อัปเดตราคา '{selected_menu_for_price}' เป็น {new_price:,.0f} บาท เรียบร้อย! ✅")
            st.rerun()

# ================= หน้า: ขายเมนู =================
elif page == "🧾 ขายเมนู":
    st.header("🧾 ขายเมนู")
    st.caption("ใช้หน้านี้เวลาลูกค้าสั่งที่หน้าร้านโดยตรง (ไม่ผ่าน QR)")

    recipes_df = get_all_recipes()
    if recipes_df.empty:
        st.info("ยังไม่มีสูตรอาหารในระบบ กรุณาเพิ่มสูตรก่อน (ไปที่เมนู 🍳 สูตรอาหาร)")
    else:
        menu_list = recipes_df["menu_name"].unique()

        with st.form("sell_form", clear_on_submit=True):
            selected_menu = st.selectbox("เลือกเมนูที่ขาย", menu_list)
            qty_sold = st.number_input("จำนวนจานที่ขาย", min_value=1, step=1)

            submitted_sell = st.form_submit_button("🧾 บันทึกการขาย")
            if submitted_sell:
                sell_menu(selected_menu, qty_sold)
                price = get_menu_price(selected_menu)
                total_price = price * qty_sold
                sale_time = str(datetime.now())

                add_transaction(
                    sale_time, "income", "ขายอาหาร", total_price,
                    f"ขาย {selected_menu} {qty_sold} จาน"
                )
                add_sale_log(sale_time, selected_menu, qty_sold, total_price)

                st.success(f"ขาย '{selected_menu}' จำนวน {qty_sold} จาน เรียบร้อย! ✅")
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
            .agg(จำนวนที่ขาย=("qty_sold", "sum"), ยอดขายรวม=("total_price", "sum"))
            .sort_values("จำนวนที่ขาย", ascending=False)
        )

        top5 = summary.head(5)

        st.subheader("🏆 เมนูขายดี Top 5 (นับจากจำนวนจาน)")
        st.bar_chart(top5["จำนวนที่ขาย"])
        st.dataframe(top5, use_container_width=True)

        st.subheader("📋 ประวัติการขายทั้งหมด")
        st.dataframe(sales_df, use_container_width=True)

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

                col1, col2 = st.columns(2)
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

# ================= หน้า: QR สั่งอาหาร =================
elif page == "📱 QR สั่งอาหาร":
    st.header("📱 สร้าง QR โค้ดสำหรับลูกค้าสั่งอาหาร")
    st.write("ให้ลูกค้าสแกน QR นี้ที่โต๊ะ เพื่อสั่งอาหารได้เองจากมือถือ")

    st.info(
        
        "ลูกค้าสแกนแล้วใช้เน็ตมือถือของตัวเองเปิดได้เลย ไม่ต้องต่อ WiFi ร้าน"
    )

    base_url = st.text_input(
        "ที่อยู่เว็บของร้าน (Base URL)",
        placeholder="เช่น https://yanagi-restaurant-manager-xxxxx.streamlit.app",
    )
    table_number = st.text_input("หมายเลขโต๊ะ", value="1")

    if st.button("🔲 สร้าง QR โค้ด"):
        if not base_url:
            st.error("กรุณากรอกที่อยู่เว็บก่อน")
        else:
            order_url = f"{base_url.rstrip('/')}/?page=order&table={table_number}"
            qr_img = qrcode.make(order_url)
            buf = io.BytesIO()
            qr_img.save(buf, format="PNG")

            st.image(buf.getvalue(), caption=f"QR โต๊ะ {table_number}", width=250)
            st.code(order_url)
            st.download_button(
                "⬇️ ดาวน์โหลด QR",
                data=buf.getvalue(),
                file_name=f"qr_table_{table_number}.png",
                mime="image/png"
            )
