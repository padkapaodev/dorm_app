import datetime
import pandas as pd
import psycopg2
import streamlit as st
from databricks import sql

# ตั้งค่าหน้าจอ App
st.set_page_config(page_title="ระบบจัดการหอพักคุณแม่", page_icon="🏢", layout="wide")

# ฟังก์ชันเชื่อมต่อ Neon PostgreSQL (สำหรับบันทึกข้อมูลมิเตอร์ดิบ)
def get_db_connection():
    conn = psycopg2.connect(st.secrets["DATABASE_URL"])
    return conn

# ฟังก์ชันเชื่อมต่อ Databricks เพื่อดึงข้อมูล Gold Layer (บิลรายเดือนที่คำนวณแล้ว)
@st.cache_data(ttl=300)
def load_gold_layer_bills():
    connection = sql.connect(
        server_hostname=st.secrets["server_hostname"],
        http_path=st.secrets["http_path"],
        access_token=st.secrets["access_token"]
    )
    query = "SELECT * FROM workspace.project_catalog.gold_layer ORDER BY bill_date DESC, room_id ASC;"
    df = pd.read_sql(query, connection)
    connection.close()
    return df

st.title("ระบบจัดการบิลหอพักและค่าน้ำ-ค่าไฟ")
st.caption("ระบบบันทึกมิเตอร์และแสดงผลใบแจ้งหนี้")

# สร้าง Tabs สำหรับสลับหน้าทำงาน
tab1, tab2, tab3 = st.tabs(["📝 บันทึกมิเตอร์ประจำเดือน", "📋 ประวัติการจดมิเตอร์", "📊 ใบแจ้งหนี้รายเดือน"])

