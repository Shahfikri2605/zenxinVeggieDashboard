import streamlit as st
import pandas as pd
import re
from streamlit_gsheets import GSheetsConnection
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(layout="wide", page_title="Zenxin Veggie Dashboard")


SHEET_MAPPING = {
    "NTUC": st.secrets["sheet_ids"]["ntuc"], 
    "CS": st.secrets["sheet_ids"]["cs"],
    "SS": st.secrets["sheet_ids"]["ss"]
}
@st.cache_resource
def get_gspread_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    return gspread.authorize(creds)

@st.cache_data(ttl=600)
def load_data(sheet_id):
    try:
        client = get_gspread_client()
        sh = client.open_by_key(sheet_id)
        worksheet = sh.get_worksheet(0)
        data = worksheet.get_all_values()
        
        if not data:
            return pd.DataFrame()
            
        df = pd.DataFrame(data[1:], columns=data[0])
        
        
        df = df[df['Location'] != ""]
        df = df[df['Date'] != ""]
        
       
        if 'Date' in df.columns:
            df['Date_dt'] = pd.to_datetime(df['Date'], format='mixed', dayfirst=False, errors='coerce')
        
        
        if 'Time' in df.columns:
            df['Time_sort'] = pd.to_timedelta(df['Time'].astype(str), errors='coerce')
            
        return df

    except Exception as e:
        st.error(f"Error loading sheet: {e}")
        return pd.DataFrame()


st.markdown("""
    <style>
    thead tr th:first-child {display:none !important;}
    tbody th { display:none !important; }
    .stTable { font-size: 22px !important; width: 100%; }
    th { background-color: #1b5e20 !important; color: white !important; font-size: 24px; text-align: left !important; }
    td { color: #ffffff !important; border-bottom: 1px solid #444 !important; height: 50px; }
    .main { background-color: #0e1117; }
    
    .table-header {
        font-size: 32px; font-weight: bold; padding: 10px;
        border-radius: 5px; margin-bottom: 10px; text-align: center;
    }
    .req-header { background-color: #2e7d32; color: white; }
    .red-header { background-color: #c62828; color: white; }
    
    /* Search Button Styling */
    div.stButton > button {
        width: 100%;
        background-color: #FFC107;
        color: black;
        font-size: 24px;
        font-weight: bold;
        padding: 10px;
    }
    </style>
    """, unsafe_allow_html=True)


def split_item_and_origin(item):
    if not isinstance(item, str) or 'N/A' in item or item.strip() == '' or item.lower() in ['nan', 'none']:
        return None, None
    match = re.search(r'\b(MYS|THA|USA|EU|AUS|ARG|ESP|PER|PRT|BRA|ITA|NZL|ZAF|CHN|VNM)\b', item)
    if match:
        origin_code = match.group(0)
        clean_name = item.replace(origin_code, "").strip()
        origin_label = origin_code if origin_code in ['MYS', 'THA'] else f"Imported ({origin_code})"
        return clean_name, origin_label
    return item, "Imported"




if 'search_clicked' not in st.session_state:
    st.session_state.search_clicked = False

st.title("🥬 Zenxin Veggie Replenishment Dashboard")

selected_store = st.selectbox("Select Store Chain:", list(SHEET_MAPPING.keys()))

c1, c2, c3, c4 = st.columns(4)

with c1:
    today = datetime.now().date()
    date_range = st.date_input("📅 Date Range", value=(today, today))

with c2:
    try:
        pre_load = load_data(SHEET_MAPPING[selected_store])
        u_locs = sorted(pre_load['Location'].dropna().unique())
        u_origins = sorted([x for x in pre_load.stack().apply(lambda s: split_item_and_origin(str(s))[1]).unique() if x])
    except:
        u_locs = []
        u_origins = []
        
    loc_options = ["ALL"] + u_locs
    sel_locs = st.multiselect("📍 Location", loc_options, default=["ALL"])

with c3:
    origin_options = ["ALL"] + ["MYS", "THA", "Imported"] 
    sel_origins = st.multiselect("🌍 Origin", origin_options, default=["ALL"])

with c4:
    type_options = ["REQUEST", "REDUCE"]
    sel_types = st.multiselect("⚖️ Type", type_options, default=["REQUEST", "REDUCE"])

if st.button("🔎 SHOW DATA"):
    st.session_state.search_clicked = True

if st.session_state.search_clicked:
    try:
        current_url = SHEET_MAPPING[selected_store]
        raw_data = load_data(current_url)
        raw_data = raw_data.dropna(subset=['Date_dt']).sort_values(by=['Date_dt', 'Time_sort'], ascending=[False, False])

        all_rows = []
        for _, row in raw_data.iterrows():
            for col in [c for c in raw_data.columns if 'request' in c.lower() or 'reduce' in c.lower()]:
                name, origin = split_item_and_origin(row.get(col))
                if name:
                    v_type = "REQUEST" if 'request' in col.lower() else "REDUCE"
                    all_rows.append({
                        "Date": row['Date_dt'].date(),
                        "Location": row['Location'],
                        "Type": v_type,
                        "Vegetable": name,
                        "Origin": origin
                    })

        df_display = pd.DataFrame(all_rows)

        if not df_display.empty:
            start, end = date_range if len(date_range) == 2 else (date_range[0], date_range[0])
            
            final_locs = u_locs if "ALL" in sel_locs else sel_locs
            mask_origin = df_display['Origin'].apply(lambda x: any(o in str(x) for o in sel_origins)) if "ALL" not in sel_origins else True

            mask = (df_display['Date'] >= start) & (df_display['Date'] <= end) & \
                   (df_display['Location'].isin(final_locs)) & \
                   (mask_origin) & \
                   (df_display['Type'].isin(sel_types))

            filtered_df = df_display[mask].copy()

            st.divider()
            st.markdown(f"### Results for {selected_store} ({start} to {end})")

            df_request = filtered_df[filtered_df['Type'] == 'REQUEST'][["Location", "Vegetable", "Origin"]]
            df_reduce = filtered_df[filtered_df['Type'] == 'REDUCE'][["Location", "Vegetable", "Origin"]]

            show_req = "REQUEST" in sel_types
            show_red = "REDUCE" in sel_types

            if show_req and show_red:
                c_left, c_right = st.columns(2)
                with c_left:
                    st.markdown('<div class="table-header req-header">📥 REQUEST LIST</div>', unsafe_allow_html=True)
                    st.table(df_request)
                with c_right:
                    st.markdown('<div class="table-header red-header">📤 REDUCE LIST</div>', unsafe_allow_html=True)
                    st.table(df_reduce)
            
            elif show_req:
                st.markdown('<div class="table-header req-header">📥 REQUEST LIST</div>', unsafe_allow_html=True)
                st.table(df_request)
                
            elif show_red:
                st.markdown('<div class="table-header red-header">📤 REDUCE LIST</div>', unsafe_allow_html=True)
                st.table(df_reduce)

        else:
            st.warning("No data found in the selected sheet.")

    except Exception as e:
        st.error(f"Error: {e}")
