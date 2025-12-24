import streamlit as st
import os
from pathlib import Path
import base64
from extraction_algorithm import extract_table_with_column_detection, extract_table_spatial

st.set_page_config(page_title="PDF Table Extractor", layout="wide", page_icon="📊")

def display_pdf(file_path):
    """Display PDF in an iframe"""
    with open(file_path, "rb") as f:
        base64_pdf = base64.b64encode(f.read()).decode('utf-8')
    pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600" type="application/pdf"></iframe>'
    return pdf_display

def get_pdf_files_from_folder(folder_path):
    """Recursively get all PDF files from a folder"""
    pdf_files = []
    folder = Path(folder_path)
    
    for file in folder.rglob('*.pdf'):
        pdf_files.append(str(file))
    
    return pdf_files

def main():
    st.title("📊 PDF Table Extractor")
    st.write("Upload PDF files or select a folder to extract tables from PDF documents")
    
    # Sidebar for options
    st.sidebar.header("Options")
    
    # Algorithm selection
    algorithm = st.sidebar.selectbox(
        "Extraction Algorithm:",
        ["Enhanced (Column Detection)", "Legacy (Spatial)"],
        help="Enhanced: Detects column separators based on vertical spacing patterns. Legacy: Simple spatial positioning."
    )
    
    input_method = st.sidebar.radio(
        "Select Input Method:",
        ["Upload Files", "Select Folder"]
    )
    
    pdf_files = []
    
    if input_method == "Upload Files":
        uploaded_files = st.file_uploader(
            "Choose PDF files", 
            type=['pdf'], 
            accept_multiple_files=True
        )
        
        if uploaded_files:
            # Save uploaded files temporarily
            temp_dir = Path("temp_pdfs")
            temp_dir.mkdir(exist_ok=True)
            
            pdf_files = []
            for uploaded_file in uploaded_files:
                temp_path = temp_dir / uploaded_file.name
                with open(temp_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                pdf_files.append(str(temp_path))
    
    else:  # Select Folder
        folder_path = st.text_input(
            "Enter folder path:",
            help="Enter the full path to the folder containing PDF files",
            key="folder_path_input"
        )
        
        if folder_path:
            # Clean and normalize the path
            folder_path_original = folder_path
            folder_path = folder_path.strip().strip('"').strip("'")
            folder_path = os.path.normpath(folder_path)
            
            # Convert to Path object for better cross-platform compatibility
            folder_path_obj = Path(folder_path)
            
            # Debug info in expander
            with st.expander("🔍 Path Debug Info (click to expand)", expanded=False):
                st.code(f"Original input: {repr(folder_path_original)}")
                st.code(f"Cleaned path: {repr(folder_path)}")
                st.code(f"Exists: {folder_path_obj.exists()}")
                st.code(f"Is directory: {folder_path_obj.is_dir()}")
                if folder_path_obj.exists():
                    st.code(f"Absolute path: {folder_path_obj.resolve()}")
            
            if folder_path_obj.exists() and folder_path_obj.is_dir():
                pdf_files = get_pdf_files_from_folder(folder_path)
                if pdf_files:
                    st.success(f"Found {len(pdf_files)} PDF file(s) in the folder")
                else:
                    st.warning("No PDF files found in the specified folder")
            else:
                st.error(f"❌ Folder path does not exist or is not a directory")
                st.code(folder_path)
                if not folder_path_obj.exists():
                    st.info("💡 The path does not exist. Please check for typos or verify the folder exists.")
                elif not folder_path_obj.is_dir():
                    st.info("💡 This path exists but is a file, not a folder. Please provide a folder path.")
                st.info("💡 Tip: Copy the full path from File Explorer. Right-click the folder → 'Copy as path'")
    
    # Process PDF files
    if pdf_files:
        st.write(f"### Processing {len(pdf_files)} PDF file(s)")
        
        for pdf_idx, pdf_file in enumerate(pdf_files):
            file_name = os.path.basename(pdf_file)
            # Create unique key using index to avoid duplicates
            unique_key = f"pdf_{pdf_idx}_{file_name}"
            
            with st.expander(f"📄 {file_name}", expanded=True):
                # Display file path
                st.markdown(f"**File Path:** `{pdf_file}`")
                
                # Download button for PDF
                with open(pdf_file, "rb") as pdf_download:
                    st.download_button(
                        label="📥 Download PDF",
                        data=pdf_download,
                        file_name=file_name,
                        mime="application/pdf",
                        key=f"download_{unique_key}"
                    )
                
                # Extract tables
                with st.spinner(f"Extracting tables from {file_name}..."):
                    if algorithm == "Enhanced (Column Detection)":
                        tables = extract_table_with_column_detection(pdf_file)
                    else:
                        tables = extract_table_spatial(pdf_file)
                
                if tables:
                    st.success(f"Found {len(tables)} table(s)")
                    
                    # Initialize session state for table navigation
                    if f"table_idx_{unique_key}" not in st.session_state:
                        st.session_state[f"table_idx_{unique_key}"] = 0
                    
                    current_idx = st.session_state[f"table_idx_{unique_key}"]
                    
                    # Navigation buttons
                    if len(tables) > 1:
                        nav_col1, nav_col2, nav_col3 = st.columns([1, 2, 1])
                        with nav_col1:
                            if st.button("⬅️ Previous", key=f"prev_{unique_key}", disabled=(current_idx == 0)):
                                st.session_state[f"table_idx_{unique_key}"] = max(0, current_idx - 1)
                                st.rerun()
                        with nav_col2:
                            st.markdown(f"<h4 style='text-align: center;'>Table {current_idx + 1} of {len(tables)}</h4>", unsafe_allow_html=True)
                        with nav_col3:
                            if st.button("Next ➡️", key=f"next_{unique_key}", disabled=(current_idx >= len(tables) - 1)):
                                st.session_state[f"table_idx_{unique_key}"] = min(len(tables) - 1, current_idx + 1)
                                st.rerun()
                    
                    # Create side-by-side layout
                    col1, col2 = st.columns([1, 1])
                    
                    # Left column: PDF Viewer
                    with col1:
                        st.markdown("### 📄 PDF Preview")
                        pdf_iframe = display_pdf(pdf_file)
                        st.markdown(pdf_iframe, unsafe_allow_html=True)
                    
                    # Right column: Current Table
                    with col2:
                        table_info = tables[current_idx]
                        st.markdown(f"### 📊 Table {current_idx + 1} (Page {table_info['page']})")
                        df = table_info['dataframe']
                        
                        # Display dataframe
                        st.dataframe(df, use_container_width=True, height=500)
                        
                        # Download button for CSV
                        csv = df.to_csv(index=False)
                        st.download_button(
                            label=f"📥 Download Table {current_idx + 1} as CSV",
                            data=csv,
                            file_name=f"{Path(file_name).stem}_table_{current_idx + 1}_page_{table_info['page']}.csv",
                            mime="text/csv",
                            key=f"csv_{unique_key}_table_{current_idx}"
                        )
                else:
                    st.warning("No tables found in this PDF")
    
    else:
        st.info("👆 Please upload PDF files or select a folder to begin")

if __name__ == "__main__":
    main()
