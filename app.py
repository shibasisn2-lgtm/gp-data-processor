import streamlit as st
import pandas as pd
import pdfplumber
import re
import io

# --- APP VERSION ---
SCRIPT_VERSION = "1.5 (Dynamic Center Split)"

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

# --- 2. DEEP PARSING LOGIC ---
def parse_lines_deep(lines, dist, block, gp, section_type):
    data_rows = []
    
    # Context holders
    major_head = ""
    minor_head = ""
    detail_head = ""
    
    for line in lines:
        line = line.strip()
        if not line: continue
        
        # Skip headers / junk lines
        if any(x in line.upper() for x in ["RECEIPTS", "PAYMENTS", "HEADS OF", "BUDGET", "AMOUNT", "TOTAL", "OPENING BALANCE"]):
            continue

        # Regex 1: Major Head (4 digits)
        match_major = re.search(r'(^|\s)(\d{4})\s', line)
        if match_major:
            major_head = match_major.group(2)
            minor_head, detail_head = "", "" # Reset children
            continue

        # Regex 2: Minor Head (3 digits)
        match_minor = re.search(r'(^|\s)(\d{3})\s', line)
        if match_minor:
            minor_head = match_minor.group(2)
            detail_head = ""
            continue

        # Regex 3: Detail Head (4 digits starting with 00)
        match_detail = re.search(r'(^|\s)(00\d{2})\s', line)
        if match_detail:
            detail_head = match_detail.group(2)
            continue

        # Regex 4: Object Head / Transaction Row
        # Looks for 2-3 alphanumeric chars (like "80", "5S", "L2") at start or after space
        match_obj = re.search(r'(^|\s)([A-Z0-9]{2,3})\s+(.*)', line)
        
        if match_obj:
            obj_head = match_obj.group(2)
            remainder = match_obj.group(3)
            
            # EXTRACT AMOUNT: Find the last valid number in the line
            amounts = re.findall(r'([\d,]+\.?\d*)', remainder)
            
            if amounts:
                try:
                    # We take the last number that isn't "0" or "0.00" if possible, 
                    # but usually the actual amount is the very last number in the row.
                    amount_str = amounts[-1].replace(',', '')
                    amount = float(amount_str)
                    
                    # Logic to clean description (remove the amount from the text)
                    desc_text = remainder.replace(amounts[-1], "").strip()
                    # Clean up trailing/leading junk
                    desc_text = re.sub(r'[\d,]+\.?\d*$', '', desc_text).strip()
                    
                    if len(desc_text) < 2: 
                        desc_text = get_desc(obj_head)

                    # Only add if we have some context (Major Head) or it looks valid
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
                            "Object Desc": desc_text,
                            "Amount": amount
                        })
                except:
                    pass 

    return data_rows

# --- 3. PDF PROCESSING ENGINE (Spatial Clustering) ---
def process_pdf(file_obj, filename):
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
            
            # --- DYNAMIC SPLIT LOGIC ---
            # Default split is middle
            split_x = width / 2
            
            # Try to find "RECEIPTS" and "PAYMENTS" to calculate exact midpoint
            words = page.extract_words()
            r_x1 = 0
            p_x0 = width
            
            for word in words:
                if "RECEIPTS" in word['text'].upper():
                    r_x1 = word['x1']
                if "PAYMENTS" in word['text'].upper():
                    p_x0 = word['x0']
            
            # If both found, split exactly between them
            if r_x1 > 0 and p_x0 < width:
                split_x = (r_x1 + p_x0) / 2
            
            # CLUSTER LINES
            lines_dict = {}
            for word in words:
                line_key = round(word['top'] / 3) * 3
                if line_key not in lines_dict:
                    lines_dict[line_key] = []
                lines_dict[line_key].append(word)
            
            sorted_line_keys = sorted(lines_dict.keys())
            
            left_lines_text = []
            right_lines_text = []
            
            for key in sorted_line_keys:
                line_words = lines_dict[key]
                line_words.sort(key=lambda w: w['x0'])
                
                # Split based on calculated split_x
                left_words = [w['text'] for w in line_words if w['x0'] < split_x]
                right_words = [w['text'] for w in line_words if w['x0'] >= split_x]
                
                if left_words:
                    left_lines_text.append(" ".join(left_words))
                if right_words:
                    right_lines_text.append(" ".join(right_words))
            
            file_receipts.extend(parse_lines_deep(left_lines_text, dist, block, gp_name, "Receipt"))
            file_payments.extend(parse_lines_deep(right_lines_text, dist, block, gp_name, "Payment"))

    return file_receipts, file_payments

# --- 4. STREAMLIT APP UI ---
st.set_page_config(page_title="GP Finance Processor", layout="wide")

st.title("📂 Gram Panchayat Finance Processor")
st.caption(f"Engine Version: {SCRIPT_VERSION}")

st.markdown("""
**System Status:** Dynamic Split Enabled.
This version calculates the center point between 'RECEIPTS' and 'PAYMENTS' headers for maximum accuracy.
""")

uploaded_files = st.file_uploader("Upload PDF Files", type="pdf", accept_multiple_files=True)

if uploaded_files:
    if st.button(f"Process {len(uploaded_files)} Files"):
        all_receipts = []
        all_payments = []
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for i, file in enumerate(uploaded_files):
            status_text.text(f"Scanning {file.name}...")
            r_data, p_data = process_pdf(file, file.name)
            all_receipts.extend(r_data)
            all_payments.extend(p_data)
            progress_bar.progress((i + 1) / len(uploaded_files))
            
        status_text.text("Processing Complete!")
        
        if len(all_receipts) == 0 and len(all_payments) == 0:
            st.error("No data found! Please check if the PDFs are scanned images (requires OCR) or text-based.")
        else:
            st.success(f"Success! Processed {len(uploaded_files)} files.")

        # --- DISPLAY RESULTS ---
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Receipts")
            if all_receipts:
                df_r = pd.DataFrame(all_receipts)
                st.write(f"Rows: {len(df_r)}")
                st.dataframe(df_r, height=300)
                st.download_button("📥 Download Receipts CSV", df_r.to_csv(index=False).encode('utf-8'), "Consolidated_Receipts.csv", "text/csv")
            else:
                st.info("No Receipts found.")

        with col2:
            st.subheader("Payments")
            if all_payments:
                df_p = pd.DataFrame(all_payments)
                st.write(f"Rows: {len(df_p)}")
                st.dataframe(df_p, height=300)
                st.download_button("📥 Download Payments CSV", df_p.to_csv(index=False).encode('utf-8'), "Consolidated_Payments.csv", "text/csv")
            else:
                st.info("No Payments found.")
