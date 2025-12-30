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

# --- TEXT PARSING LOGIC ---
def parse_text_block(text_lines, dist, block, gp, section_type):
    data_rows = []
    
    # Context holders
    major_head = ""
    minor_head = ""
    detail_head = ""
    
    for line in text_lines:
        line = line.strip()
        if not line: continue
        
        # Skip headers / junk lines
        if any(x in line.upper() for x in ["RECEIPTS", "PAYMENTS", "HEADS OF", "BUDGET", "AMOUNT", "TOTAL", "OPENING BALANCE", "CLOSING BALANCE"]):
            continue

        # Regex 1: Major Head (4 digits at start)
        match_major = re.match(r'^(\d{4})\s+(.*)', line)
        if match_major:
            major_head = match_major.group(1)
            minor_head, detail_head = "", "" # Reset children
            continue

        # Regex 2: Minor Head (3 digits at start)
        match_minor = re.match(r'^(\d{3})\s+(.*)', line)
        if match_minor:
            minor_head = match_minor.group(1)
            detail_head = ""
            continue

        # Regex 3: Detail Head (4 digits starting with 00)
        match_detail = re.match(r'^(00\d{2})\s+(.*)', line)
        if match_detail:
            detail_head = match_detail.group(1)
            continue

        # Regex 4: Object Head / Transaction Row
        # Looks for: CODE (2-3 chars) + DESC + AMOUNT (Numeric at end)
        match_obj = re.search(r'^([A-Z0-9]{2,3})\s+(.*?)\s+([\d,]+\.?\d*)$', line)
        
        if match_obj:
            obj_head = match_obj.group(1)
            desc_text = match_obj.group(2).strip()
            amount_str = match_obj.group(3).replace(',', '')
            
            try:
                amount = float(amount_str)
            except:
                continue

            # Add row if amount matches logic (sometimes 0 amounts are valid headers, but usually we want data)
            if amount >= 0:
                data_rows.append({
                    "Dist": "01", # Placeholder
                    "Dist_Name": dist,
                    "Block_ID": "09", # Placeholder
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

# --- PDF PROCESSING (SPLIT PAGE STRATEGY) ---
def process_pdf(file_obj, filename):
    # 1. Parse Filename for Metadata
    try:
        # Example: "anugul talacher badajorda.pdf"
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
            
            # 2. Split Strategy: Cut page in half vertically
            # Left Half = Receipts
            # Right Half = Payments
            # We use a slight offset from center to ensure we don't cut text in half
            split_x = width / 2
            
            left_bbox = (0, 0, split_x, height)
            right_bbox = (split_x, 0, width, height)
            
            # 3. Extract & Parse Left Side (Receipts)
            left_crop = page.crop(bbox=left_bbox)
            left_text = left_crop.extract_text()
            if left_text:
                rows = parse_text_block(left_text.split('\n'), dist, block, gp_name, "Receipt")
                file_receipts.extend(rows)
            
            # 4. Extract & Parse Right Side (Payments)
            right_crop = page.crop(bbox=right_bbox)
            right_text = right_crop.extract_text()
            if right_text:
                rows = parse_text_block(right_text.split('\n'), dist, block, gp_name, "Payment")
                file_payments.extend(rows)

    return file_receipts, file_payments

# --- STREAMLIT APP LAYOUT ---
st.set_page_config(page_title="GP Finance Processor", layout="wide")

st.title("📂 Gram Panchayat Finance Processor")
st.markdown("""
**Instructions:**
1. Upload your GP Financial PDFs (Receipts Left / Payments Right format).
2. The system will automatically split the pages and extract the data.
3. Download the consolidated CSV files.
""")

uploaded_files = st.file_uploader("Upload PDF Files", type="pdf", accept_multiple_files=True)

if uploaded_files:
    if st.button(f"Process {len(uploaded_files)} Files"):
        all_receipts = []
        all_payments = []
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for i, file in enumerate(uploaded_files):
            status_text.text(f"Processing {file.name}...")
            # Streamlit file objects can be passed directly to pdfplumber
            r_data, p_data = process_pdf(file, file.name)
            all_receipts.extend(r_data)
            all_payments.extend(p_data)
            progress_bar.progress((i + 1) / len(uploaded_files))
            
        status_text.text("Processing Complete!")
        st.success(f"Done! Processed {len(uploaded_files)} files.")

        # --- DISPLAY RESULTS ---
        tab1, tab2 = st.tabs(["Receipts Data", "Payments Data"])

        with tab1:
            if all_receipts:
                df_r = pd.DataFrame(all_receipts)
                st.write(f"Total Receipts Rows: {len(df_r)}")
                st.dataframe(df_r)
                st.download_button(
                    "📥 Download Receipts CSV",
                    df_r.to_csv(index=False).encode('utf-8'),
                    "Consolidated_Receipts.csv",
                    "text/csv"
                )
            else:
                st.warning("No Receipts found.")

        with tab2:
            if all_payments:
                df_p = pd.DataFrame(all_payments)
                st.write(f"Total Payments Rows: {len(df_p)}")
                st.dataframe(df_p)
                st.download_button(
                    "📥 Download Payments CSV",
                    df_p.to_csv(index=False).encode('utf-8'),
                    "Consolidated_Payments.csv",
                    "text/csv"
                )
            else:
                st.warning("No Payments found.")
