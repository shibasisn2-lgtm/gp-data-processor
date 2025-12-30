import streamlit as st
import pandas as pd
import pdfplumber
import re
import io

# --- 1. CONFIGURATION & MAPPING ---
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
    '2049': 'Interest Payments',
    '8658': 'Suspense Account',
    '0071': 'State Govt Schemes (Harishchandra)',
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

# --- 2. PARSING LOGIC ---
def parse_text_block(text_lines, dist, block, gp, section_type):
    data_rows = []
    
    # Hierarchy Context
    major_head = ""
    minor_head = ""
    detail_head = ""
    
    for line in text_lines:
        line = line.strip()
        if not line: continue
        
        # Skip headers / junk
        if any(x in line.upper() for x in ["RECEIPTS", "PAYMENTS", "HEADS OF", "BUDGET", "AMOUNT", "TOTAL"]):
            continue

        # 1. Major Head (4 digits at start)
        match_major = re.match(r'^(\d{4})\s+(.*)', line)
        if match_major:
            major_head = match_major.group(1)
            minor_head, detail_head = "", "" # Reset children
            continue

        # 2. Minor Head (3 digits at start)
        match_minor = re.match(r'^(\d{3})\s+(.*)', line)
        if match_minor:
            minor_head = match_minor.group(1)
            detail_head = ""
            continue

        # 3. Detail Head (4 digits starting with 00)
        match_detail = re.match(r'^(00\d{2})\s+(.*)', line)
        if match_detail:
            detail_head = match_detail.group(1)
            continue

        # 4. Object Head / Transaction Row
        match_obj = re.search(r'^([A-Z0-9]{2,3})\s+(.*?)\s+([\d,]+\.?\d*)$', line)
        
        if match_obj:
            obj_head = match_obj.group(1)
            desc_text = match_obj.group(2).strip()
            amount_str = match_obj.group(3).replace(',', '')
            
            try:
                amount = float(amount_str)
            except:
                continue

            if amount >= 0:
                data_rows.append({
                    "Dist_Name": dist,
                    "Block_Name": block,
                    "GP": gp,
                    "Type": section_type,
                    "MAJOR HEAD": major_head,
                    "Major Desc": get_desc(major_head),
                    "MINOR HEAD": minor_head,
                    "Minor Desc": get_desc(minor_head),
                    "Detail Head": detail_head,
                    "Detail Desc": get_desc(detail_head),
                    "OBJECT HEAD": obj_head,
                    "Object Desc": desc_text if len(desc_text) > 2 else get_desc(obj_head),
                    "Amount": amount
                })
    return data_rows

# --- 3. PDF PROCESSING ENGINE (Smart Split) ---
def process_pdf(file_obj, filename):
    # Filename parsing
    try:
        parts = filename.replace('.pdf', '').split(' ')
        dist = parts[0].title() if len(parts) > 0 else "Unknown"
        block = parts[1].title() if len(parts) > 1 else "Unknown"
        gp_name = " ".join(parts[2:]).title() if len(parts) > 2 else "Unknown"
    except:
        dist, block, gp_name = "Angul", "Unknown", filename

    file_receipts = []
    file_payments = []

    with pdfplumber.open(file_obj) as pdf:
        for page in pdf.pages:
            width = page.width
            height = page.height
            
            # --- SMART SPLIT LOGIC ---
            # Default split is middle
            split_x = width / 2
            
            # Search for "PAYMENTS" text object to find exact X coordinate
            words = page.extract_words()
            for word in words:
                if "PAYMENTS" in word['text'].upper():
                    # Set split line slightly to the left of "PAYMENTS"
                    split_x = word['x0'] - 20 
                    break
            
            # Left Box (Receipts)
            left_bbox = (0, 0, split_x, height)
            # Right Box (Payments)
            right_bbox = (split_x, 0, width, height)
            
            # Extract
            left_crop = page.crop(bbox=left_bbox)
            left_text = left_crop.extract_text()
            
            right_crop = page.crop(bbox=right_bbox)
            right_text = right_crop.extract_text()
            
            if left_text:
                file_receipts.extend(parse_text_block(left_text.split('\n'), dist, block, gp_name, "Receipt"))
            if right_text:
                file_payments.extend(parse_text_block(right_text.split('\n'), dist, block, gp_name, "Payment"))

    return file_receipts, file_payments

# --- 4. STREAMLIT UI ---
st.set_page_config(page_title="GP Finance Processor", page_icon="📂")

st.title("📂 Gram Panchayat Data Processor")
st.write("Upload your PDF files below. The system uses 'Smart Split' to separate Receipts and Payments.")

uploaded_files = st.file_uploader("Upload PDF Files", type="pdf", accept_multiple_files=True)

if uploaded_files:
    if st.button(f"Process {len(uploaded_files)} Files"):
        all_receipts = []
        all_payments = []
        
        progress_bar = st.progress(0)
        
        for i, file in enumerate(uploaded_files):
            # Streamlit uploads are file-like objects, pdfplumber can read them directly
            r_data, p_data = process_pdf(file, file.name)
            all_receipts.extend(r_data)
            all_payments.extend(p_data)
            progress_bar.progress((i + 1) / len(uploaded_files))
            
        st.success("Processing Complete!")

        # --- TABS FOR VIEWING DATA ---
        tab1, tab2 = st.tabs(["Receipts", "Payments"])

        with tab1:
            if all_receipts:
                df_r = pd.DataFrame(all_receipts)
                st.write(f"Found {len(df_r)} Receipt records")
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
                st.write(f"Found {len(df_p)} Payment records")
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
                st.warning("No Payments found. (Check if the PDF layout matches the expected Receipts-Left / Payments-Right format)")
