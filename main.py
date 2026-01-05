import os
import re
import time
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from fpdf import FPDF

from course_slot_parser import parse_course_slot_table

# --------------------------------------------------
# CONFIG
# --------------------------------------------------
TIMETABLE_URL = "https://academia.srmist.edu.in/#My_Time_Table_Attendance"
LOGIN_WAIT_SECONDS = 40
OUTPUT_PDF = "SRM_Timetable.pdf"

FONT_PATH = r"C:\Users\chait\AppData\Local\Microsoft\Windows\Fonts\DejaVuSans.ttf"

BROWSER_PATHS = [
    ("Brave", r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"),
    ("Comet", r"C:\Program Files\CometBrowser\Comet.exe"),
    ("Chrome", None),
    ("Edge", None),
]

# --------------------------------------------------
# STEP 1: Launch browser with user profile
# --------------------------------------------------
driver = None
used_browser = None

for name, binary in BROWSER_PATHS:
    try:
        if name != "Edge":
            options = webdriver.ChromeOptions()
            user_data_dir = os.path.join(
                os.environ["USERPROFILE"], "AppData", "Local", f"{name}UserData"
            )
            os.makedirs(user_data_dir, exist_ok=True)
            options.add_argument(f"--user-data-dir={user_data_dir}")
            options.add_argument("--start-maximized")
            options.add_argument("--new-window")
            if binary:
                options.binary_location = binary
            driver = webdriver.Chrome(options=options)
        else:
            options = webdriver.EdgeOptions()
            options.add_argument("--start-maximized")
            driver = webdriver.Edge(options=options)

        used_browser = name
        break
    except Exception as e:
        print(f"⚠️ Failed to launch {name}: {e}")

if not driver:
    raise RuntimeError("❌ No supported browser found")

print(f"✅ Launched {used_browser}")

# Ensure single tab
while len(driver.window_handles) > 1:
    driver.switch_to.window(driver.window_handles[-1])
    driver.close()
driver.switch_to.window(driver.window_handles[0])

# --------------------------------------------------
# STEP 2: Open timetable page
# --------------------------------------------------
driver.get(TIMETABLE_URL)

# --------------------------------------------------
# STEP 3: Login check
# --------------------------------------------------
try:
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CLASS_NAME, "course_tbl"))
    )
    print("✅ Already logged in")
except:
    print(f"➡️ Login manually ({LOGIN_WAIT_SECONDS}s)")
    time.sleep(LOGIN_WAIT_SECONDS)
    driver.get(TIMETABLE_URL)
    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.CLASS_NAME, "course_tbl"))
    )

# --------------------------------------------------
# STEP 4: Parse slot → subject mapping
# --------------------------------------------------
html = driver.page_source
slot_map = parse_course_slot_table(html)

# --------------------------------------------------
# STEP 5: Extract batch number
# --------------------------------------------------
soup = BeautifulSoup(html, "html.parser")
batch_number = None

for tr in soup.find_all("tr"):
    tds = tr.find_all("td")
    if len(tds) >= 2 and tds[0].get_text(strip=True) == "Combo / Batch:":
        text = tds[1].get_text(strip=True)
        if "/" in text:
            batch_number = text.split("/")[-1]
        break

if batch_number not in {"1", "2"}:
    raise RuntimeError("❌ Failed to detect batch number")

print(f"🎯 Detected Batch {batch_number}")

# --------------------------------------------------
# STEP 6: Open Unified Timetable page
# --------------------------------------------------
if batch_number == "1":
    batch_url = "https://academia.srmist.edu.in/login#Page:Unified_Time_Table_2025_Batch_1"
    caption_text = "Unified Time Table for B.Tech / M.Tech - Batch 1"
else:
    batch_url = "https://academia.srmist.edu.in/login#Page:Unified_Time_Table_2025_batch_2"
    caption_text = "Unified Time Table for B.Tech / M.Tech - Batch 2"

driver.get(batch_url)

