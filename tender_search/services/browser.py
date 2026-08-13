import os
import time

from playwright.sync_api import sync_playwright


CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Chromium\Application\chrome.exe",
]


def delay(ms: int) -> None:
    time.sleep(ms / 1000)


def sleep_for_animation(ms: int) -> None:
    delay(ms)


def detect_chrome_path() -> str:
    env_path = os.environ.get("CHROME_PATH")
    if env_path and os.path.exists(env_path):
        return env_path
    for p in CHROME_CANDIDATES:
        if os.path.exists(p):
            return p
    raise FileNotFoundError(
        "Chrome not found. Please install Chrome or set CHROME_PATH env variable."
    )


def create_browser(headless: bool = False):
    chrome_path = os.environ.get("CHROME_PATH") or detect_chrome_path()
    pw = sync_playwright().start()
    browser = pw.chromium.launch(executable_path=chrome_path, headless=headless)
    return pw, browser


def create_page(browser):
    return browser.new_page()
