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
    st.write("Upload PDF files to extract tables from PDF documents")
    
    # Sidebar for options
    st.sidebar.header("Options")
    
    # Algorithm selection
    algorithm = st.sidebar.selectbox(
        "Extraction Algorithm:",
        ["Enhanced (Column Detection)", "Legacy (Spatial)"],
        help="Enhanced: Detects column separators based on vertical spacing patterns. Legacy: Simple spatial positioning."
    )
    
    # Detect if running locally or in cloud
    is_cloud = os.getcwd().startswith('/mount/src/') or os.getcwd().startswith('/app/')
    
    st.sidebar.header("Upload PDFs")
    if is_cloud:
        st.sidebar.info("ℹ️ Running in cloud mode")
    
    st.sidebar.markdown("""
    **📁 How to upload folder contents:**
    1. Click 'Browse files' below
    2. In the file dialog, press `Ctrl+A` (or `Cmd+A` on Mac) to select all PDFs
    3. Or hold `Ctrl/Cmd` and click to select multiple files
    4. You can select files from different folders
    """)
    
    uploaded_files = st.sidebar.file_uploader(
        "Choose PDF files (multiple files allowed)", 
        type=['pdf'], 
        accept_multiple_files=True,
        help="Select all PDF files from your folder(s). You can select files from multiple folders."
    )
    
    pdf_files = []
    
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
        
        st.success(f"✅ Uploaded {len(pdf_files)} PDF file(s)")

    
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
                    
                    # Left column: PDF Download/Info
                    with col1:
                        st.markdown("### 📄 PDF Document")
                        
                        # Display PDF download button prominently
                        with open(pdf_file, "rb") as pdf_data:
                            st.download_button(
                                label="📥 Download Full PDF",
                                data=pdf_data,
                                file_name=file_name,
                                mime="application/pdf",
                                key=f"download_full_{unique_key}",
                                use_container_width=True
                            )
                        
                        # Try to display PDF preview (may not work in all browsers/deployments)
                        try:
                            pdf_iframe = display_pdf(pdf_file)
                            st.markdown(pdf_iframe, unsafe_allow_html=True)
                        except Exception as e:
                            st.info("📄 PDF preview not available in this environment. Use the download button above to view the PDF.")
                    
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
        st.info("👆 Please upload PDF files using the sidebar to begin")
        st.markdown("""
        ### 💡 Tips for uploading multiple files:
        - Click **'Browse files'** in the sidebar
        - Use **Ctrl+A** (Windows/Linux) or **Cmd+A** (Mac) to select all PDFs in a folder
        - Hold **Ctrl/Cmd** and click to select specific files
        - You can navigate to different folders and select files from multiple locations
        - All selected files will be processed together
        """)

if __name__ == "__main__":
    main()
