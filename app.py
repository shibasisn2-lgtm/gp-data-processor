import streamlit as st
import pandas as pd
import pdfplumber
import re
import io

# --- CONFIGURATION & MAPPING ---
HEAD_MAPPING = {
    '0027': '14th Finance Commission',
    '0081': 'Central Finance Commission Grant',
    '0086': '5th State Finance Commission',
    '0088': '4th State Finance Commission',
    '0049': 'Interest Receipts',
    '1601': 'Grants-in-aid',
    '2059': 'Maint. of Community Assets',
    '2215': 'Water Supply & Sanitation',
    '2515': 'Panchayati Raj Programmes',
    '4515': 'Capital Outlay on P.R.',
    '3054': 'Transportation/Roads',
    '2202': 'Education',
    '8658': 'Suspense Account',
    '101': 'Maintenance/Grants',
    '102': 'State Govt Grants',
    '103': 'GP Programmes',
    '800': 'Other Expenditure',
    '80': 'Other Expenditure',
    '37': 'Bank Interest',
    '5S': '5th SFC',
    '4S': '4th SFC',
    'L2': 'Labour Cess',
    'R1': 'Royalty'
}

def get_desc(code):
    return HEAD_MAPPING.get(code, "Description")

def extract_data_from_pdf(file_obj, filename):
    try:
        # Simple filename parsing
        parts = filename.replace('.pdf', '').split(' ')
        dist = parts[0].title() if len(parts) > 0 else "Unknown"
        block = parts[1].title() if len(parts) > 1 else "Unknown"
        gp_name = " ".join(parts[2:]).title() if len(parts) > 2 else "Unknown"
    except:
        dist, block, gp_name = "Angul", "Unknown", filename

    receipts_data = []
    payments_data = []
    current_section = None 
    
    major_head = ""
    minor_head = ""
    detail_head = ""
    
    with pdfplumber.open(file_obj) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text: continue
            
            lines = text.split('\n')
            for line in lines:
                line = line.strip()
                
                # Detect Section Switch
                if "RECEIPTS" in line.upper() and "PAYMENTS" in line.upper():
                    pass 
                elif "RECEIPTS" in line.upper():
                    current_section = "RECEIPTS"
                    major_head, minor_head, detail_head = "", "", ""
                elif "PAYMENTS" in line.upper():
                    current_section = "PAYMENTS"
                    major_head, minor_head, detail_head = "", "", ""

                # 1. Detect Major Head (4 digits)
                match_major = re.match(r'^(\d{4})\s+(.*)', line)
                if match_major:
                    major_head = match_major.group(1)
                    minor_head, detail_head = "", ""
                    continue

                # 2. Detect Minor Head (3 digits)
                match_minor = re.match(r'^(\d{3})\s+(.*)', line)
                if match_minor:
                    minor_head = match_minor.group(1)
                    detail_head = ""
                    continue

                # 3. Detect Detail Head (4 digits starting with 00)
                match_detail = re.match(r'^(00\d{2})\s+(.*)', line)
                if match_detail:
                    detail_head = match_detail.group(1)
                    continue

                # 4. Detect Object Head/Transaction Row
                match_obj = re.search(r'^([A-Z0-9]{2,3})\s+(.*?)\s+([\d,]+\.?\d*)$', line)
                if match_obj:
                    obj_head = match_obj.group(1)
                    desc_text = match_obj.group(2)
                    amount_str = match_obj.group(3).replace(',', '')
                    
                    try:
                        amount = float(amount_str)
                    except:
                        continue 

                    row = {
                        "Dist": "01", 
                        "Dist_Name": dist,
                        "Block_ID": "09", 
                        "Block_Name": block,
                        "GP": gp_name,
                        "MAJOR HEAD": major_head,
                        "Major Desc": get_desc(major_head),
                        "MINOR HEAD": minor_head,
                        "Minor Desc": get_desc(minor_head),
                        "Detail Head": detail_head,
                        "Detail Desc": get_desc(detail_head),
                        "OBJECT HEAD": obj_head,
                        "Object Desc": desc_text if len(desc_text) > 2 else get_desc(obj_head),
                        "Amount": amount
                    }

                    if current_section == "RECEIPTS":
                        receipts_data.append(row)
                    elif current_section == "PAYMENTS":
                        payments_data.append(row)

    return receipts_data, payments_data

# --- STREAMLIT UI ---
st.set_page_config(page_title="GP Finance Processor", page_icon="📂")

st.title("📂 Gram Panchayat Data Processor")
st.write("Upload your PDF files below. The system will extract Receipts and Payments automatically.")

uploaded_files = st.file_uploader("Upload PDF Files", type="pdf", accept_multiple_files=True)

if uploaded_files:
    if st.button(f"Process {len(uploaded_files)} Files"):
        all_receipts = []
        all_payments = []
        
        progress_bar = st.progress(0)
        
        for i, file in enumerate(uploaded_files):
            r_data, p_data = extract_data_from_pdf(file, file.name)
            all_receipts.extend(r_data)
            all_payments.extend(p_data)
            progress_bar.progress((i + 1) / len(uploaded_files))
            
        st.success("Processing Complete!")

        # --- TABS FOR VIEWING DATA ---
        tab1, tab2 = st.tabs(["Receipts", "Payments"])

        with tab1:
            if all_receipts:
                df_r = pd.DataFrame(all_receipts)
                st.dataframe(df_r)
                
                # Convert to CSV
                csv_r = df_r.to_csv(index=False).encode('utf-8')
                st.download_button(
                    "Download Receipts CSV",
                    csv_r,
                    "Consolidated_Receipts.csv",
                    "text/csv",
                    key='download-r'
                )
            else:
                st.warning("No Receipts found.")

        with tab2:
            if all_payments:
                df_p = pd.DataFrame(all_payments)
                st.dataframe(df_p)
                
                # Convert to CSV
                csv_p = df_p.to_csv(index=False).encode('utf-8')
                st.download_button(
                    "Download Payments CSV",
                    csv_p,
                    "Consolidated_Payments.csv",
                    "text/csv",
                    key='download-p'
                )
            else:
                st.warning("No Payments found.")