with tab1:
    st.subheader("ฟอร์มบันทึกค่ามิเตอร์ประจำเดือน")
    
    with st.form("bill_entry_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            room_id = st.selectbox("เลขห้องพัก", options=[1, 2, 3, 4], index=0)
            bill_date = st.date_input("วันที่บันทึก/วันที่บิล", value=datetime.date.today())
            
        with col2:
            elec_meter = st.number_input("เลขมิเตอร์ไฟ (kWh)", min_value=0, step=1, value=0)
            water_meter = st.number_input("เลขมิเตอร์น้ำ (ลบ.ม.)", min_value=0.0, step=0.1, value=0.0)
            
        note = st.text_input("หมายเหตุ (ถ้ามี)", placeholder="เช่น ย้ายออก / ซ่อมมิเตอร์")
        
        submitted = st.form_submit_button("💾 บันทึกข้อมูลเข้าระบบ")
        
        if submitted:
            date_str = bill_date.strftime("%Y%m")
            bill_id = f"{date_str}-{room_id}"
            
            try:
                conn = get_db_connection()
                cur = conn.cursor()
                
                insert_query = """
                    INSERT INTO dorm_bills (bill_id, room_id, bill_date, elec_meter, water_meter, note)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (bill_id) 
                    DO UPDATE SET 
                        elec_meter = EXCLUDED.elec_meter,
                        water_meter = EXCLUDED.water_meter,
                        note = EXCLUDED.note,
                        bill_date = EXCLUDED.bill_date;
                """
                cur.execute(insert_query, (bill_id, room_id, bill_date, elec_meter, water_meter, note))
                conn.commit()
                cur.close()
                conn.close()
                
                st.success(f"✅ บันทึกข้อมูลสำเร็จ! (Bill ID: {bill_id})")
            except Exception as e:
                st.error(f"❌ เกิดข้อผิดพลาดในการบันทึกข้อมูล: {e}")

with tab2:
    st.subheader("รายการมิเตอร์ที่บันทึกล่าสุด")
    if st.button("🔄 รีเฟรชข้อมูลมิเตอร์"):
        st.rerun()
        
    try:
        conn = get_db_connection()
        query = """
            SELECT bill_id, room_id, bill_date, elec_meter, water_meter, note 
            FROM dorm_bills 
            ORDER BY bill_date DESC, room_id ASC 
            LIMIT 20;
        """
        bills_df = pd.read_sql(query, conn)
        conn.close()
        st.dataframe(bills_df, use_container_width=True)
    except Exception as e:
        st.error(f"ไม่สามารถดึงข้อมูลได้: {e}")

with tab3:
    st.subheader("📊 ใบแจ้งหนี้และสร้างบิลรายห้อง")
    st.caption("เลือกห้องและงวดบิลด้านล่างเพื่อดูใบแจ้งหนี้สำหรับแคปเจอร์ส่งให้ผู้เช่า")
    
    try:
        gold_df = load_gold_layer_bills()
        
        if not gold_df.empty:
            # สร้างตัวเลือกห้องพักแบบใช้งานง่าย
            col_sel1, col_sel2 = st.columns(2)
            with col_sel1:
                available_rooms = sorted(gold_df["room_id"].unique())
                selected_room = st.selectbox("🚪 เลือกห้องพัก", options=available_rooms, format_func=lambda x: f"ห้องพักที่ {x}")
            with col_sel2:
                # กรองเฉพาะบิลของห้องที่เลือก
                room_bills = gold_df[gold_df["room_id"] == selected_room]
                selected_bill_id = st.selectbox("📅 เลือกงวดประจำเดือน (Bill ID)", options=room_bills["bill_id"].unique())
            
            # ดึงข้อมูลของบิลที่เลือก
            current_bill = room_bills[room_bills["bill_id"] == selected_bill_id].iloc[0]
            
            # แปลงวันที่เป็นชื่อเดือนภาษาไทย
            bill_date_obj = pd.to_datetime(current_bill['bill_date'])
            thai_months = {
                1: "มกราคม", 2: "กุมภาพันธ์", 3: "มีนาคม", 4: "เมษายน", 
                5: "พฤษภาคม", 6: "มิถุนายน", 7: "กรกฎาคม", 8: "สิงหาคม", 
                9: "กันยายน", 10: "ตุลาคม", 11: "พฤศจิกายน", 12: "ธันวาคม"
            }
            month_name = thai_months.get(bill_date_obj.month, "")
            year_th = bill_date_obj.year + 543
            formatted_period = f"{month_name} {year_th}"
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            # -----------------------------------------------------------------
            # ส่วนแสดงผลใบเสร็จ (ปรับขนาดความสูงให้พอดี ไม่โดนตัดบนมือถือ)
            # -----------------------------------------------------------------
            import streamlit.components.v1 as components

            receipt_code = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{
                        font-family: sans-serif;
                        background-color: #ffffff;
                        color: #222222;
                        margin: 0;
                        padding: 5px;
                    }}
                    .receipt-box {{
                        border: 3px solid #2E7D32; 
                        padding: 20px; 
                        border-radius: 15px; 
                        background-color: #ffffff; 
                        box-shadow: 0 4px 10px rgba(0,0,0,0.1);
                        max-width: 550px;
                        margin: 0 auto;
                    }}
                    .header {{
                        text-align: center;
                    }}
                    .room-badge {{
                        font-size: 16px; 
                        margin-bottom: 12px; 
                        background-color: #f1f8e9; 
                        padding: 10px 15px; 
                        border-radius: 8px;
                    }}
                    .row-item {{
                        display: flex; 
                        justify-content: space-between; 
                        border-bottom: 1px dashed #eee; 
                        padding: 8px 0;
                        font-size: 15px;
                    }}
                    .total-box {{
                        background-color: #e8f5e9; 
                        padding: 12px; 
                        border-radius: 10px; 
                        text-align: center;
                        margin-top: 12px;
                    }}
                </style>
            </head>
            <body>
                <div class="receipt-box">
                    <div class="header">
                        <h2 style="color: #2E7D32; margin: 0 0 3px 0;">🏢 ใบแจ้งหนี้ค่าเช่าหอพัก</h2>
                        <p style="color: #444; font-size: 15px; margin: 0; font-weight: bold;">ประจำเดือน {formatted_period}</p>
                    </div>
                    
                    <hr style="border: 1px solid #ddd; margin: 12px 0;">
                    
                    <div class="room-badge">
                        🏠 <b>ห้องพักหมายเลข:</b> <span style="font-size: 20px; color: #1b5e20; font-weight: bold;">{current_bill['room_id']}</span><br>
                        <span style="font-size: 12px; color: #555;">รหัสบิล: {current_bill['bill_id']}</span>
                    </div>
                    
                    <div>
                        <div class="row-item">
                            <span>🛏️ ค่าเช่าห้องพัก</span>
                            <b>{current_bill['rent']:,.2f} บาท</b>
                        </div>
                        <div class="row-item">
                            <span>💧 ค่าน้ำ ({current_bill['water_unit_used']} หน่วย)</span>
                            <b>{current_bill['water_charge']:,.2f} บาท</b>
                        </div>
                        <div class="row-item">
                            <span>⚡ ค่าไฟ ({current_bill['elec_unit_used']} หน่วย)</span>
                            <b>{current_bill['elec_charge']:,.2f} บาท</b>
                        </div>
                    </div>
                    
                    <div class="total-box">
                        <p style="margin: 0; font-size: 15px; color: #2e7d32; font-weight: bold;">ยอดรวมสุทธิที่ต้องชำระ</p>
                        <h1 style="margin: 3px 0 0 0; color: #c62828; font-size: 28px;">{current_bill['total_charge']:,.2f} บาท</h1>
                    </div>
                    
                    <p style="text-align: center; font-size: 12px; color: #888; margin: 10px 0 0 0;">
                        หากชำระล่าช้า ปรับเพิ่มวันละ 50 บาทค่ะ 🙏
                    </p>
                </div>
            </body>
            </html>
            """
            
            components.html(receipt_code, height=525, scrolling=False)
            st.markdown("<br>", unsafe_allow_html=True)
            
            # คำแนะนำการใช้งาน
            st.info("💡 **วิธีส่งให้ผู้เช่า:** เพียงแคปเจอร์หน้าจอ (Screenshot) กรอบใบเสร็จด้านบนนี้ แล้วส่งเข้า Line ห้องพักได้ทันที สะดวกและชัดเจนที่สุดครับ!")

        else:
            st.warning("⚠️ ยังไม่มีข้อมูลใบแจ้งหนี้ใน Databricks Gold Layer")
            
    except Exception as e:
        st.error(f"❌ เกิดข้อผิดพลาดในการโหลดข้อมูล: {e}")