# Wait for timetable
start = time.time()
while True:
    soup = BeautifulSoup(driver.page_source, "html.parser")
    caption = soup.find("caption", string=lambda x: x and caption_text in x)
    if caption:
        break
    if time.time() - start > 60:
        raise RuntimeError("❌ Timetable did not load")
    time.sleep(2)

print("✅ Timetable loaded")

table = caption.find_parent("table")

# --------------------------------------------------
# STEP 7: Convert timetable to DataFrame
# --------------------------------------------------
# Try to read with header=None first to preserve all columns
try:
    df = pd.read_html(str(table), header=None)[0]
except:
    df = pd.read_html(str(table))[0]

# --------------------------------------------------
# STEP 8: NORMALIZE TABLE (FIXES PDF ISSUES)
# --------------------------------------------------

# Extract first column header from HTML if it exists
soup_table = BeautifulSoup(str(table), "html.parser")
first_col_header = "Day"  # Default header name

# Try to find the header rows to get proper first column header
header_rows = soup_table.find_all("tr", limit=3)
if len(header_rows) >= 3:
    # Check if first column has multi-row headers (FROM, TO, Hour/Day Order)
    first_cell_headers = []
    for row in header_rows[:3]:
        first_cell = row.find("td") or row.find("th")
        if first_cell:
            text = first_cell.get_text(strip=True)
            if text:
                first_cell_headers.append(text)
    
    # If we found header info, use "Day" as header, otherwise use first found text
    if first_cell_headers:
        # Check if any contains "Hour" or "Day" or "Order"
        if any("hour" in h.lower() or "day" in h.lower() or "order" in h.lower() for h in first_cell_headers):
            first_col_header = "Day/Hour"
        else:
            first_col_header = first_cell_headers[-1] if first_cell_headers else "Day"

# Check if first column is a numeric index (not Day column)
first_col_name = str(df.columns[0])
if first_col_name.isdigit() or first_col_name == "0" or first_col_name.lower() == "nan":
    # First column might be index, check if it has Day data
    if len(df) > 0:
        first_col_sample = str(df.iloc[0, 0]).lower()
        if "day" not in first_col_sample and not first_col_name.isdigit():
            # Not a day column, might be index - check if we should keep it
            pass
    # If it's numeric index, we'll keep it but rename it
    if first_col_name.isdigit() or first_col_name == "0":
        # Rename first column to "Day" if it contains day info, otherwise keep as is
        pass

# Fill merged cells
df = df.ffill()

# Merge FROM/TO rows into one time range row
# Find rows that contain FROM and TO (check first column and also check if column headers contain them)
from_row_idx = None
to_row_idx = None
hour_order_row_idx = None

# Check first few rows for FROM/TO in first column
for idx in range(min(5, len(df))):
    first_cell = str(df.iloc[idx, 0]).lower().strip()
    if "from" in first_cell and from_row_idx is None:
        from_row_idx = idx
    elif "to" in first_cell and to_row_idx is None:
        to_row_idx = idx
    elif ("hour" in first_cell or "order" in first_cell) and hour_order_row_idx is None:
        hour_order_row_idx = idx

# Also check column headers for FROM/TO
col_headers = [str(col).lower() for col in df.columns]
if "from" in col_headers[0] or any("from" in str(df.iloc[0, i]).lower() for i in range(min(3, len(df.columns)))):
    # FROM might be in headers, check first row
    if from_row_idx is None:
        for idx in range(min(3, len(df))):
            if any("from" in str(df.iloc[idx, i]).lower() for i in range(min(3, len(df.columns)))):
                from_row_idx = idx
                break

