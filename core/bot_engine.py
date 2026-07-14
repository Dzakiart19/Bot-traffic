import random
import requests
from bs4 import BeautifulSoup
import time
import threading
from selenium import webdriver
from selenium.webdriver.firefox.options import Options

DEFAULT_TARGET   = "https://dramacina--dzeckart.replit.app"
DEFAULT_TIMEOUT  = 30
DEFAULT_STAY_TIME = 5

# ── Proxy sources ─────────────────────────────────────────────────────────────
# API sources: return plain-text "ip:port" per line — far more reliable than
# HTML scraping because they don't break when the site redesigns its layout.
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

# HTML-scraping fallback (still works but fewer proxies)
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
            # strip optional protocol prefix
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
    """
    Collect proxies from all sources (API-first, HTML as fallback).
    Returns a deduplicated list of (ip, port) tuples.
    """
    seen   = set()
    result = []

    # 1. API sources
    for name, url in API_SOURCES:
        for item in _fetch_api(name, url, log_fn):
            if item not in seen:
                seen.add(item)
                result.append(item)

    # 2. HTML fallback if APIs gave fewer than expected
    if len(result) < 500:
        log_fn("[INFO] API sources low — trying HTML fallback sources")
        for url in HTML_SOURCES:
            for item in _fetch_html(url, log_fn):
                if item not in seen:
                    seen.add(item)
                    result.append(item)

    random.shuffle(result)
    return result


# ── Browser visitor ───────────────────────────────────────────────────────────

def visit_with_proxy(ip, port, target_url, timeout, stay_time):
    options = Options()
    options.add_argument("--headless")
    options.set_preference("network.proxy.type", 1)
    options.set_preference("network.proxy.http",      ip)
    options.set_preference("network.proxy.http_port", port)
    options.set_preference("network.proxy.ssl",       ip)
    options.set_preference("network.proxy.ssl_port",  port)
    options.set_preference("network.proxy.ftp",       ip)
    options.set_preference("network.proxy.ftp_port",  port)
    driver = None
    try:
        driver = webdriver.Firefox(options=options)
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
        log_fn(f"[ROUND {stats['round']}] Collecting proxies from all sources...")

        proxies = fetch_all_proxies(log_fn)
        log_fn(f"[INFO] {len(proxies)} unique proxies ready for round {stats['round']}")

        for ip, port in proxies:
            if stop_event and stop_event.is_set():
                break
            proxy_str = f"{ip}:{port}"
            stats['tried']         += 1
            stats['current_proxy']  = proxy_str
            log_fn(f"[TRY] {proxy_str}")
            ok = visit_with_proxy(ip, port, target_url, timeout, stay_time)
            if ok:
                stats['success'] += 1
                log_fn(f"[OK] {proxy_str} ✓")
            else:
                stats['failed'] += 1
                log_fn(f"[FAIL] {proxy_str}")

        if not (stop_event and stop_event.is_set()):
            log_fn(f"[SLEEP] Round {stats['round']} complete — sleeping 10s")
            for _ in range(10):
                if stop_event and stop_event.is_set():
                    break
                time.sleep(1)

    stats['running']        = False
    stats['current_proxy']  = '-'
    log_fn("[STOPPED] Bot stopped.")
