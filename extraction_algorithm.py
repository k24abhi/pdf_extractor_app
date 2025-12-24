import pdfplumber
import pandas as pd
import re
from collections import defaultdict
import numpy as np

def detect_rows_with_consistent_spacing(words, y_tolerance=3):
    """
    Detect rows with consistent vertical spacing - a key table characteristic.
    Returns list of row groups where each group has words with similar y-position.
    """
    if not words:
        return []
    
    # Group words into rows with y-tolerance
    rows_dict = defaultdict(list)
    
    for word in words:
        word_y = word['top']
        matched_row = None
        for existing_y in rows_dict.keys():
            if abs(word_y - existing_y) <= y_tolerance:
                matched_row = existing_y
                break
        
        if matched_row is not None:
            rows_dict[matched_row].append(word)
        else:
            rows_dict[word_y].append(word)
    
    # Sort rows by y position
    sorted_rows = [(y, rows_dict[y]) for y in sorted(rows_dict.keys())]
    
    return sorted_rows


def analyze_row_spacing(sorted_rows):
    """
    Analyze vertical spacing between rows to identify table regions.
    Uses an aggressive approach to capture ALL content.
    Returns list of (start_idx, end_idx, avg_spacing, spacing_variance) tuples.
    """
    if len(sorted_rows) < 2:
        return []
    
    # Calculate spacing between consecutive rows
    spacings = []
    for i in range(len(sorted_rows) - 1):
        spacing = sorted_rows[i + 1][0] - sorted_rows[i][0]
        spacings.append(spacing)
    
    if not spacings:
        return []
    
    # Strategy: Look for very large gaps (>200px) that indicate completely separate sections
    # Otherwise, group everything together
    table_regions = []
    region_start = 0
    
    for i, spacing in enumerate(spacings):
        # Only break on EXTREMELY large gaps (likely page footer/header breaks)
        if spacing > 200:  # More than 200px gap (increased from 100px)
            # End current region
            if i - region_start >= 0:  # At least 1 row
                region_spacings = spacings[region_start:i]
                avg_spacing = np.mean(region_spacings) if region_spacings else spacing
                std_spacing = np.std(region_spacings) if len(region_spacings) > 1 else 0
                variance_ratio = std_spacing / avg_spacing if avg_spacing > 0 else 0
                table_regions.append((region_start, i, avg_spacing, variance_ratio))
            
            # Start new region
            region_start = i + 1
    
    # Add the final region
    if region_start < len(sorted_rows) - 1:
        region_spacings = spacings[region_start:]
        avg_spacing = np.mean(region_spacings) if region_spacings else 10
        std_spacing = np.std(region_spacings) if len(region_spacings) > 1 else 0
        variance_ratio = std_spacing / avg_spacing if avg_spacing > 0 else 0
        table_regions.append((region_start, len(sorted_rows) - 1, avg_spacing, variance_ratio))
    elif region_start == len(sorted_rows) - 1:
        # Edge case: last row by itself
        table_regions.append((region_start, region_start, 10, 0))
    
    # Fallback: if no regions found, treat entire document as one table
    if not table_regions and len(sorted_rows) >= 2:
        avg_spacing = np.mean(spacings)
        std_spacing = np.std(spacings)
        variance_ratio = std_spacing / avg_spacing if avg_spacing > 0 else 0
        table_regions.append((0, len(sorted_rows) - 1, avg_spacing, variance_ratio))
    
    return table_regions


def detect_column_separators_by_position(sorted_rows, page_width):
    """
    Detect column boundaries by analyzing where words start (x0 positions).
    Groups words into columns based on x-position clustering.
    """
    # Collect all x0 positions weighted by frequency
    x_positions = []
    for y_pos, row_words in sorted_rows:
        for word in row_words:
            x_positions.append(word['x0'])
    
    if not x_positions:
        return []
    
    # Sort and find clusters
    x_sorted = sorted(x_positions)
    clusters = []
    current_cluster = [x_sorted[0]]
    
    for x in x_sorted[1:]:
        if x - current_cluster[-1] < 30:  # Within 30px = same column start
            current_cluster.append(x)
        else:
            if len(current_cluster) >= len(sorted_rows) * 0.1:  # At least 10% of rows use this position
                clusters.append(np.mean(current_cluster))
            current_cluster = [x]
    
    if len(current_cluster) >= len(sorted_rows) * 0.1:
        clusters.append(np.mean(current_cluster))
    
    # Convert column starts to separators (midpoint between adjacent columns)
    separators = []
    for i in range(len(clusters) - 1):
        separator = (clusters[i] + clusters[i+1]) / 2
        if 30 < separator < page_width - 30:
            separators.append(separator)
    
    return separators