# If we found FROM and TO rows, merge them
if from_row_idx is not None and to_row_idx is not None:
    # Combine FROM and TO times into "FROM-TO" format
    for col_idx in range(1, len(df.columns)):  # Skip first column
        from_val = str(df.iloc[from_row_idx, col_idx]).strip()
        to_val = str(df.iloc[to_row_idx, col_idx]).strip()
        
        # Skip if values are just "FROM" or "TO" labels
        if from_val and to_val and from_val.lower() != "from" and to_val.lower() != "to":
            # Combine time ranges (e.g., "08:00 - 08:50" and "08:00 - 08:50" -> "08:00-08:50")
            # Or if they're different, combine them
            if from_val == to_val:
                combined = from_val
            else:
                # Extract just the time part if there are dashes
                from_time = from_val.split("-")[-1].strip() if "-" in from_val else from_val
                to_time = to_val.split("-")[-1].strip() if "-" in to_val else to_val
                combined = f"{from_val.split('-')[0].strip() if '-' in from_val else from_val}-{to_time}"
            df.iloc[from_row_idx, col_idx] = combined
    
    # Update first column to show combined header
    df.iloc[from_row_idx, 0] = "Time" if "hour" not in str(df.iloc[from_row_idx, 0]).lower() else df.iloc[from_row_idx, 0]
    
    # Remove the TO row
    df = df.drop(df.index[to_row_idx]).reset_index(drop=True)
    print("✅ Merged FROM/TO rows into single time range row")

# Replace slot codes → subjects (including slashed codes like P2/X)
def replace_slot_code(value):
    """Replace slot codes with subject names, handling slashed codes like P2/X, and remove room numbers"""
    if not isinstance(value, str):
        return value
    
    value = str(value).strip()
    
    # Helper function to remove room numbers (everything in parentheses)
    def remove_room_info(text):
        """Remove room information in parentheses"""
        # Remove content in parentheses
        text = re.sub(r'\([^)]*\)', '', text)
        # Clean up extra spaces
        text = ' '.join(text.split())
        return text.strip()
    
    # Handle slashed codes like "P2/X" or "B/X"
    if "/" in value and not value.startswith("/"):
        parts = value.split("/", 1)
        base_slot = parts[0].strip()
        suffix = parts[1].strip() if len(parts) > 1 else ""
        
        # Get subject name for base slot
        if base_slot in slot_map:
            subject_name = slot_map[base_slot]
            # Remove room info from subject name
            subject_base = remove_room_info(subject_name)
            
            # Return subject name with suffix: "Molecular Biology Laboratory/X"
            return f"{subject_base}/{suffix}" if suffix else subject_base
        else:
            # If base slot not found, return as is
            return value
    
    # Regular slot code replacement - remove room numbers
    if value in slot_map:
        subject_name = slot_map[value]
        return remove_room_info(subject_name)
    
    # If not in slot_map, remove room info from value itself if present
    return remove_room_info(value)

df = df.map(replace_slot_code)
df = df.astype(str)

# Detect if first column contains Day information
first_col_has_day = False
if len(df) > 0 and len(df.columns) > 0:
    # Check first few rows of first column for "Day" pattern
    first_col_values = [str(df.iloc[i, 0]).lower() for i in range(min(7, len(df)))]
    first_col_has_day = any("day" in val for val in first_col_values) or any("from" in val for val in first_col_values) or any("to" in val for val in first_col_values) or any("hour" in val for val in first_col_values)
    
    # If first column has day info, rename it to "Day"
    if first_col_has_day:
        df.columns = [first_col_header] + list(df.columns[1:])

# Remove last 2 columns (if there are more than 2 columns)
if len(df.columns) > 2:
    df = df.iloc[:, :-2]
    print(f"✅ Removed last 2 columns. Remaining columns: {len(df.columns)}")
elif len(df.columns) <= 2:
    print(f"⚠️ Warning: Only {len(df.columns)} column(s) available, cannot remove 2 columns")

print("✅ Timetable normalized")

# --------------------------------------------------
# REMOVE "Hour / Day Order" ROW (1 2 3 4 ...)
# --------------------------------------------------

def is_hour_day_order_row(row):
    """
    Detect rows like:
    Day | 1 | 2 | 3 | 4 | ...
    or
    Hour/Day Order | 1 | 2 | 3 | ...
    """
    first_cell = str(row.iloc[0]).lower()
    if any(keyword in first_cell for keyword in ["hour/day order"]):
        numeric_cells = sum(
            str(cell).strip().isdigit() for cell in row.iloc[1:]
        )
        return numeric_cells >= len(row) - 2
    return False

