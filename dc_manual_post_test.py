import argparse
import pickle
import textwrap
import time
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager


BASE_DIR = Path(__file__).resolve().parent
COOKIE_PATH = BASE_DIR / "cookies_dc.pkl"
DEBUG_DIR = BASE_DIR / "data" / "dc_post_test"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)
LOGIN_URL = "https://sign.dcinside.com/login?s_url=https%3A%2F%2Fgall.dcinside.com%2F&s_key=513"
HOME_URL = "https://gall.dcinside.com/"
DEFAULT_WAIT = 15
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Open a DCInside write page, prefill content, and optionally submit."
    )
    parser.add_argument("--gallery-url", help="Target gallery URL, for example https://gall.dcinside.com/mgallery/board/lists/?id=example")
    parser.add_argument("--title", help="Post title")
    parser.add_argument("--body", help="Post body text")
    parser.add_argument("--body-file", help="UTF-8 text file to load as the post body")
    parser.add_argument("--attach", nargs="*", default=[], help="Optional attachment file paths")
    parser.add_argument("--submit", action="store_true", help="Click the final submit button automatically")
    parser.add_argument("--headless", action="store_true", help="Run Chrome in headless mode")
    return parser.parse_args()


def prompt_value(label: str) -> str:
    value = ""
    while not value.strip():
        value = input(f"{label}: ").strip()
    return value


def prompt_body() -> str:
    print("Body input mode. End with a single line containing :end")
    lines: list[str] = []
    while True:
        line = input()
        if line.strip() == ":end":
            break
        lines.append(line)
    body = "\n".join(lines).strip()
    if not body:
        raise ValueError("Body cannot be empty")
    return body


def resolve_body(args: argparse.Namespace) -> str:
    if args.body_file:
        return Path(args.body_file).read_text(encoding="utf-8").strip()
    if args.body:
        return args.body.strip()
    return prompt_body()


def resolve_attachments(paths: list[str]) -> list[str]:
    resolved: list[str] = []
    for raw in paths:
        path = Path(raw).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Attachment not found: {path}")
        resolved.append(str(path))
    return resolved


def create_driver(headless: bool) -> webdriver.Chrome:
    options = Options()
    options.add_argument(f"user-agent={USER_AGENT}")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1440,1200")
    if headless:
        options.add_argument("--headless=new")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)


def load_cookies(driver: webdriver.Chrome) -> int:
    if not COOKIE_PATH.exists():
        return 0
    driver.get(HOME_URL)
    count = 0
    with COOKIE_PATH.open("rb") as handle:
        cookies = pickle.load(handle)
    for cookie in cookies:
        clean_cookie = dict(cookie)
        clean_cookie.pop("expiry", None)
        if clean_cookie.get("sameSite") not in {"Strict", "Lax", "None"}:
            clean_cookie.pop("sameSite", None)
        try:
            driver.add_cookie(clean_cookie)
            count += 1
        except WebDriverException:
            continue
    driver.get(HOME_URL)
    return count


def save_cookies(driver: webdriver.Chrome) -> None:
    with COOKIE_PATH.open("wb") as handle:
        pickle.dump(driver.get_cookies(), handle)


def wait_for_page_ready(driver: webdriver.Chrome, timeout: int = DEFAULT_WAIT) -> None:
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )


def is_logged_in(driver: webdriver.Chrome) -> bool:
    wait_for_page_ready(driver)
    page_text = driver.page_source
    if "logout" in page_text.lower():
        return True
    if "로그아웃" in page_text:
        return True
    if "로그인해 주세요" in page_text:
        return False
    try:
        driver.find_element(By.XPATH, "//*[contains(text(), '로그아웃')]")
        return True
    except NoSuchElementException:
        return False


def ensure_logged_in(driver: webdriver.Chrome) -> None:
    loaded = load_cookies(driver)
    if loaded and is_logged_in(driver):
        print(f"Loaded {loaded} saved cookie(s).")
        return
    print("Saved login cookies are missing or expired.")
    print("A login page will open. Please log in with your own account.")
    driver.get(LOGIN_URL)
    input("After login is complete in the browser, press Enter here...")
    driver.get(HOME_URL)
    if not is_logged_in(driver):
        raise RuntimeError("Login was not detected. Please try again.")
    save_cookies(driver)
    print(f"Saved refreshed login cookies to {COOKIE_PATH}")


def find_first(driver: webdriver.Chrome, selectors: list[tuple[str, str]]):
    for by, value in selectors:
        try:
            element = driver.find_element(by, value)
            if element.is_displayed():
                return element
        except NoSuchElementException:
            continue
    raise NoSuchElementException(f"No element matched selectors: {selectors}")


def open_write_page(driver: webdriver.Chrome, gallery_url: str) -> None:
    driver.get(gallery_url)
    wait_for_page_ready(driver)
    if "/write/" in driver.current_url:
        return

    selectors = [
        (By.XPATH, "//a[contains(normalize-space(.), '글쓰기')]"),
        (By.XPATH, "//button[contains(normalize-space(.), '글쓰기')]"),
        (By.CSS_SELECTOR, "a[href*='/board/write/']"),
        (By.CSS_SELECTOR, "a[href*='/mgallery/board/write/']"),
    ]
    button = find_first(driver, selectors)
    driver.execute_script("arguments[0].click();", button)
    WebDriverWait(driver, DEFAULT_WAIT).until(lambda d: "/write/" in d.current_url)
    wait_for_page_ready(driver)


def fill_title(driver: webdriver.Chrome, title: str) -> None:
    selectors = [
        (By.CSS_SELECTOR, "input[name='subject']"),
        (By.CSS_SELECTOR, "input#subject"),
        (By.CSS_SELECTOR, "input[placeholder*='제목']"),
        (By.CSS_SELECTOR, "input[type='text']"),
    ]
    title_input = find_first(driver, selectors)
    title_input.clear()
    title_input.send_keys(title)


