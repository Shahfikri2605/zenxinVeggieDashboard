import streamlit as st
import pandas as pd
import re
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import plotly.express as px # Added for analysis charts

st.set_page_config(layout="wide", page_title="Zenxin 3 Request & 3 Reduce Dashboard")

SHEET_MAPPING = {
    "MYS": st.secrets["sheet_ids"]["mys"], 
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
def load_data(sheet_id, store_name):
    try:
        client = get_gspread_client()
        sh = client.open_by_key(sheet_id)
        if store_name == "MYS":
            try: worksheet = sh.worksheet("Main Data")
            except: worksheet = sh.get_worksheet(3) 
        else: worksheet = sh.get_worksheet(0)
            
        data = worksheet.get_all_values()
        if not data: return pd.DataFrame()
            
        df = pd.DataFrame(data[1:], columns=data[0])
        df.columns = df.columns.str.strip() 

        if 'Outlet Name' in df.columns: df = df.rename(columns={'Outlet Name': 'Location'})
        if 'Location' in df.columns: df = df[df['Location'].str.strip() != ""]
        if 'Date' in df.columns:
            df = df[df['Date'] != ""]
            df['Date_dt'] = pd.to_datetime(df['Date'], format='mixed', dayfirst=False, errors='coerce')
        if 'Time' in df.columns: df['Time_sort'] = pd.to_timedelta(df['Time'].astype(str), errors='coerce')
        return df
    except Exception as e:
        st.error(f"Error loading sheet: {e}")
        return pd.DataFrame()

# Custom Styling
st.markdown("""
    <style>
    thead tr th:first-child {display:none !important;}
    tbody th { display:none !important; }
    .stTable { font-size: 20px !important; width: 100%; }
    th { background-color: #1b5e20 !important; color: white !important; font-size: 22px; text-align: left !important; }
    td { color: #ffffff !important; border-bottom: 1px solid #444 !important; height: 45px; }
    .table-header { font-size: 24px; font-weight: bold; padding: 10px; border-radius: 5px; margin-bottom: 10px; text-align: center; }
    .req-header { background-color: #2e7d32; color: white; }
    .red-header { background-color: #c62828; color: white; }
    div.stButton > button { width: 100%; background-color: #FFC107; color: black; font-size: 24px; font-weight: bold; padding: 10px; }
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

st.title("🥬 Zenxin 3 Request & 3 Reduce Dashboard")

selected_store = st.selectbox("Select Store Chain:", list(SHEET_MAPPING.keys()))

c1, c2, c3, c4 = st.columns(4)
with c1:
    today = datetime.now().date()
    date_range = st.date_input("📅 Date Range", value=(today, today))
with c2:
    try:
        pre_load = load_data(SHEET_MAPPING[selected_store], selected_store)
        u_locs = sorted(pre_load['Location'].dropna().astype(str).unique())
    except: u_locs = []
    sel_locs = st.multiselect("📍 Location", ["ALL"] + u_locs, default=["ALL"])
with c3:
    sel_origins = st.multiselect("🌍 Origin", ["ALL", "MYS", "THA", "Imported"], default=["ALL"])
with c4:
    sel_types = st.multiselect("⚖️ Type", ["REQUEST", "REDUCE"], default=["REQUEST", "REDUCE"])

if st.button("🔎 SHOW DATA"):
    st.session_state.search_clicked = True

if st.session_state.search_clicked:
    try:
        raw_data = load_data(SHEET_MAPPING[selected_store], selected_store)
        raw_data = raw_data.dropna(subset=['Date_dt']).sort_values(by=['Date_dt', 'Time_sort'], ascending=[False, False])

        all_rows = []
        for _, row in raw_data.iterrows():
            if selected_store == "MYS":
                prefixes = [('Veggie request', 'REQUEST'), ('Veggie reduce', 'REDUCE')]
                for prefix, v_type in prefixes:
                    for i in range(1, 4):
                        veggie_col, qty_col = f"{prefix} {i}", f"{prefix} {i} Qty"
                        if veggie_col in raw_data.columns:
                            name, origin = split_item_and_origin(row.get(veggie_col))
                            if name:
                                qty_val = row.get(qty_col, 0)
                                try: qty_val = float(qty_val) if str(qty_val).strip() != "" else 0
                                except: qty_val = 0
                                all_rows.append({
                                    "Date": row['Date_dt'].date(), "Location": row['Location'], "Type": v_type,
                                    "Vegetable": name, "Qty": qty_val, "Origin": origin
                                })
            else:
                relevant_cols = [c for c in raw_data.columns if ('request' in c.lower() or 'reduce' in c.lower()) and 'qty' not in c.lower()]
                for col in relevant_cols:
                    name, origin = split_item_and_origin(row.get(col))
                    if name:
                        all_rows.append({
                            "Date": row['Date_dt'].date(), "Location": row['Location'], 
                            "Type": "REQUEST" if 'request' in col.lower() else "REDUCE",
                            "Vegetable": name, "Qty": 1, "Origin": origin # Use 1 as count for non-MYS
                        })

        df_display = pd.DataFrame(all_rows)
        if not df_display.empty:
            start, end = date_range if len(date_range) == 2 else (date_range[0], date_range[0])
            df_display['Date_Filter'] = pd.to_datetime(df_display['Date'])
            mask = (df_display['Date_Filter'] >= pd.to_datetime(start)) & (df_display['Date_Filter'] <= pd.to_datetime(end))
            if "ALL" not in sel_locs: mask &= df_display['Location'].isin(sel_locs)
            if "ALL" not in sel_origins: mask &= df_display['Origin'].apply(lambda x: any(o in str(x) for o in sel_origins))
            mask &= df_display['Type'].isin(sel_types)

            filtered_df = df_display[mask].copy()
            st.divider()
            st.markdown(f"### Results for {selected_store} ({start} to {end})")

            # --- TABS ---
            tab1, tab2, tab3 = st.tabs(["🏆 Top Locations", "📋 Full Table View", "📊 Analysis"])

            with tab1: # Location Drilldown
                summary = filtered_df.groupby(['Location', 'Type']).size().unstack(fill_value=0).reset_index()
                for t in ['REQUEST', 'REDUCE']: 
                    if t not in summary.columns: summary[t] = 0
                summary['Total'] = summary['REQUEST'] + summary['REDUCE']
                summary = summary.sort_values(by='Total', ascending=False)
                for _, row in summary.iterrows():
                    with st.expander(f"📍 {row['Location']}   |   📥 {row['REQUEST']} Req   |   📤 {row['REDUCE']} Red"):
                        loc_df = filtered_df[filtered_df['Location'] == row['Location']]
                        cl, cr = st.columns(2)
                        sub_cols = ["Vegetable", "Qty", "Origin"] if selected_store == "MYS" else ["Vegetable", "Origin"]
                        with cl:
                            st.markdown('<div class="table-header req-header">📥 REQUEST</div>', unsafe_allow_html=True)
                            st.table(loc_df[loc_df['Type'] == 'REQUEST'][sub_cols])
                        with cr:
                            st.markdown('<div class="table-header red-header">📤 REDUCE</div>', unsafe_allow_html=True)
                            st.table(loc_df[loc_df['Type'] == 'REDUCE'][sub_cols])

            with tab2: # Full Table
                final_cols = ["Location", "Vegetable", "Qty", "Origin"] if selected_store == "MYS" else ["Location", "Vegetable", "Origin"]
                col_req, col_red = st.columns(2)
                with col_req:
                    st.markdown('<div class="table-header req-header">📥 ALL REQUESTS</div>', unsafe_allow_html=True)
                    st.table(filtered_df[filtered_df['Type'] == 'REQUEST'][final_cols])
                with col_red:
                    st.markdown('<div class="table-header red-header">📤 ALL REDUCES</div>', unsafe_allow_html=True)
                    st.table(filtered_df[filtered_df['Type'] == 'REDUCE'][final_cols])

            with tab3: # --- NEW ANALYSIS TAB ---
                st.subheader("Item Performance Analysis")
                
                # Aggregate by Vegetable and Type
                if selected_store == "MYS":
                    # For MYS, show Total Qty
                    item_analysis = filtered_df.groupby(['Vegetable', 'Type'])['Qty'].sum().unstack(fill_value=0).reset_index()
                else:
                    # For others, show Occurrences
                    item_analysis = filtered_df.groupby(['Vegetable', 'Type']).size().unstack(fill_value=0).reset_index()
                
                for t in ['REQUEST', 'REDUCE']:
                    if t not in item_analysis.columns: item_analysis[t] = 0
                
                item_analysis['Total Activity'] = item_analysis['REQUEST'] + item_analysis['REDUCE']
                item_analysis = item_analysis.sort_values(by='Total Activity', ascending=False)

                # Visualizations
                col_chart1, col_chart2 = st.columns(2)
                
                with col_chart1:
                    st.write("**Top 10 Requested Items**")
                    top_req = item_analysis.sort_values(by='REQUEST', ascending=False).head(10)
                    fig_req = px.bar(top_req, x='Vegetable', y='REQUEST', color_discrete_sequence=['#2e7d32'])
                    st.plotly_chart(fig_req, use_container_width=True)

                with col_chart2:
                    st.write("**Top 10 Reduced Items**")
                    top_red = item_analysis.sort_values(by='REDUCE', ascending=False).head(10)
                    fig_red = px.bar(top_red, x='Vegetable', y='REDUCE', color_discrete_sequence=['#c62828'])
                    st.plotly_chart(fig_red, use_container_width=True)

                st.divider()
                st.write("**Complete Item Summary Table**")
                st.dataframe(item_analysis, use_container_width=True, hide_index=True)

        else: st.warning("No data found for the selected filters.")
    except Exception as e: st.error(f"Error: {e}")
