import os
import shutil

BASE_DIR = os.path.join(os.environ["USERPROFILE"], "AppData", "Local")

# These are ONLY the Selenium-created profiles from main.py
SELENIUM_PROFILES = [
    "BraveUserData",
    "CometUserData",
    "ChromeUserData",
]

deleted = False

for profile in SELENIUM_PROFILES:
    path = os.path.join(BASE_DIR, profile)

    if os.path.exists(path):
        try:
            shutil.rmtree(path)
            print(f"🗑️ Deleted Selenium browser profile: {profile}")
            deleted = True
        except Exception as e:
            print(f"⚠️ Failed to delete {profile}: {e}")

if not deleted:
    print("ℹ️ No Selenium browser profiles found")

print("✅ Logout complete — Selenium sessions cleared")
