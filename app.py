from datetime import date, timedelta, datetime
import streamlit as st
import pandas as pd
from database import init_db, add_transaction, get_all_transactions, delete_transaction, add_or_update_item, get_all_inventory, add_recipe_item, get_all_recipes, sell_menu

init_db()
st.write("สถานะ login:", st.session_state.get("logged_in"))
USERNAME = "MSAN"
PASSWORD = "1234"

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

st.title("🍽️ ระบบจัดการร้านอาหาร")

st.header("📝 บันทึกรายรับ-รายจ่าย")

with st.form("transaction_form", clear_on_submit=True):
    col1, col2 = st.columns(2)

    with col1:
        trans_date = st.date_input("วันที่", value=date.today())
        trans_type = st.selectbox(
            "ประเภท",
            ["income", "expense"],
            format_func=lambda x: "รายรับ" if x == "income" else "รายจ่าย"
        )

    with col2:
        category = st.text_input("หมวดหมู่ (เช่น ขายอาหาร, ค่าวัตถุดิบ)")
        amount = st.number_input("จำนวนเงิน (บาท)", min_value=0.0, step=1.0)
    note = st.text_input("หมายเหตุ (ถ้ามี)")

    submitted = st.form_submit_button("💾 บันทึกรายการ")

if submitted:
    add_transaction(str(datetime.now()), trans_type, category, amount, note)
    st.success("บันทึกรายการเรียบร้อยแล้ว! ✅")

st.header("📊 สรุปยอดรายรับ-รายจ่าย")

df = get_all_transactions()

if df.empty:
    st.info("ยังไม่มีรายการบันทึกไว้")
else:
    df["date"] = pd.to_datetime(df["date"])

    period = st.radio(
        "เลือกช่วงเวลา",
        ["เดือนนี้", "สัปดาร์นี้", "ทั้งหมด", "กำหนดเอง"],
        horizontal=True
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
        
    elif period == "กำหนดเอง":
        col_start, col_end = st.columns(2)
        with col_start:
            start_date = st.date_input("วันที่เริ่มต้น", value=date.today() - timedelta(days=30))
        with col_end:
            end_date = st.date_input("วันที่สิ้นสุด", value=date.today())

        filtered_df = df[
            (df["date"] <= pd.Timestamp(start_date)) &
            (df["date"] <= pd.Timestamp(end_date))
        ]
    
    total_income = filtered_df[filtered_df["type"] == "income"]["amount"].sum()
    total_expense = filtered_df[filtered_df["type"] == "expense"]["amount"].sum()
    net_profit = total_income - total_expense

    col1, col2, col3 = st.columns(3)
    col1.metric("💰 รายรับรวม", f"{total_income:,.2f} บาท")
    col2.metric("💸 รายจ่ายรวม", f"{total_expense:,.2f} บาท")
    col3.metric("📈 กำไรสุทธิ", f"{net_profit:,.2f} บาท")
    chart_data = pd.DataFrame({
        "ยอดเงิน": [total_income, total_expense]
    }, index=["รายรับ", "รายจ่าย"])

    st.bar_chart(chart_data)

    daily_data = filtered_df.groupby(filtered_df["date"].dt.date)["amount"].sum()
    st.line_chart(daily_data)

    st.subheader("📋 ประวัติรายการ")
    st.dataframe(filtered_df, use_container_width=True)

    st.subheader("🗑️ ลบรายการ")

    df["label"] = df["id"].astype(str) + " | " + df["date"].astype(str) + " | " + df["type"] + " | " + df["category"] + " | " + df["amount"].astype(str) + " บาท"
    
    selected_label = st.selectbox("เลือกรายการที่ต้องการลบ", df["label"])
    selected_id = int(selected_label.split(" | ")[0])

    if st.button("🗑️ ลบรายการนี้"):
        delete_transaction(selected_id)
        st.success("ลบรายการเรียบร้อยแล้ว! ✅")
        st.rerun()
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
        else:
            st.error("กรุณากรอกชื่อวัตถุดิบและหน่วยให้ครบ")

inventory_df = get_all_inventory()

if inventory_df.empty:
    st.info("ยังไม่มีวัตถุดิบในระบบ")
else:
    low_stock = inventory_df[inventory_df["quantity"]<= inventory_df["low_stock_th" \
"eshold"]]

    if not low_stock.empty:
        st.warning("⚠️ วัตถุดิบใกล้หมด!")
        for _, row in low_stock.iterrows():
            st.error(f"🔴{row['item_name']} เหลือ {row['quantity']} {row['unit']}")

    st.subheader("📋 รายการวัตถุดิบทั้งหมด")
    st.dataframe(inventory_df, use_container_width=True)
    st.header("🍜 จัดการสูตรอาหาร")

    with st.form("recipe_form", clear_on_submit=True):
        menu_name = st.text_input("ชื่อเมนู")
        item_name_recipe = st.text_input("ชื่อวัตถุดิบที่ใช้")
        qty_used = st.number_input("จำนวนที่ใช้ต่อจาน", min_value=0.0, step=0.1)

        submitted_recipe = st.form_submit_button("+ เพิ่ทวัตถุดิบเข้าสูตรอาหาร")

        if submitted_recipe:
            if menu_name and item_name_recipe:
                add_recipe_item(menu_name, item_name_recipe, qty_used)
                st.success(f"เพิ่ม '{item_name_recipe}' เข้าสูตร ' {menu_name}' เรียบร้อยแล้ว! ✅")
            else:
                st.error("กรุณากรอกชื่อเมนูและวัตถุดิบให้ครบ")

recipes_df = get_all_recipes()

if recipes_df.empty:
    st.info("ยังไม่มีสูตรอาหารในระบบ")
else:
    st.subheader("📋 สูตรอาหารทั้งหมด")
    st.dataframe(recipes_df, use_container_width=True)
st.header("🧾 ขายเมนู")

recipes_df = get_all_recipes()

if recipes_df.empty:
    st.info("ยังไม่มีสูตรอาหารในระบบ กรุณาเพิ่มสูตรก่อน")
else:
    menu_list = recipes_df["menu_name"].unique()

    with st.form("sell_form", clear_on_submit=True):
        selected_menu = st.selectbox("เลือกเมนนูที่ขาย", menu_list)
        qty_sold = st.number_input("จำนวนจานที่ขาย", min_value=1, step=1)

        submitted_sell = st.form_submit_button("🧾 บันทึกการขาย")

        if submitted_sell :
           sell_menu(selected_menu, qty_sold)
           st.success(f"ขาย '{selected_menu}' จำนวน {qty_sold} จาน เรียบร้อย! ✅")