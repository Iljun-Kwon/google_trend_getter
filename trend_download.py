import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


URL = "https://trends.google.co.kr/trends/explore?date=now%207-d&geo=KR&gprop=youtube&hl=ko"

DOWNLOAD_DIR = Path.cwd() / "csv"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

PROFILE_DIR = Path.cwd() / "edge_automation_profile"
PROFILE_DIR.mkdir(parents=True, exist_ok=True)


def make_edge_driver():
    opts = EdgeOptions()
    opts.add_argument("--window-size=1400,1000")
    opts.add_argument("--disable-gpu")
    opts.add_argument(f"--user-data-dir={PROFILE_DIR.resolve()}")
    opts.add_argument("--remote-debugging-port=0")

    prefs = {
        "download.default_directory": str(DOWNLOAD_DIR.resolve()),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    }
    opts.add_experimental_option("prefs", prefs)

    return webdriver.Edge(options=opts)


def wait_for_all_downloads(expected_count=2, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        if list(DOWNLOAD_DIR.glob("*.crdownload")):
            time.sleep(0.5)
            continue

        csvs = list(DOWNLOAD_DIR.glob("*.csv"))
        if len(csvs) >= expected_count:
            return csvs

        time.sleep(0.5)

    raise TimeoutError("Downloads did not complete in time.")


def cleanup_entities_csv():
    """Delete relatedEntities.csv if it exists."""
    for p in DOWNLOAD_DIR.glob("*relatedEntities*.csv"):
        try:
            p.unlink()
            print(f"Deleted: {p.name}")
        except Exception as e:
            print(f"Failed to delete {p.name}: {e}")


def download_related_queries_only():
    driver = make_edge_driver()
    wait = WebDriverWait(driver, 40)

    try:
        driver.get(URL)
        time.sleep(2)
        driver.refresh()
        time.sleep(3)

        # Scroll so both widgets render
        driver.execute_script("window.scrollTo(0, 1800);")
        time.sleep(2)

        # Find ALL CSV export buttons
        export_buttons = wait.until(
            EC.presence_of_all_elements_located(
                (By.CSS_SELECTOR, "button.widget-actions-item.export[title='CSV']")
            )
        )

        # Click all export buttons
        for btn in export_buttons:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            time.sleep(0.3)
            try:
                btn.click()
            except:
                driver.execute_script("arguments[0].click();", btn)
            time.sleep(1.2)

        wait_for_all_downloads(expected_count=len(export_buttons))

        # ✅ Delete relatedEntities.csv
        cleanup_entities_csv()

        # Remaining file should be relatedQueries.csv
        remaining = list(DOWNLOAD_DIR.glob("*.csv"))
        print("Remaining CSV files:")
        for f in remaining:
            print(" -", f.name)

    finally:
        driver.quit()


if __name__ == "__main__":
    download_related_queries_only()
