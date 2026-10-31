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
    st.subheader("📊 ใบแจ้งหนี้และสรุปยอดค่าใช้จ่าย")
    
    col_btn1, col_btn2 = st.columns([1, 4])
    with col_btn1:
        if st.button("🔄 โหลดข้อมูล"):
            st.cache_data.clear()
            st.rerun()
            
    try:
        with st.spinner("กำลังดึงข้อมูลใบแจ้งหนี้"):
            gold_df = load_gold_layer_bills()
            
        if not gold_df.empty:
            # แสดง KPI สรุปภาพรวม
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(label="จำนวนบิลทั้งหมด", value=f"{len(gold_df)} รายการ")
            with col2:
                total_rev = gold_df["total_charge"].sum() if "total_charge" in gold_df.columns else 0
                st.metric(label="ยอดเรียกเก็บรวม", value=f"{total_rev:,.2f} บาท")
            with col3:
                st.metric(label="แหล่งข้อมูล", value="Databricks Delta Table", delta="Gold Layer")
                
            st.markdown("---")
            
            # เพิ่มฟิลเตอร์กรองดูตามห้องพัก
            selected_room = st.selectbox("กรองดูตามห้องพัก", options=["ทั้งหมด"] + list(gold_df["room_id"].unique()))
            
            filtered_df = gold_df if selected_room == "ทั้งหมด" else gold_df[gold_df["room_id"] == selected_room]
            
            st.dataframe(filtered_df, use_container_width=True)
        else:
            st.info("ยังไม่มีข้อมูลในตาราง Gold Layer บน Databricks")
    except Exception as e:
        st.error(f"❌ ไม่สามารถเชื่อมต่อหรือดึงข้อมูลได้: {e}")
        st.info("💡 คำแนะนำ: ตรวจสอบค่า `server_hostname`, `http_path` และ `access_token` ใน Streamlit Secrets ว่าถูกต้องครบถ้วนหรือไม่")