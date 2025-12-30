import streamlit as st
import pandas as pd
import pdfplumber
import re
import io

# --- APP CONFIGURATION ---
st.set_page_config(
    page_title="GP Finance Pro",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CUSTOM CSS FOR UI IMPROVEMENTS ---
st.markdown("""
    <style>
    /* 1. MAIN BACKGROUND GRADIENT */
    .stApp {
        background: #ECE9E6;  /* fallback for old browsers */
        background: -webkit-linear-gradient(to right, #FFFFFF, #ECE9E6);  /* Chrome 10-25, Safari 5.1-6 */
        background: linear-gradient(to right, #F4F7F6, #E2E9F0); /* W3C, IE 10+/ Edge, Firefox 16+, Chrome 26+, Opera 12+, Safari 7+ */
    }

    /* 2. CARD STYLE CONTAINERS */
    div.css-1r6slb0.e1tzin5v2 {
        background-color: #FFFFFF;
        padding: 2rem;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
        border: 1px solid #E0E0E0;
    }

    /* 3. HEADER STYLING */
    h1 {
        color: #2C3E50;
        font-family: 'Helvetica Neue', sans-serif;
        font-weight: 700;
    }
    h3 {
        color: #34495E;
    }

    /* 4. CUSTOM BUTTON STYLE */
    div.stButton > button:first-child {
        background: linear-gradient(90deg, #4b6cb7 0%, #182848 100%);
        color: white;
        border: none;
        padding: 0.5rem 2rem;
        border-radius: 8px;
        font-weight: bold;
        transition: all 0.3s ease;
    }
    div.stButton > button:first-child:hover {
        transform: scale(1.02);
        box-shadow: 0 4px 10px rgba(0,0,0,0.2);
    }

    /* 5. DATAFRAME BORDER */
    .stDataFrame {
        border: 1px solid #E0E0E0;
        border-radius: 5px;
    }
    
    /* 6. UPLOAD BOX STYLING */
    [data-testid='stFileUploader'] {
        background-color: #ffffff;
        border-radius: 10px;
        padding: 15px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    </style>
""", unsafe_allow_html=True)

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
    major_head = ""
    minor_head = ""
    detail_head = ""
    
    for line in lines:
        line = line.strip()
        if not line: continue
        
        if any(x in line.upper() for x in ["RECEIPTS", "PAYMENTS", "HEADS OF", "BUDGET", "AMOUNT", "TOTAL", "OPENING BALANCE"]):
            continue

        match_major = re.search(r'(^|\s)(\d{4})\s', line)
        if match_major:
            major_head = match_major.group(2)
            minor_head, detail_head = "", "" 
            continue

        match_minor = re.search(r'(^|\s)(\d{3})\s', line)
        if match_minor:
            minor_head = match_minor.group(2)
            detail_head = ""
            continue

        match_detail = re.search(r'(^|\s)(00\d{2})\s', line)
        if match_detail:
            detail_head = match_detail.group(2)
            continue

        match_obj = re.search(r'(^|\s)([A-Z0-9]{2,3})\s+(.*)', line)
        if match_obj:
            obj_head = match_obj.group(2)
            remainder = match_obj.group(3)
            amounts = re.findall(r'([\d,]+\.?\d*)', remainder)
            
            if amounts:
                try:
                    amount_str = amounts[-1].replace(',', '')
                    amount = float(amount_str)
                    desc_text = remainder.replace(amounts[-1], "").strip()
                    desc_text = re.sub(r'[\d,]+\.?\d*$', '', desc_text).strip()
                    
                    if len(desc_text) < 2: 
                        desc_text = get_desc(obj_head)

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

# --- 3. PDF PROCESSING ENGINE ---
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
            split_x = width / 2
            
            words = page.extract_words()
            r_x1 = 0
            p_x0 = width
            
            for word in words:
                if "RECEIPTS" in word['text'].upper():
                    r_x1 = word['x1']
                if "PAYMENTS" in word['text'].upper():
                    p_x0 = word['x0']
            
            if r_x1 > 0 and p_x0 < width:
                split_x = (r_x1 + p_x0) / 2
            
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
                
                left_words = [w['text'] for w in line_words if w['x0'] < split_x]
                right_words = [w['text'] for w in line_words if w['x0'] >= split_x]
                
                if left_words:
                    left_lines_text.append(" ".join(left_words))
                if right_words:
                    right_lines_text.append(" ".join(right_words))
            
            file_receipts.extend(parse_lines_deep(left_lines_text, dist, block, gp_name, "Receipt"))
            file_payments.extend(parse_lines_deep(right_lines_text, dist, block, gp_name, "Payment"))

    return file_receipts, file_payments

# --- 4. MAIN UI LAYOUT ---

# Sidebar
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2910/2910768.png", width=80)
    st.title("Settings")
    st.info("💡 **Tips:**\n\nEnsure your PDFs are text-based (not scanned images).\n\nThe system automatically splits pages into Left (Receipts) and Right (Payments).")
    st.divider()
    st.write("Current Version: **2.0 (UI Update)**")

# Main Content
col_header_1, col_header_2 = st.columns([3, 1])
with col_header_1:
    st.title("📊 Gram Panchayat Finance Processor")
    st.markdown("##### Transform complex PDF Financial Statements into clean Excel/CSV data instantly.")

st.divider()

# File Uploader Section
st.subheader("1. Upload Documents")
uploaded_files = st.file_uploader("", type="pdf", accept_multiple_files=True, help="Select multiple PDF files at once")

if uploaded_files:
    st.write(f"📂 **{len(uploaded_files)}** files selected.")
    
    # Process Button
    if st.button("🚀 Process Files Now"):
        all_receipts = []
        all_payments = []
        
        progress_text = "Operation in progress. Please wait..."
        my_bar = st.progress(0, text=progress_text)
        
        for i, file in enumerate(uploaded_files):
            r_data, p_data = process_pdf(file, file.name)
            all_receipts.extend(r_data)
            all_payments.extend(p_data)
            # Update progress
            my_bar.progress((i + 1) / len(uploaded_files), text=f"Processing {file.name}...")
            
        my_bar.empty()
        st.balloons()
        st.success("Processing Complete!")

        # --- RESULTS SECTION ---
        st.divider()
        st.subheader("2. Results Dashboard")

        # Metric Cards
        m1, m2, m3 = st.columns(3)
        m1.metric("Files Processed", len(uploaded_files))
        m2.metric("Receipt Rows", len(all_receipts))
        m3.metric("Payment Rows", len(all_payments))

        # Tabs for Data
        tab1, tab2 = st.tabs(["📥 Receipts Data", "📤 Payments Data"])

        with tab1:
            if all_receipts:
                df_r = pd.DataFrame(all_receipts)
                st.dataframe(df_r, use_container_width=True)
                
                csv_r = df_r.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="⬇️ Download Receipts CSV",
                    data=csv_r,
                    file_name="Consolidated_Receipts.csv",
                    mime="text/csv",
                    key='dl-r'
                )
            else:
                st.warning("No Receipt data found in the uploaded files.")

        with tab2:
            if all_payments:
                df_p = pd.DataFrame(all_payments)
                st.dataframe(df_p, use_container_width=True)
                
                csv_p = df_p.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="⬇️ Download Payments CSV",
                    data=csv_p,
                    file_name="Consolidated_Payments.csv",
                    mime="text/csv",
                    key='dl-p'
                )
            else:
                st.warning("No Payment data found. Please check PDF layout.")

else:
    st.info("👆 Please upload PDF files to begin.")
