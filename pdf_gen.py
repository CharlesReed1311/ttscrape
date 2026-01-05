from fpdf import FPDF
import pandas as pd

FONT_PATH = r"C:\Users\chait\AppData\Local\Microsoft\Windows\Fonts\DejaVuSans.ttf"
FONT_PATH_BOLD = r"C:\Users\chait\AppData\Local\Microsoft\Windows\Fonts\DejaVuSans-Bold.ttf"
MAX_LINES = 4
LINE_HEIGHT = 10  # per line height

def map_slot_to_subject(cell_text, slot_map):
    """Map slot codes to subject names. Handles compound slots like P2/X"""
    if not isinstance(cell_text, str):
        return str(cell_text), False  # False = slot not in map

    parts = cell_text.split('/')
    mapped_parts = []
    found_any = False

    for part in parts:
        part = part.strip()
        if part in slot_map:
            mapped_parts.append(slot_map[part])
            found_any = True
        else:
            mapped_parts.append("-")  # replace unknown slot with "-"
    
    return " / ".join(mapped_parts), found_any


def generate_pdf(df: pd.DataFrame, slot_map: dict, output_file="timetable.pdf"):
    pdf = FPDF(orientation="L", unit="mm", format="A3")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Use dark theme
    pdf.set_fill_color(0, 0, 0)
    pdf.rect(0, 0, pdf.w, pdf.h, style="F")
    pdf.set_text_color(255, 255, 255)

    # Register font
    pdf.add_font("CustomFont", "", FONT_PATH, uni=True)
    pdf.add_font("CustomFont", "B", FONT_PATH_BOLD, uni=True)

    # Title
    pdf.set_font("CustomFont", "B", 20)
    pdf.cell(0, 12, "SRM Timetable", ln=True, align="C")
    pdf.ln(4)

    # Determine column widths dynamically
    usable_width = pdf.w - 20  # left + right margins
    num_cols = len(df.columns)
    day_col_width = 30  # first column fixed for Day/Time
    other_col_width = (usable_width - day_col_width) / (num_cols - 1)  
    col_widths = [day_col_width] + [other_col_width] * (num_cols - 1)

    # ----------------------------
    # Header row using multi_cell
    # ----------------------------
    pdf.set_font("CustomFont", "B", 14)
    x_start = pdf.l_margin
    y_start = pdf.get_y()

    # First, pre-calculate max header height
    header_lines_list = []
    header_heights = []

    for idx, col in enumerate(df.columns):
        lines = pdf.multi_cell(
            w=col_widths[idx],
            h=LINE_HEIGHT,
            txt=str(col),
            split_only=True
        )
        if len(lines) > MAX_LINES:
            lines = lines[:MAX_LINES]
            # truncate last line if needed
            while pdf.get_string_width(lines[-1] + "...") > col_widths[idx]:
                lines[-1] = lines[-1][:-1]
            lines[-1] += "..."
        header_lines_list.append(lines)
        header_heights.append(LINE_HEIGHT * len(lines))

    max_header_height = max(header_heights)

    # Draw each header cell
    x_draw = x_start
    for idx, lines in enumerate(header_lines_list):
        width = col_widths[idx]
        pdf.set_xy(x_draw, y_start)
        pdf.set_draw_color(255, 255, 255)
        pdf.rect(x_draw, y_start, width, max_header_height)  # border

        # Center text vertically
        total_text_height = LINE_HEIGHT * len(lines)
        y_text = y_start + (max_header_height - total_text_height) / 2
        pdf.set_xy(x_draw, y_text)
        pdf.multi_cell(width, LINE_HEIGHT, "\n".join(lines), border=0, align="C")

        x_draw += width

    pdf.set_xy(pdf.l_margin, y_start + max_header_height)  # move below header

    # ----------------------------
    # Data rows
    # ----------------------------
    pdf.set_font("CustomFont", "", 14)
    pdf.set_draw_color(255, 255, 255)

    for _, row in df.iterrows():
        # Map slots to subject names
        mapped_row = []
        slot_found_flags = []  # track which slots exist in map

        for idx, col in enumerate(df.columns):
            cell_text = row[col]

            if idx == 0:
                # Exempt Day/Time column from mapping
                mapped_row.append(str(cell_text))
                slot_found_flags.append(True)  # treat as valid
            else:
                mapped_text, found = map_slot_to_subject(cell_text, slot_map)
                mapped_row.append(mapped_text)
                slot_found_flags.append(found)

        # Calculate cell heights
        cell_heights = []
        wrapped_lines_list = []

        for idx, text in enumerate(mapped_row):
            text = str(text).replace("\u2013", "-")  # replace en-dash
            lines = pdf.multi_cell(
                w=col_widths[idx],
                h=LINE_HEIGHT,
                txt=text,
                split_only=True
            )
            if len(lines) > MAX_LINES:
                lines = lines[:MAX_LINES]
                while pdf.get_string_width(lines[-1] + "...") > col_widths[idx]:
                    lines[-1] = lines[-1][:-1]
                lines[-1] += "..."
            wrapped_lines_list.append(lines)
            cell_heights.append(LINE_HEIGHT * len(lines))

        max_row_height = max(cell_heights)

        # Draw cells
        x_start = pdf.get_x()
        y_start = pdf.get_y()

        for idx, lines in enumerate(wrapped_lines_list):
            width = col_widths[idx]

            # Vertical centering only for Day/Time column (idx=0)
            if idx == 0:
                total_text_height = LINE_HEIGHT * len(lines)
                y_text = y_start + (max_row_height - total_text_height) / 2
            else:
                y_text = y_start

            # Set fill color
            if idx == 0:
                pdf.set_fill_color(0, 0, 0)  # keep Day/Time black
            else:
                cell_text_lower = mapped_row[idx].lower()
                if not slot_found_flags[idx]:  # slot not found
                    pdf.set_fill_color(50, 50, 50)  # grey
                elif "lab" in cell_text_lower:  # LAB slot
                    pdf.set_fill_color(0, 255, 0)  # dark green
                else:  # non-LAB slot
                    pdf.set_fill_color(50, 50, 255)  # blue

            # Draw border + fill
            pdf.set_draw_color(255, 255, 255)
            pdf.rect(x_start, y_start, width, max_row_height, style="DF")

            # Draw text
            pdf.set_xy(x_start, y_text)
            pdf.multi_cell(width, LINE_HEIGHT, "\n".join(lines), border=0, align="C")

            x_start += width

        # Move to next row
        pdf.set_xy(pdf.l_margin, y_start + max_row_height)

    # Save PDF
    pdf.output(output_file)
    print(f"✅ PDF saved as {output_file}")