rows_to_drop = []
for idx in range(len(df)):
    if is_hour_day_order_row(df.iloc[idx]):
        rows_to_drop.append(idx)

if rows_to_drop:
    df = df.drop(rows_to_drop).reset_index(drop=True)
    print("✅ Removed Hour / Day Order row")

# --------------------------------------------------
# STEP 9: Generate PDF using FPDF
# --------------------------------------------------
pdf = FPDF(orientation="L", unit="mm", format="A4")
pdf.add_page()

# Register fonts
pdf.add_font("DejaVu", "", FONT_PATH, uni=True)
pdf.add_font("DejaVu", "B", FONT_PATH, uni=True)

pdf.set_font("DejaVu", "B", 16)
pdf.cell(0, 10, f"SRM Academic Timetable - Batch {batch_number}", ln=1, align="C")
pdf.ln(4)

page_width = pdf.w - 20
row_height = 14  # Increased height to accommodate longer subject names and larger fonts

# Set column widths: fixed width for Day column, equal width for others
if first_col_has_day:
    day_col_width = 25  # Fixed width for Day column
    remaining_width = page_width - day_col_width
    other_col_width = remaining_width / (len(df.columns) - 1) if len(df.columns) > 1 else remaining_width
else:
    day_col_width = 0
    other_col_width = page_width / len(df.columns) if len(df.columns) > 0 else page_width

def truncate_text(text, max_width, font_name, font_style, font_size):
    """Truncate text to fit within cell width using FPDF's text width calculation"""
    pdf.set_font(font_name, font_style, font_size)
    text = str(text).replace("\u2013", "-")
    
    # Get actual text width
    text_width = pdf.get_string_width(text)
    
    if text_width <= max_width:
        return text
    
    # Binary search for maximum fitting length
    low, high = 0, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        test_text = text[:mid] + "..."
        test_width = pdf.get_string_width(test_text)
        if test_width <= max_width:
            low = mid
        else:
            high = mid - 1
    
    if low == 0:
        return "..."
    return text[:low] + "..."

# Header with larger font
header_font_size = 11
pdf.set_font("DejaVu", "B", header_font_size)
for idx, col in enumerate(df.columns):
    # All columns center aligned
    width = day_col_width if (first_col_has_day and idx == 0) else (other_col_width if first_col_has_day else other_col_width)
    text = truncate_text(col, width, "DejaVu", "B", header_font_size)
    pdf.cell(width, row_height, text, border=1, align="C")
pdf.ln()

# Data rows with multi-line support and larger font
data_font_size = 10
time_font_size = 12  # Larger font for time/hour rows
pdf.set_font("DejaVu", "", data_font_size)
line_height = 5
 # Height per line of text (increased for larger font)

