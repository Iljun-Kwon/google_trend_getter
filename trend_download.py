import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

PROFILE_DIR = Path.cwd() / "edge_automation_profile"
PROFILE_DIR.mkdir(parents=True, exist_ok=True)
EDGE_DRIVER_PATH = r"C:\WebDriver\msedgedriver.exe"

ALLOWED_GEOS = {"KR", "US", "MX"}

def trends_url(geo: str) -> str:
    g = geo.upper()
    if g not in ALLOWED_GEOS:
        raise ValueError(f"geo must be one of {sorted(ALLOWED_GEOS)}")
    return f"https://trends.google.co.kr/trends/explore?date=now%207-d&geo={g}&gprop=youtube&hl=ko"


def make_edge_driver(download_dir: Path):
    download_dir.mkdir(parents=True, exist_ok=True)

    opts = EdgeOptions()
    opts.add_argument("--log-level=3")
    opts.add_argument("--window-size=1400,1000")
    opts.add_argument("--disable-gpu")
    opts.add_argument(f"--user-data-dir={PROFILE_DIR.resolve()}")
    opts.add_argument("--remote-debugging-port=0")

    prefs = {
        "download.default_directory": str(download_dir.resolve()),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    }
    opts.add_experimental_option("prefs", prefs)

    service = EdgeService(EDGE_DRIVER_PATH)

    return webdriver.Edge(service=service, options=opts)


def wait_for_all_downloads(download_dir: Path, expected_count=2, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        if list(download_dir.glob("*.crdownload")):
            time.sleep(0.5)
            continue

        csvs = list(download_dir.glob("*.csv"))
        if len(csvs) >= expected_count:
            return csvs

        time.sleep(0.5)

    raise TimeoutError("Downloads did not complete in time.")


def cleanup_entities_csv(download_dir: Path):
    """Delete relatedEntities.csv if it exists."""
    for p in download_dir.glob("*relatedEntities*.csv"):
        try:
            p.unlink()
            print(f"Deleted: {p.name}")
        except Exception as e:
            print(f"Failed to delete {p.name}: {e}")


def download_related_queries_only(geo: str, csv_dir: Path):
    before_csvs = {p.resolve() for p in csv_dir.glob("*.csv")}
    url = trends_url(geo)
    driver = make_edge_driver(csv_dir)
    wait = WebDriverWait(driver, 40)

    try:
        driver.get(url)
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

        wait_for_all_downloads(csv_dir, expected_count=len(export_buttons))

        # ✅ Delete relatedEntities.csv
        cleanup_entities_csv(csv_dir)
        #'''
        # for using mannual downloads, Remaining file should be relatedQueries.csv
        candidates = list(csv_dir.glob("*relatedQueries*.csv"))
        if not candidates:
            raise FileNotFoundError("relatedQueries.csv not found after download")
        newest = max(candidates, key=lambda p: p.stat().st_mtime)
        #'''

        #for preventing corrupt name
        '''
        after_csvs = {p.resolve() for p in csv_dir.glob("*.csv")}
        new_csvs = list(after_csvs - before_csvs)

        new_queries = [p for p in new_csvs if ("relatedQueries" in p.name and "clean" not in p.name)]
        if not new_queries:
            raise RuntimeError("Download failed: no NEW relatedQueries*.csv appeared (prevented corrupt rename).")
        newest = max(new_queries, key=lambda p: p.stat().st_mtime)
        #'''

        return newest
    
    finally:
        driver.quit()


if __name__ == "__main__":
    base = Path.cwd() / "csv"
    for g in ("KR", "US", "MX"):
        out_dir = base / g
        p = download_related_queries_only(g, out_dir)
