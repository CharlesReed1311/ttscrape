import os
import re
import time
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from course_slot_parser import parse_course_slot_table
from pdf_gen import generate_pdf

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
# STEP 7: Extract UNIQUE Day-wise rows into list
# --------------------------------------------------
day_rows = []
seen = set()

for tr in table.find_all("tr"):
    tds = tr.find_all("td")
    if not tds:
        continue

    first_cell_text = tds[0].get_text(strip=True)

    # Match only "Day 1", "Day 2", ...
    if re.fullmatch(r"Day\s+\d+", first_cell_text):
        # ⬇️ remove last 2 always-null cells here
        row = tuple(td.get_text(strip=True) for td in tds[:-2])

        if row not in seen:
            seen.add(row)
            day_rows.append(list(row))

# --------------------------------------------------
# STEP 8: Add Day/Time headers and create DataFrame
# --------------------------------------------------
time_headers = [
    "08:00 - 08:50",
    "08:50 - 09:40",
    "09:45 - 10:35",
    "10:40 - 11:30",
    "11:35 - 12:25",
    "12:30 - 01:20",
    "01:25 - 02:15",
    "02:20 - 03:10",
    "03:10 - 04:00",
    "04:00 - 04:50",
]
headers = ["Day/Time"] + time_headers

df = pd.DataFrame(day_rows, columns=headers)

# --------------------------------------------------
# STEP 9: Generate PDF
# --------------------------------------------------
generate_pdf(df, slot_map)
