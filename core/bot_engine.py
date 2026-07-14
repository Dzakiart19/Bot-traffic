import random
import requests
from bs4 import BeautifulSoup
import time
import logging
import subprocess
import threading
import queue as _queue
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
VALIDATE_TIMEOUT = 8    # seconds per HTTP check
VALIDATE_WORKERS = 50   # parallel threads for validation
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
    """Quick HTTP connectivity check. Returns True if proxy is alive."""
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


# ── Browser visitor ───────────────────────────────────────────────────────────

def visit_with_proxy(ip, port, target_url, timeout, stay_time):
    options = Options()
    options.add_argument("--headless")
    options.set_preference("network.proxy.type",      1)
    options.set_preference("network.proxy.http",      ip)
    options.set_preference("network.proxy.http_port", port)
    options.set_preference("network.proxy.ssl",       ip)
    options.set_preference("network.proxy.ssl_port",  port)
    options.set_preference("network.proxy.ftp",       ip)
    options.set_preference("network.proxy.ftp_port",  port)

    # Redirect geckodriver log to /dev/null — fixes version-mismatch noise
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


# ── Main loop (pipeline: validate + visit run in parallel) ────────────────────

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
        total = len(raw_proxies)
        log_fn(
            f"[INFO] {total} proxy unik ditemukan — "
            f"pipeline validasi + kunjungan dimulai bersamaan..."
        )

        # ── Pipeline queue: validator → Selenium visitor ──────────────────
        # Proxy yang sudah terbukti hidup langsung masuk antrian,
        # Selenium tidak perlu menunggu validasi 100% selesai.
        live_queue       = _queue.Queue(maxsize=300)
        validation_done  = threading.Event()

        # Shared counters (guarded by lock)
        _lock      = threading.Lock()
        _alive     = [0]
        _dead      = [0]
        _checked   = [0]

        # ── Producer: validate proxies, push live ones to queue ───────────
        def _validation_worker():
            def _check_and_push(ip, port):
                if stop_event and stop_event.is_set():
                    return
                ok = _check_proxy(ip, port)
                with _lock:
                    _checked[0] += 1
                    if ok:
                        _alive[0] += 1
                        live_queue.put((ip, port))
                    else:
                        _dead[0] += 1
                    c = _checked[0]
                    if c % 500 == 0 or c == total:
                        log_fn(
                            f"[VALIDATE] Progress: {c}/{total} | "
                            f"✅ Hidup: {_alive[0]} | ❌ Mati: {_dead[0]}"
                        )

            with ThreadPoolExecutor(max_workers=VALIDATE_WORKERS) as exe:
                fts = [exe.submit(_check_and_push, ip, port) for ip, port in raw_proxies]
                for f in as_completed(fts):
                    if stop_event and stop_event.is_set():
                        exe.shutdown(wait=False, cancel_futures=True)
                        break
                    f.result()

            log_fn(
                f"[VALIDATE] Selesai — {_alive[0]} hidup, {_dead[0]} mati dihapus"
            )
            validation_done.set()

        # Start validation in background
        val_thread = threading.Thread(target=_validation_worker, daemon=True)
        val_thread.start()

        log_fn("[INFO] Menunggu proxy hidup pertama lalu langsung mulai kunjungan...")

        # ── Consumer: visit with Selenium as live proxies arrive ──────────
        while not (stop_event and stop_event.is_set()):
            try:
                ip, port = live_queue.get(timeout=1)
            except _queue.Empty:
                # Keep waiting if validation is still running
                if not validation_done.is_set():
                    continue
                # Validation done and queue drained — round complete
                if live_queue.empty():
                    break
                continue

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

        val_thread.join(timeout=5)

        if not (stop_event and stop_event.is_set()):
            log_fn(f"[SLEEP] Round {stats['round']} selesai — tidur 10s")
            for _ in range(10):
                if stop_event and stop_event.is_set():
                    break
                time.sleep(1)

    stats['running']       = False
    stats['current_proxy'] = '-'
    log_fn("[STOPPED] Bot berhenti.")