for row_idx, (_, row) in enumerate(df.iterrows()):
    # Check if this is a time/hour row
    first_cell_text = str(row.iloc[0]).lower() if len(row) > 0 else ""
    is_time_row = any(keyword in first_cell_text for keyword in ["time", "hour", "order", "from", "to"])
    # Calculate required height for each cell in this row
    cell_heights = []
    cell_widths = []
    cell_texts = []
    
    for idx, val in enumerate(row):
        if first_col_has_day and idx == 0:
            width = day_col_width
            font_style = "B"  # Keep Day column bold
        else:
            width = day_col_width if (first_col_has_day and idx == 0) else (other_col_width if first_col_has_day else other_col_width)
            font_style = ""
        
        # Use bold and larger font for time/hour rows
        if is_time_row:
            font_style = "B"
            current_font_size = time_font_size
        else:
            current_font_size = data_font_size
        
        text = str(val).replace("\u2013", "-")
        
        # Calculate how many lines this text will need with appropriate font
        pdf.set_font("DejaVu", font_style, current_font_size)
        # Use a more accurate method: split text and measure
        words = text.split()
        lines = []
        current_line = ""
        
        for word in words:
            test_line = current_line + (" " if current_line else "") + word
            if pdf.get_string_width(test_line) <= width - 4:  # -4 for padding with larger font
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        
        if current_line:
            lines.append(current_line)
        
        lines_needed = max(1, len(lines))
        
        # Cap at 4 lines and truncate text if it exceeds
        max_lines = 4
        final_text = text
        if lines_needed > max_lines:
            # Truncate text to fit in 4 lines
            truncated_lines = lines[:max_lines]
            # Add "..." to last line if text was truncated
            if len(lines) > max_lines:
                last_line = truncated_lines[-1]
                if len(last_line) > 0:
                    # Try to fit "..." at the end
                    pdf.set_font("DejaVu", font_style, data_font_size)
                    while pdf.get_string_width(last_line + "...") > width - 4 and len(last_line) > 0:
                        last_line = last_line[:-1]
                    truncated_lines[-1] = last_line + "..."
            # Reconstruct text from truncated lines
            final_text = " ".join(truncated_lines)
            lines_needed = max_lines
        
        cell_widths.append(width)
        cell_texts.append((final_text, font_style, current_font_size))
        # Use larger line height for time rows
        current_line_height = line_height * 1.2 if is_time_row else line_height
        cell_height = max(row_height, lines_needed * current_line_height)
        cell_heights.append(cell_height)
    
    # Use the maximum height for all cells in this row
    max_cell_height = max(cell_heights) if cell_heights else row_height
    
    # Draw each cell with multi_cell
    start_x = 10  # Left margin
    start_y = pdf.get_y()
    current_x = start_x
    
    for idx, cell_data in enumerate(cell_texts):
        if len(cell_data) == 3:
            text, font_style, cell_font_size = cell_data
        else:
            text, font_style = cell_data
            cell_font_size = time_font_size if is_time_row else data_font_size
        
        width = cell_widths[idx]
        
        # Draw border rectangle first (ensures all cells have same height)
        pdf.rect(current_x, start_y, width, max_cell_height)
        
        # Calculate vertical centering for time/hour rows
        if is_time_row:
            # Set font first for accurate width calculation
            pdf.set_font("DejaVu", font_style, cell_font_size)
            # Use larger line height for time rows
            current_line_height = cell_font_size * 0.6  # Line height for time rows
            # Calculate number of lines text will take
            words = text.split()
            lines = []
            current_line = ""
            for word in words:
                test_line = current_line + (" " if current_line else "") + word
                if pdf.get_string_width(test_line) <= width - 4:
                    current_line = test_line
                else:
                    if current_line:
                        lines.append(current_line)
                    current_line = word
            if current_line:
                lines.append(current_line)
            
            # Calculate actual text height
            num_lines = max(1, len(lines))
            text_height = num_lines * current_line_height
            # Center vertically
            text_start_y = start_y + (max_cell_height - text_height) / 2
        else:
            text_start_y = start_y
            current_line_height = line_height
        
        # Reset position for text inside cell
        pdf.set_xy(current_x, text_start_y)
        
        # Set font with appropriate size
        pdf.set_font("DejaVu", font_style, cell_font_size)
        
        # All cells center aligned
        align = "C"
        
        # Use the line height calculated above (or default for non-time rows)
        if not is_time_row:
            current_line_height = line_height
        
        # Draw text with multi_cell (no border, we drew it manually)
        pdf.multi_cell(width, current_line_height, text, border=0, align=align)
        
        # Reset y position back to start_y for next cell
        pdf.set_xy(current_x + width, start_y)
        
        # Move x position for next cell
        current_x += width
    
    # Move to next row (reset x, move y down by max height)
    pdf.set_xy(10, start_y + max_cell_height)

pdf.output(OUTPUT_PDF)
print(f"✅ PDF saved as {OUTPUT_PDF}")

# --------------------------------------------------
# STEP 10: Cleanup
# --------------------------------------------------
driver.quit()
print("🧹 Browser closed")
