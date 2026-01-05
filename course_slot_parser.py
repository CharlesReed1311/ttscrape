from bs4 import BeautifulSoup
from typing import Dict


def parse_course_slot_table(html: str) -> Dict[str, str]:
    """
    Parses SRM 'course_tbl' table and returns a slot -> subject mapping.

    Supports:
    - Theory slots (A, B, C, ...)
    - Lab slots (P1-P2-P3- etc.)

    Output example:
    {
        "B": "Molecular Biology (B103)",
        "P1": "Molecular Biology Laboratory LAB (Molecular Biology Lab)"
    }
    """

    soup = BeautifulSoup(html, "html.parser")

    table = soup.select_one("table.course_tbl")
    if not table:
        raise ValueError("course_tbl table not found in HTML")

    slot_map: Dict[str, str] = {}

    rows = table.select("tr")[1:]  # skip header row

    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 11:
            continue

        subject = cells[2].get_text(strip=True)
        slot_raw = cells[8].get_text(strip=True)
        # Room information removed - not needed in slot map

        # LAB slots: P1-P2-P3-
        if "-" in slot_raw:
            slots = [s for s in slot_raw.split("-") if s]
            for slot in slots:
                slot_map[slot] = f"{subject} LAB"

        # THEORY slots: A, B, C...
        else:
            slot_map[slot_raw] = subject

    return slot_map