def fill_body_in_textarea(driver: webdriver.Chrome, body: str) -> bool:
    selectors = [
        (By.CSS_SELECTOR, "textarea[name='memo']"),
        (By.CSS_SELECTOR, "textarea#memo"),
        (By.CSS_SELECTOR, "textarea"),
    ]
    for by, value in selectors:
        try:
            element = driver.find_element(by, value)
            if not element.is_displayed():
                continue
            driver.execute_script("arguments[0].value = arguments[1];", element, body)
            driver.execute_script(
                "arguments[0].dispatchEvent(new Event('input', {bubbles: true}));",
                element,
            )
            return True
        except NoSuchElementException:
            continue
    return False


def fill_body_in_summernote(driver: webdriver.Chrome, body: str) -> bool:
    try:
        editable = driver.find_element(By.CSS_SELECTOR, ".note-editor .note-editable[contenteditable='true']")
    except NoSuchElementException:
        return False

    if not editable.is_displayed():
        return False

    html = body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    html = html.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")

    # DC mini galleries currently use Summernote. Writing through its API keeps
    # the hidden textarea and editor state in sync better than typing into the DOM.
    driver.execute_script(
        """
        const html = arguments[0];
        if (window.jQuery && jQuery('#memo').length && jQuery('#memo').summernote) {
            jQuery('#memo').summernote('code', html);
            jQuery('#memo').summernote('focus');
            return;
        }
        const editable = document.querySelector('.note-editor .note-editable[contenteditable="true"]');
        if (editable) {
            editable.innerHTML = html;
            editable.dispatchEvent(new Event('input', { bubbles: true }));
        }
        const memo = document.querySelector('#memo');
        if (memo) {
            memo.value = html;
            memo.dispatchEvent(new Event('input', { bubbles: true }));
            memo.dispatchEvent(new Event('change', { bubbles: true }));
        }
        """,
        html,
    )
    return True


def fill_body_in_iframe(driver: webdriver.Chrome, body: str) -> bool:
    iframes = driver.find_elements(By.TAG_NAME, "iframe")
    for frame in iframes:
        try:
            driver.switch_to.frame(frame)
            editable = driver.find_elements(By.CSS_SELECTOR, "body[contenteditable='true'], div[contenteditable='true']")
            for element in editable:
                if not element.is_displayed():
                    continue
                driver.execute_script("arguments[0].innerHTML = '';", element)
                element.send_keys(body)
                driver.switch_to.default_content()
                return True
            driver.switch_to.default_content()
        except WebDriverException:
            driver.switch_to.default_content()
    return False


def fill_body(driver: webdriver.Chrome, body: str) -> None:
    if fill_body_in_summernote(driver, body):
        return
    if fill_body_in_textarea(driver, body):
        return
    if fill_body_in_iframe(driver, body):
        return
    raise RuntimeError("Could not locate a writable body editor on the page.")


def attach_files(driver: webdriver.Chrome, attachments: list[str]) -> None:
    if not attachments:
        return
    file_input = find_first(
        driver,
        [
            (By.CSS_SELECTOR, "input[type='file']"),
        ],
    )
    file_input.send_keys("\n".join(attachments))


def click_submit(driver: webdriver.Chrome) -> None:
    selectors = [
        (By.XPATH, "//button[contains(normalize-space(.), '등록')]"),
        (By.XPATH, "//a[contains(normalize-space(.), '등록')]"),
        (By.CSS_SELECTOR, "button[type='submit']"),
        (By.CSS_SELECTOR, "input[type='submit']"),
    ]
    button = find_first(driver, selectors)
    driver.execute_script("arguments[0].click();", button)


def save_debug_bundle(driver: webdriver.Chrome, prefix: str) -> None:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    screenshot = DEBUG_DIR / f"{prefix}_{stamp}.png"
    html_dump = DEBUG_DIR / f"{prefix}_{stamp}.html"
    try:
        driver.save_screenshot(str(screenshot))
        html_dump.write_text(driver.page_source, encoding="utf-8")
        print(f"Saved debug screenshot: {screenshot}")
        print(f"Saved debug HTML: {html_dump}")
    except Exception as exc:
        print(f"Failed to save debug bundle: {exc}")


def run() -> None:
    args = parse_args()
    gallery_url = (args.gallery_url or prompt_value("Gallery URL")).strip()
    title = (args.title or prompt_value("Title")).strip()
    body = resolve_body(args)
    attachments = resolve_attachments(args.attach)

    driver = create_driver(headless=args.headless)
    try:
        ensure_logged_in(driver)
        open_write_page(driver, gallery_url)
        fill_title(driver, title)
        fill_body(driver, body)
        attach_files(driver, attachments)

        print("")
        print("The write page has been filled.")
        print(f"Current URL: {driver.current_url}")
        print(f"Attachments: {len(attachments)}")

        if args.submit:
            confirm = input("Type YES to click the final submit button automatically: ").strip()
            if confirm == "YES":
                click_submit(driver)
                print("Submit click was sent. Please verify the result in the browser.")
            else:
                print("Automatic submit was skipped.")
        else:
            print("Automatic submit is OFF. Please review and submit manually in the browser if you want.")

        input("Press Enter after you finish reviewing the browser window...")
    except (NoSuchElementException, TimeoutException, RuntimeError, WebDriverException) as exc:
        print("")
        print("The posting test did not complete cleanly.")
        print(textwrap.fill(str(exc), width=100))
        save_debug_bundle(driver, "dc_post_test_error")
        input("Press Enter after checking the browser window...")
        raise
    finally:
        driver.quit()


if __name__ == "__main__":
    run()