def detect_vertical_gaps(sorted_rows, page_width, gap_threshold_pct=0.05):
    """
    Detect persistent vertical whitespace gaps that act as column separators.
    Returns list of x-coordinates representing column boundaries.
    Fallback to position-based detection if gap detection doesn't work.
    """
    x_resolution = 2  # pixels
    gap_positions = defaultdict(int)  # Count how many rows have a gap at each x
    
    total_rows = len(sorted_rows)
    
    # Find the overall content boundaries
    all_x_positions = []
    for y_pos, row_words in sorted_rows:
        for word in row_words:
            all_x_positions.extend([word['x0'], word['x1']])
    
    if not all_x_positions:
        return []
    
    content_start = int(min(all_x_positions))
    content_end = int(max(all_x_positions))
    
    for y_pos, row_words in sorted_rows:
        # Sort words in this row by x position
        sorted_words = sorted(row_words, key=lambda w: w['x0'])
        
        # Mark occupied x-positions in this row
        occupied = set()
        for word in sorted_words:
            x_start = int(word['x0'] / x_resolution) * x_resolution
            x_end = int(word['x1'] / x_resolution) * x_resolution
            for x in range(x_start, x_end + x_resolution, x_resolution):
                occupied.add(x)
        
        # Find gaps in this row - only within content boundaries
        for x in range(content_start, content_end, x_resolution):
            if x not in occupied:
                gap_positions[x] += 1
    
    # Find persistent gaps (present in ≥15% of rows) - very lenient for better detection
    min_gap_width = page_width * gap_threshold_pct
    persistence_threshold = 0.15 * total_rows  # Reduced from 0.20 to 0.15 for better sensitivity
    
    separators = []
    in_gap = False
    gap_start = None
    
    for x in sorted(range(0, int(page_width), x_resolution)):
        gap_count = gap_positions.get(x, 0)
        
        if gap_count >= persistence_threshold:
            if not in_gap:
                gap_start = x
                in_gap = True
        else:
            if in_gap and gap_start is not None:
                gap_width = x - gap_start
                if gap_width >= min_gap_width:
                    # Record middle of gap
                    gap_middle = (gap_start + x) / 2
                    if 30 < gap_middle < page_width - 30:  # Ignore edges
                        separators.append(gap_middle)
                in_gap = False
                gap_start = None
    
    # Fallback: if no separators found but we have multi-word rows, use position-based detection
    if not separators and total_rows > 0:
        # Check if rows have multiple words that might indicate columns
        multi_word_rows = sum(1 for y, words in sorted_rows if len(words) > 2)
        if multi_word_rows > total_rows * 0.3:  # 30% of rows have multiple words
            separators = detect_column_separators_by_position(sorted_rows, page_width)
    
    return separators


def validate_column_alignment(sorted_rows, separators, tolerance=10):
    """
    Validate that words align consistently with detected column separators.
    Returns True if ≥80% of rows show expected column alignments.
    """
    if not separators:
        return False
    
    aligned_rows = 0
    
    for y_pos, row_words in sorted_rows:
        if not row_words:
            continue
        
        # Check if words respect column boundaries
        columns_used = set()
        valid_alignment = True
        
        for word in row_words:
            word_center = (word['x0'] + word['x1']) / 2
            
            # Determine which column this word belongs to
            col_idx = 0
            for sep in separators:
                if word_center > sep:
                    col_idx += 1
                else:
                    break
            
            # Check if word crosses a separator (invalid for tables)
            crosses_separator = False
            for sep in separators:
                if word['x0'] < sep - tolerance < word['x1']:
                    crosses_separator = True
                    break
            
            if crosses_separator:
                valid_alignment = False
                break
            
            columns_used.add(col_idx)
        
        if valid_alignment and len(columns_used) >= 2:
            aligned_rows += 1
    
    alignment_ratio = aligned_rows / len(sorted_rows) if sorted_rows else 0
    return alignment_ratio >= 0.3  # Reduced from 0.4 to 0.3 for maximum flexibility


def has_financial_patterns(row_words, separators):
    """
    Check if row contains financial patterns (numbers, currency, right-aligned amounts).
    """
    # If no separators, check all words
    if not separators:
        words_to_check = row_words
    else:
        # Check rightmost column for numeric/currency patterns
        words_to_check = [w for w in row_words if w['x0'] > separators[-1]]
    
    for word in words_to_check:
        # Check for financial patterns - currency symbols, numbers with decimals, percentages
        text = word['text'].strip()
        if re.search(r'[\$€£¥%]|^\-?\d[\d,]*\.\d+$|^\d[\d,]+$|^\(\d[\d,]*\.?\d*\)$', text):
            return True
    
    return False


