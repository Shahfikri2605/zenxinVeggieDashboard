import streamlit as st
import pandas as pd
import re
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import plotly.express as px
import io # <-- Added for Excel export
import xlsxwriter.utility

st.set_page_config(layout="wide", page_title="Zenxin 3 Request & 3 Reduce Dashboard")

SHEET_MAPPING = {
    "Supermarket MYS": st.secrets["sheet_ids"]["mys"],
    "Retail/Outlet MYS" : st.secrets["sheet_ids"]["outlet"],
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
        if store_name in ['Supermarket MYS','Retail/Outlet MYS']:
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

# --- NEW FUNCTION: Generate Styled Excel ---
import xlsxwriter.utility 
import io
import pandas as pd

def generate_excel(df, selected_store, start_date, end_date):
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book
        
        # --- DEFINE FORMATS ---
        # NEW: Formats for the Report Title and Date
        report_title_format = workbook.add_format({
            'bold': True, 'font_size': 18, 'font_color': '#1b5e20', 'valign': 'vcenter'
        })
        report_date_format = workbook.add_format({
            'italic': True, 'font_size': 12, 'font_color': '#555555', 'valign': 'vcenter'
        })
        
        # Existing Formats
        loc_header_format = workbook.add_format({
            'bold': True, 'bg_color': '#1E1E24', 'font_color': 'white', 'font_size': 12, 'valign': 'vcenter', 'border': 1
        })
        req_title_format = workbook.add_format({'bold': True, 'align': 'center', 'bg_color': '#2e7d32', 'font_color': 'white', 'font_size': 14})
        red_title_format = workbook.add_format({'bold': True, 'align': 'center', 'bg_color': '#c62828', 'font_color': 'white', 'font_size': 14})
        col_header_format = workbook.add_format({'bold': True, 'bg_color': '#1b5e20', 'font_color': 'white', 'bottom': 1})
        req_header_format = workbook.add_format({'bold': True, 'bg_color': '#2e7d32', 'font_color': 'white', 'border': 1})
        red_header_format = workbook.add_format({'bold': True, 'bg_color': '#c62828', 'font_color': 'white', 'border': 1})
        analysis_header_format = workbook.add_format({'bold': True, 'bg_color': '#1b5e20', 'font_color': 'white', 'border': 1})
        sub_header_format = workbook.add_format({'bold': True, 'bg_color': '#e0e0e0', 'border': 1})

        loc_counts = df.groupby('Location').size().reset_index(name='Total')
        loc_order = loc_counts.sort_values(by='Total', ascending=False)['Location'].tolist()
        
        df_full = df.copy()
        df_full['Location'] = pd.Categorical(df_full['Location'], categories=loc_order, ordered=True)
        df_full = df_full.sort_values(['Location', 'Date', 'Vegetable'])

        # =======================================================
        # SHEET 1: TOP LOCATIONS
        # =======================================================
        ws_top = workbook.add_worksheet('Top Locations')
        
        # ADD TITLE & DATE
        ws_top.write('A1', 'Request and Reduce Item Report', report_title_format)
        ws_top.write('A2', f'Date: {start_date} to {end_date}', report_date_format)
        
        current_row = 3 # Shift data down to row 3 (0-indexed, so it's the 4th row)
        
        for loc in loc_order:
            loc_df = df_full[df_full['Location'] == loc]
            req_df = loc_df[loc_df['Type'] == 'REQUEST'].reset_index(drop=True)
            red_df = loc_df[loc_df['Type'] == 'REDUCE'].reset_index(drop=True)
            
            req_count = len(req_df)
            red_count = len(red_df)
            
            header_str = f"📍 {loc}   |   📥 {req_count} Req   |   📤 {red_count} Red"
            ws_top.merge_range(current_row, 0, current_row, 6, header_str, loc_header_format)
            header_row = current_row
            current_row += 1
            
            ws_top.merge_range(current_row, 0, current_row, 2, "📥 REQUEST", req_title_format)
            ws_top.merge_range(current_row, 4, current_row, 6, "📤 REDUCE", red_title_format)
            current_row += 1
            
            headers = ['Vegetable', 'Qty', 'Origin']
            for i, h in enumerate(headers):
                ws_top.write(current_row, i, h, col_header_format)
                ws_top.write(current_row, i+4, h, col_header_format)
            current_row += 1
            
            start_data_row = current_row
            
            for i, row in req_df.iterrows():
                ws_top.write(start_data_row + i, 0, row['Vegetable'])
                ws_top.write(start_data_row + i, 1, row.get('Qty', ''))
                ws_top.write(start_data_row + i, 2, row.get('Origin', ''))
                
            for i, row in red_df.iterrows():
                ws_top.write(start_data_row + i, 4, row['Vegetable'])
                ws_top.write(start_data_row + i, 5, row.get('Qty', ''))
                ws_top.write(start_data_row + i, 6, row.get('Origin', ''))
                
            max_rows = max(len(req_df), len(red_df))
            end_data_row = start_data_row + max_rows
            
            for r in range(header_row + 1, end_data_row):
                ws_top.set_row(r, None, None, {'level': 1, 'hidden': True})
            
            current_row = end_data_row
            ws_top.set_row(current_row, 10) 
            current_row += 1 

        ws_top.set_column('A:A', 30) 
        ws_top.set_column('B:B', 8)  
        ws_top.set_column('C:C', 15) 
        ws_top.set_column('D:D', 3)  
        ws_top.set_column('E:E', 30) 
        ws_top.set_column('F:F', 8)  
        ws_top.set_column('G:G', 15) 
        
        ws_top.outline_settings(symbols_below=False)


        # =======================================================
        # SHEET 2: ALL REQUESTS
        # =======================================================
        df_req = df_full[df_full['Type'] == 'REQUEST'].drop(columns=['Type'])
        # Pass startrow=3 to push the dataframe down
        df_req.to_excel(writer, index=False, sheet_name='All Requests', startrow=3)
        ws_req = writer.sheets['All Requests']
        
        # ADD TITLE & DATE
        ws_req.write('A1', 'Supermarket Request and Reduce Item Report', report_title_format)
        ws_req.write('A2', f'Date: {start_date} to {end_date}', report_date_format)

        for col_num, value in enumerate(df_req.columns.values):
            ws_req.write(3, col_num, value, req_header_format) # Write header on row 3
            max_len = max(df_req[value].astype(str).map(len).max() if not df_req.empty else 0, len(str(value))) + 2
            ws_req.set_column(col_num, col_num, max_len)

        # =======================================================
        # SHEET 3: ALL REDUCES
        # =======================================================
        df_red = df_full[df_full['Type'] == 'REDUCE'].drop(columns=['Type'])
        # Pass startrow=3 to push the dataframe down
        df_red.to_excel(writer, index=False, sheet_name='All Reduces', startrow=3)
        ws_red = writer.sheets['All Reduces']
        
        # ADD TITLE & DATE
        ws_red.write('A1', 'Supermarket Request and Reduce Item Report', report_title_format)
        ws_red.write('A2', f'Date: {start_date} to {end_date}', report_date_format)

        for col_num, value in enumerate(df_red.columns.values):
            ws_red.write(3, col_num, value, red_header_format) # Write header on row 3
            max_len = max(df_red[value].astype(str).map(len).max() if not df_red.empty else 0, len(str(value))) + 2
            ws_red.set_column(col_num, col_num, max_len)

        # =======================================================
        # SHEET 4: ANALYSIS
        # =======================================================
        ws_analysis = workbook.add_worksheet('Analysis')
        
        # ADD TITLE & DATE
        ws_analysis.write('A1', 'Supermarket Request and Reduce Item Report', report_title_format)
        ws_analysis.write('A2', f'Date: {start_date} to {end_date}', report_date_format)
        
        if selected_store == "MYS":
            item_analysis = df.groupby(['Vegetable', 'Type'])['Qty'].sum().unstack(fill_value=0).reset_index()
        else:
            item_analysis = df.groupby(['Vegetable', 'Type']).size().unstack(fill_value=0).reset_index()
            
        for t in ['REQUEST', 'REDUCE']:
            if t not in item_analysis.columns: item_analysis[t] = 0
            
        top_req = item_analysis[['Vegetable', 'REQUEST']].sort_values(by='REQUEST', ascending=False).head(10)
        top_red = item_analysis[['Vegetable', 'REDUCE']].sort_values(by='REDUCE', ascending=False).head(10)
        
        # Shift rows down by 3 (Row 1 becomes Row 4)
        ws_analysis.merge_range('A4:B4', 'Top 10 Requested Items', analysis_header_format)
        ws_analysis.write('A5', 'Vegetable', sub_header_format)
        ws_analysis.write('B5', 'Qty', sub_header_format)
        for i, (index, row) in enumerate(top_req.iterrows()):
            ws_analysis.write(i+5, 0, row['Vegetable'])
            ws_analysis.write(i+5, 1, row['REQUEST'])
            
        ws_analysis.merge_range('D4:E4', 'Top 10 Reduced Items', analysis_header_format)
        ws_analysis.write('D5', 'Vegetable', sub_header_format)
        ws_analysis.write('E5', 'Qty', sub_header_format)
        for i, (index, row) in enumerate(top_red.iterrows()):
            ws_analysis.write(i+5, 3, row['Vegetable'])
            ws_analysis.write(i+5, 4, row['REDUCE'])
            
        ws_analysis.set_column('A:A', 25)
        ws_analysis.set_column('D:D', 25)

        num_req = len(top_req)
        if num_req > 0:
            chart_req = workbook.add_chart({'type': 'bar'})
            chart_req.add_series({
                'name':       'Requested Qty',
                'categories': ['Analysis', 5, 0, 4 + num_req, 0], 
                'values':     ['Analysis', 5, 1, 4 + num_req, 1], 
                'fill':       {'color': '#2e7d32'}
            })
            chart_req.set_title({'name': 'Top 10 Requested Items'})
            chart_req.set_legend({'none': True})
            ws_analysis.insert_chart('A17', chart_req, {'x_scale': 1.2, 'y_scale': 1.2}) # Shifted chart down

        num_red = len(top_red)
        if num_red > 0:
            chart_red = workbook.add_chart({'type': 'bar'})
            chart_red.add_series({
                'name':       'Reduced Qty',
                'categories': ['Analysis', 5, 3, 4 + num_red, 3],
                'values':     ['Analysis', 5, 4, 4 + num_red, 4],
                'fill':       {'color': '#c62828'}
            })
            chart_red.set_title({'name': 'Top 10 Reduced Items'})
            chart_red.set_legend({'none': True})
            ws_analysis.insert_chart('F17', chart_red, {'x_scale': 1.2, 'y_scale': 1.2}) # Shifted chart down

    return output.getvalue()
# -----------------------------------------

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
            # Drop the internal filtering column before exporting/displaying
            filtered_df = filtered_df.drop(columns=['Date_Filter']) 

            st.divider()
            
            # --- ADDED EXCEL DOWNLOAD BUTTON ---
            # --- EXCEL DOWNLOAD BUTTON ---
            col_title, col_download = st.columns([3, 1])
            with col_title:
                st.markdown(f"### Results for {selected_store} ({start} to {end})")
            with col_download:
                # Add start and end to this function call!
                excel_data = generate_excel(filtered_df, selected_store, start, end) 
                
                st.download_button(
                    label="📥 Download Detailed Excel Report",
                    data=excel_data,
                    file_name=f"Zenxin_{selected_store}_Report_{start}_to_{end}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            # -----------------------------------

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
