import pdfplumber
import pandas as pd
import re
from collections import defaultdict

def find_column_separators(page):
    """
    Find column separators by detecting vertical whitespace (constant spacing along y-axis).
    Returns x-coordinates where there are vertical gaps (no text obstacles).
    """
    words = page.extract_words(x_tolerance=2, y_tolerance=2)
    
    if not words:
        return []
    
    # Get page dimensions
    page_width = page.width
    page_height = page.height
    
    # Create a grid to track occupied x-positions at different y-levels
    # Sample y-positions across the page
    y_samples = 50  # Number of vertical samples
    x_resolution = 5  # Check every 5 pixels horizontally
    
    # For each x-position, count how many y-levels have text
    x_occupation = defaultdict(int)
    
    for word in words:
        x_start = int(word['x0'] / x_resolution) * x_resolution
        x_end = int(word['x1'] / x_resolution) * x_resolution
        
        # Mark all x-positions this word occupies
        for x in range(int(x_start), int(x_end) + x_resolution, x_resolution):
            x_occupation[x] += 1
    
    # Find x-positions with minimal text (potential column separators)
    if not x_occupation:
        return []
    
    max_occupation = max(x_occupation.values())
    threshold = max_occupation * 0.1  # Column separators have < 10% occupation
    
    separators = []
    in_gap = False
    gap_start = None
    
    for x in sorted(set(range(0, int(page_width), x_resolution))):
        occupation = x_occupation.get(x, 0)
        
        if occupation < threshold:
            if not in_gap:
                gap_start = x
                in_gap = True
        else:
            if in_gap and gap_start is not None:
                # Found end of gap, record the middle
                gap_middle = (gap_start + x) / 2
                if gap_middle > 50 and gap_middle < page_width - 50:  # Ignore edges
                    separators.append(gap_middle)
                in_gap = False
                gap_start = None
    
    return separators


def extract_table_with_column_detection(pdf_path):
    """
    Extract tables using enhanced algorithm that detects column separators
    based on vertical spacing patterns.
    """
    all_tables = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                # Extract words with positions
                words = page.extract_words(x_tolerance=2, y_tolerance=2)
                
                if not words:
                    continue
                
                # Find column separators
                separators = find_column_separators(page)
                
                # If no separators found, use simple two-column split
                if not separators:
                    # Fallback to spatial analysis
                    all_text_x = []
                    all_num_x = []
                    
                    for word in words:
                        if re.match(r'^[\$\-\d,\.]+$', word['text']):
                            all_num_x.append(word['x0'])
                        else:
                            all_text_x.append(word['x1'])
                    
                    if all_text_x and all_num_x:
                        max_text_x = max(all_text_x)
                        min_num_x = min(all_num_x)
                        separators = [(max_text_x + min_num_x) / 2]
                    else:
                        separators = [page.width / 2]
                
                # Group words by row (y-coordinate)
                rows_dict = defaultdict(list)
                for word in words:
                    y = round(word['top'])
                    rows_dict[y].append(word)
                
                # Sort rows by y position
                sorted_y = sorted(rows_dict.keys())
                
                # Build table with columns based on separators
                table_data = []
                num_cols = len(separators) + 1
                
                for y in sorted_y:
                    row_words = sorted(rows_dict[y], key=lambda w: w['x0'])
                    
                    # Distribute words into columns based on separators
                    row = [''] * num_cols
                    
                    for word in row_words:
                        word_x = (word['x0'] + word['x1']) / 2  # Use center of word
                        
                        # Determine which column this word belongs to
                        col_idx = 0
                        for sep in separators:
                            if word_x > sep:
                                col_idx += 1
                            else:
                                break
                        
                        if col_idx < num_cols:
                            if row[col_idx]:
                                row[col_idx] += ' ' + word['text']
                            else:
                                row[col_idx] = word['text']
                    
                    # Clean up and add row if not empty
                    row = [cell.strip() for cell in row]
                    if any(cell for cell in row):
                        table_data.append(row)
                
                # Create DataFrame with numeric headers
                if table_data:
                    headers = list(range(num_cols))
                    df = pd.DataFrame(table_data, columns=headers)
                    
                    # Clean up: remove completely empty rows
                    df = df[df.apply(lambda row: any(row.astype(bool)), axis=1)]
                    
                    if not df.empty:
                        all_tables.append({
                            'page': page_num,
                            'dataframe': df,
                            'num_columns': num_cols
                        })
    
    except Exception as e:
        print(f"Error extracting from {pdf_path}: {str(e)}")
    
    return all_tables


def extract_table_spatial(pdf_path):
    """
    Legacy extraction method using simple spatial positioning.
    Kept for backward compatibility.
    """
    all_tables = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                # Extract words with positions
                words = page.extract_words(x_tolerance=2, y_tolerance=2)
                
                if not words:
                    continue
                
                # Group words by row (y-coordinate)
                rows_dict = defaultdict(list)
                
                for word in words:
                    y = round(word['top'])
                    rows_dict[y].append(word)
                
                # Sort rows by y position
                sorted_y = sorted(rows_dict.keys())
                
                # Analyze x-positions to find column boundary
                all_text_x = []
                all_num_x = []
                
                for y in sorted_y:
                    row_words = sorted(rows_dict[y], key=lambda w: w['x0'])
                    for word in row_words:
                        # Check if word looks like a number/amount
                        if re.match(r'^[\$\-\d,\.]+$', word['text']):
                            all_num_x.append(word['x0'])
                        else:
                            all_text_x.append(word['x1'])  # right edge of text
                
                # Find the column split point
                if all_text_x and all_num_x:
                    max_text_x = max(all_text_x)
                    min_num_x = min(all_num_x)
                    col_split = (max_text_x + min_num_x) / 2
                else:
                    col_split = page.width / 2
                
                # Build table with proper columns
                table_data = []
                
                for y in sorted_y:
                    row_words = sorted(rows_dict[y], key=lambda w: w['x0'])
                    
                    # Split into two columns based on x position
                    col1_words = [w['text'] for w in row_words if w['x0'] < col_split]
                    col2_words = [w['text'] for w in row_words if w['x0'] >= col_split]
                    
                    col1_text = ' '.join(col1_words).strip()
                    col2_text = ' '.join(col2_words).strip()
                    
                    if col1_text or col2_text:  # Skip empty rows
                        table_data.append([col1_text, col2_text])
                
                # Create DataFrame with numeric headers
                if table_data:
                    # Use numeric headers: 0, 1, 2, etc.
                    num_cols = len(table_data[0]) if table_data else 2
                    headers = list(range(num_cols))
                    
                    df = pd.DataFrame(table_data, columns=headers)
                    
                    # Clean up: remove empty rows
                    df = df[(df.iloc[:, 0] != '') | (df.iloc[:, 1] != '')]
                    
                    if not df.empty:
                        all_tables.append({
                            'page': page_num,
                            'dataframe': df
                        })
    except Exception as e:
        print(f"Error extracting from {pdf_path}: {str(e)}")
    
    return all_tables