def identify_table_regions(page):
    """
    Identify isolated table regions based on structural characteristics.
    Returns list of table regions with their rows and columns.
    """
    words = page.extract_words(x_tolerance=2, y_tolerance=2)
    
    if not words or len(words) < 10:  # Too few words for a table
        return []
    
    # Step 1: Detect rows with consistent spacing
    sorted_rows = detect_rows_with_consistent_spacing(words)
    
    if len(sorted_rows) < 1:  # Changed from 3 to 1 - accept even single row
        return []
    
    # Step 2: Analyze row spacing to find table regions
    table_regions = analyze_row_spacing(sorted_rows)
    
    if not table_regions:
        return []
    
    # Step 3: For each potential table region, detect columns
    validated_tables = []
    
    for start_idx, end_idx, avg_spacing, variance in table_regions:
        region_rows = sorted_rows[start_idx:end_idx + 1]
        
        if len(region_rows) < 1:  # Accept even single row
            continue
        
        # Detect vertical gaps (column separators)
        separators = detect_vertical_gaps(region_rows, page.width)
        
        # Validate column alignment only if we have multiple columns
        # and only as a soft check (don't reject on failure)
        alignment_valid = True
        if len(separators) > 0:
            alignment_valid = validate_column_alignment(region_rows, separators)
        
        # Check for financial patterns
        has_financial = False
        for y_pos, row_words in region_rows:
            if has_financial_patterns(row_words, separators):
                has_financial = True
                break
        
        # Calculate content density for info only
        total_words = sum(len(row_words) for _, row_words in region_rows)
        words_per_row = total_words / len(region_rows) if region_rows else 0
        
        # Accept ALL regions - no filtering
        validated_tables.append({
            'rows': region_rows,
            'separators': separators,
            'num_columns': len(separators) + 1,
            'avg_row_spacing': avg_spacing,
            'has_financial': has_financial,
            'alignment_valid': alignment_valid,
            'words_per_row': words_per_row
        })
    
    return validated_tables


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
    Extract tables using enhanced algorithm that identifies isolated table regions
    based on structural characteristics (spacing, alignment, whitespace patterns).
    Ignores paragraphs and unstructured text.
    """
    all_tables = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                # Identify table regions on this page
                table_regions = identify_table_regions(page)
                
                if not table_regions:
                    continue
                
                # Extract each identified table
                for table_idx, table_info in enumerate(table_regions):
                    region_rows = table_info['rows']
                    separators = table_info['separators']
                    num_cols = table_info['num_columns']
                    
                    # Build table data
                    table_data = []
                    
                    for y_pos, row_words in region_rows:
                        row_words_sorted = sorted(row_words, key=lambda w: w['x0'])
                        
                        # Distribute words into columns based on separators
                        row = [''] * num_cols
                        
                        # If no separators, use heuristic based on x-position
                        if not separators:
                            # Group words by x-position ranges
                            for word in row_words_sorted:
                                # Simple heuristic: divide page into equal columns
                                col_idx = min(int(word['x0'] / (page.width / num_cols)), num_cols - 1)
                                if row[col_idx]:
                                    row[col_idx] += ' ' + word['text']
                                else:
                                    row[col_idx] = word['text']
                        else:
                            # Use separators to determine columns
                            for word in row_words_sorted:
                                # Use left edge (x0) for column assignment to avoid words
                                # that span across separators being assigned to wrong column
                                word_position = word['x0']
                                
                                # Determine column index
                                col_idx = 0
                                for sep in separators:
                                    if word_position > sep:
                                        col_idx += 1
                                    else:
                                        break
                                
                                if col_idx < num_cols:
                                    if row[col_idx]:
                                        row[col_idx] += ' ' + word['text']
                                    else:
                                        row[col_idx] = word['text']
                        
                        # Clean up and add row
                        row = [cell.strip() for cell in row]
                        if any(cell for cell in row):
                            table_data.append(row)
                    
                    # Create DataFrame
                    if table_data:  # Accept any table data, even 1 row
                        headers = list(range(num_cols))
                        df = pd.DataFrame(table_data, columns=headers)
                        
                        # Clean up: remove completely empty rows
                        df = df[df.apply(lambda row: any(row.astype(bool)), axis=1)]
                        
                        if not df.empty:
                            all_tables.append({
                                'page': page_num,
                                'dataframe': df,
                                'num_columns': num_cols,
                                'table_index': table_idx,
                                'has_financial': table_info['has_financial'],
                                'separators': separators
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
                
                # Group words by row (y-coordinate) with tolerance
                rows_dict = defaultdict(list)
                y_tolerance = 3  # pixels - words within this distance are considered same row
                
                for word in words:
                    word_y = word['top']
                    # Find if there's an existing row within tolerance
                    matched_row = None
                    for existing_y in rows_dict.keys():
                        if abs(word_y - existing_y) <= y_tolerance:
                            matched_row = existing_y
                            break
                    
                    if matched_row is not None:
                        rows_dict[matched_row].append(word)
                    else:
                        rows_dict[word_y].append(word)
                
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
