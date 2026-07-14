import random
import requests
from bs4 import BeautifulSoup
import time
import logging
import subprocess
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service

# ── Suppress geckodriver version-mismatch warning ─────────────────────────────
logging.getLogger("selenium.webdriver.common.service").setLevel(logging.ERROR)
logging.getLogger("selenium").setLevel(logging.ERROR)

DEFAULT_TARGET    = "https://dramacina--dzeckart.replit.app"
DEFAULT_TIMEOUT   = 30
DEFAULT_STAY_TIME = 5

# ── Proxy validation settings ─────────────────────────────────────────────────
VALIDATE_TIMEOUT = 8    # seconds per proxy check (HTTP only, very fast)
VALIDATE_WORKERS = 50   # parallel threads for validation phase
# Neutral lightweight endpoint — just checks connectivity, no side effects
VALIDATE_URL     = "http://httpbin.org/ip"

# ── Proxy sources ─────────────────────────────────────────────────────────────
API_SOURCES = [
    (
        "ProxyScrape HTTP",
        "https://api.proxyscrape.com/v3/free-proxy-list/get"
        "?request=displayproxies&proxy_type=http&timeout=5000"
        "&country=all&ssl=all&anonymity=all&simplified=true",
    ),
    (
        "TheSpeedX/PROXY-List HTTP",
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    ),
    (
        "monosans/proxy-list HTTP",
        "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    ),
    (
        "clarketm/proxy-list",
        "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
    ),
]

HTML_SOURCES = [
    "https://free-proxy-list.net",
    "https://www.sslproxies.org",
    "https://us-proxy.org",
    "https://free-proxy-list.net/anonymous-proxy.html",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


# ── Fetchers ──────────────────────────────────────────────────────────────────

def _fetch_api(name, url, log_fn):
    """Fetch plain-text ip:port list from an API endpoint."""
    try:
        r = requests.get(url, timeout=15, headers=HEADERS)
        r.raise_for_status()
        proxies = []
        for line in r.text.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '://' in line:
                line = line.split('://', 1)[1]
            parts = line.split(':')
            if len(parts) == 2 and parts[1].isdigit():
                proxies.append((parts[0], int(parts[1])))
        log_fn(f"[FETCH] {name}: {len(proxies)} proxies")
        return proxies
    except Exception as e:
        log_fn(f"[WARN] {name} failed: {e}")
        return []


def _fetch_html(url, log_fn):
    """Fallback: scrape HTML table (free-proxy-list style)."""
    try:
        r = requests.get(url, timeout=15, headers=HEADERS)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, 'html.parser')
        table = soup.find(class_='table table-striped table-bordered')
        if not table:
            log_fn(f"[WARN] No table at {url}")
            return []
        proxies = []
        for row in table.find_all('tr')[1:]:
            cols = row.find_all('td')
            if len(cols) >= 2:
                ip   = cols[0].get_text(strip=True)
                port = cols[1].get_text(strip=True)
                if ip and port.isdigit():
                    proxies.append((ip, int(port)))
        log_fn(f"[FETCH] HTML {url}: {len(proxies)} proxies")
        return proxies
    except Exception as e:
        log_fn(f"[WARN] HTML {url} failed: {e}")
        return []


def fetch_all_proxies(log_fn=print):
    """Collect proxies from all sources. Returns deduplicated (ip, port) list."""
    seen   = set()
    result = []

    for name, url in API_SOURCES:
        for item in _fetch_api(name, url, log_fn):
            if item not in seen:
                seen.add(item)
                result.append(item)

    if len(result) < 500:
        log_fn("[INFO] API sources low — trying HTML fallback sources")
        for url in HTML_SOURCES:
            for item in _fetch_html(url, log_fn):
                if item not in seen:
                    seen.add(item)
                    result.append(item)

    random.shuffle(result)
    return result


# ── Proxy validator ───────────────────────────────────────────────────────────

def _check_proxy(ip, port):
    """
    Quick connectivity check via plain HTTP request.
    Returns True if the proxy responds successfully, False otherwise.
    Much faster than opening a browser — used to pre-filter dead proxies.
    """
    proxy_url = f"http://{ip}:{port}"
    try:
        r = requests.get(
            VALIDATE_URL,
            proxies={"http": proxy_url, "https": proxy_url},
            timeout=VALIDATE_TIMEOUT,
            headers=HEADERS,
        )
        return r.status_code < 500
    except Exception:
        return False


def validate_proxies(proxies, log_fn=print, stop_event=None):
    """
    Filter a raw proxy list down to only live ones using parallel HTTP checks.
    Uses VALIDATE_WORKERS threads so 6000+ proxies finish in ~2-3 minutes
    instead of hours.
    """
    total = len(proxies)
    log_fn(f"[VALIDATE] Testing {total} proxies dengan {VALIDATE_WORKERS} thread paralel...")

    alive      = []
    dead_count = 0
    checked    = 0
    lock       = __import__('threading').Lock()

    def _task(ip, port):
        nonlocal dead_count, checked
        if stop_event and stop_event.is_set():
            return None
        ok = _check_proxy(ip, port)
        with lock:
            checked += 1
            if ok:
                alive.append((ip, port))
            else:
                dead_count += 1
            # log progress every 500 proxies
            if checked % 500 == 0 or checked == total:
                log_fn(
                    f"[VALIDATE] Progress: {checked}/{total} | "
                    f"✅ Hidup: {len(alive)} | ❌ Mati: {dead_count}"
                )
        return ok

    with ThreadPoolExecutor(max_workers=VALIDATE_WORKERS) as exe:
        futures = {exe.submit(_task, ip, port): (ip, port) for ip, port in proxies}
        for f in as_completed(futures):
            if stop_event and stop_event.is_set():
                exe.shutdown(wait=False, cancel_futures=True)
                break
            f.result()  # surface any unexpected exceptions

    log_fn(
        f"[VALIDATE] Selesai — {len(alive)} proxy hidup dari {total} total "
        f"({dead_count} proxy mati dihapus)"
    )
    return alive


# ── Browser visitor ───────────────────────────────────────────────────────────

def visit_with_proxy(ip, port, target_url, timeout, stay_time):
    """Open Firefox headless through the given proxy and visit target_url."""
    options = Options()
    options.add_argument("--headless")
    options.set_preference("network.proxy.type",      1)
    options.set_preference("network.proxy.http",      ip)
    options.set_preference("network.proxy.http_port", port)
    options.set_preference("network.proxy.ssl",       ip)
    options.set_preference("network.proxy.ssl_port",  port)
    options.set_preference("network.proxy.ftp",       ip)
    options.set_preference("network.proxy.ftp_port",  port)

    # Redirect geckodriver log to /dev/null → fixes version-mismatch noise
    service = Service(log_output=subprocess.DEVNULL)

    driver = None
    try:
        driver = webdriver.Firefox(options=options, service=service)
        driver.set_page_load_timeout(timeout)
        driver.get(target_url)
        time.sleep(stay_time)
        driver.quit()
        return True
    except Exception:
        try:
            if driver:
                driver.quit()
        except Exception:
            pass
        return False


# ── Main loop ─────────────────────────────────────────────────────────────────

def run_bot(target_url=DEFAULT_TARGET, timeout=DEFAULT_TIMEOUT,
            stay_time=DEFAULT_STAY_TIME, log_fn=print,
            stop_event=None, stats=None):
    if stats is None:
        stats = {}
    stats.update({'tried': 0, 'success': 0, 'failed': 0,
                  'running': True, 'round': 0, 'current_proxy': '-'})

    while not (stop_event and stop_event.is_set()):
        stats['round'] += 1
        log_fn(f"[ROUND {stats['round']}] Mengumpulkan proxy dari semua sumber...")

        raw_proxies = fetch_all_proxies(log_fn)
        log_fn(f"[INFO] {len(raw_proxies)} proxy unik ditemukan — mulai validasi cepat...")

        # ── Step 1: filter dead proxies via fast HTTP check ───────────────
        live_proxies = validate_proxies(raw_proxies, log_fn, stop_event)

        if not live_proxies:
            log_fn("[WARN] Tidak ada proxy hidup ditemukan, langsung ke round berikutnya...")
            continue

        log_fn(f"[INFO] {len(live_proxies)} proxy hidup siap digunakan untuk round {stats['round']}")

        # ── Step 2: use only live proxies with Selenium ───────────────────
        for ip, port in live_proxies:
            if stop_event and stop_event.is_set():
                break
            proxy_str = f"{ip}:{port}"
            stats['tried']        += 1
            stats['current_proxy'] = proxy_str
            log_fn(f"[TRY] {proxy_str}")
            ok = visit_with_proxy(ip, port, target_url, timeout, stay_time)
            if ok:
                stats['success'] += 1
                log_fn(f"[OK] {proxy_str} ✓")
            else:
                stats['failed'] += 1
                log_fn(f"[FAIL] {proxy_str}")

        if not (stop_event and stop_event.is_set()):
            log_fn(f"[SLEEP] Round {stats['round']} selesai — tidur 10s")
            for _ in range(10):
                if stop_event and stop_event.is_set():
                    break
                time.sleep(1)

    stats['running']       = False
    stats['current_proxy'] = '-'
    log_fn("[STOPPED] Bot berhenti.")
