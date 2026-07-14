import random
import urllib.parse
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
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ── Suppress geckodriver version-mismatch warning ─────────────────────────────
logging.getLogger("selenium.webdriver.common.service").setLevel(logging.ERROR)
logging.getLogger("selenium").setLevel(logging.ERROR)

DEFAULT_TARGET    = "https://dramacina--dzeckart.replit.app"
DEFAULT_TIMEOUT   = 30
DEFAULT_STAY_TIME = 25   # Naik dari 5 → iklan perlu waktu load & terlihat

# ── Organic search queries (Google referrer) ──────────────────────────────────
SEARCH_QUERIES = [
    "nonton drama korea online gratis",
    "drama korea terbaru 2024 subtitle indonesia",
    "watch korean drama free streaming",
    "nonton drama china sub indo",
    "drama romantis korea terbaru",
    "streaming drama korea gratis",
    "nonton film drama online",
    "korean drama 2024 full episode",
    "drama asia terbaru sub indo",
    "nonton drama online subtitle",
]

# ── Proxy validation settings ─────────────────────────────────────────────────
VALIDATE_TIMEOUT = 8
VALIDATE_WORKERS = 50
VALIDATE_URL     = "http://httpbin.org/ip"

# ── Realistic User-Agent pool ──────────────────────────────────────────────────
USER_AGENTS = [
    # Chrome Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    # Chrome macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    # Firefox Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    # Firefox Linux
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    # Safari macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    # Edge Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    # Mobile Chrome Android
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.82 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    # Mobile Safari iPhone
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Mobile/15E148 Safari/604.1",
]

# ── Realistic screen resolutions (width, height) ───────────────────────────────
SCREEN_SIZES = [
    (1920, 1080), (1366, 768), (1536, 864), (1440, 900),
    (1280, 720),  (1600, 900), (2560, 1440), (1280, 800),
    # Mobile portrait
    (390, 844), (375, 812), (414, 896), (360, 800),
]

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
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
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


# ── Human-like helpers ────────────────────────────────────────────────────────

def _human_delay(lo=0.3, hi=1.2):
    """Short random pause to mimic human reaction time."""
    time.sleep(random.uniform(lo, hi))


def _set_organic_referrer(driver, timeout):
    """
    Singgah sebentar ke Google Search sebelum ke target.
    Ini membuat HTTP Referer = google.com → traffic terlihat organik
    bagi ad network (lebih dipercaya, CTR lebih tinggi).
    """
    query = urllib.parse.quote(random.choice(SEARCH_QUERIES))
    try:
        driver.get(f"https://www.google.com/search?q={query}&hl=en")
        # Tunggu halaman Google muncul
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except Exception:
            pass
        # Baca sebentar seperti orang melihat hasil pencarian
        time.sleep(random.uniform(2.0, 4.0))
    except Exception:
        pass  # Kalau Google tidak bisa diakses via proxy, lanjut saja


def _visit_inner_pages(driver, base_url, log_fn):
    """
    Setelah halaman utama, navigasi ke 1-2 halaman dalam (internal links).
    Meningkatkan pageview depth → lebih banyak ad impression per sesi.
    """
    try:
        links = driver.find_elements(By.CSS_SELECTOR, "a[href]")
        internal = []
        for lnk in links[:40]:
            try:
                href = lnk.get_attribute("href") or ""
                # Hanya link internal, bukan anchor/javascript, panjang wajar
                if (href.startswith(base_url)
                        and href.rstrip("/") != base_url.rstrip("/")
                        and len(href) < 300
                        and "#" not in href
                        and "javascript" not in href):
                    internal.append(href)
            except Exception:
                continue

        if not internal:
            return

        # Kunjungi 1-2 halaman dalam secara acak
        picks = random.sample(internal, min(random.randint(1, 2), len(internal)))
        for page_url in picks:
            try:
                driver.get(page_url)
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.TAG_NAME, "body"))
                    )
                except Exception:
                    pass
                _human_delay(1.0, 2.5)
                # Baca halaman dalam selama 10-18 detik
                _read_page_naturally(driver, random.uniform(10, 18))
                log_fn(f"[INNER] {page_url[:70]}")
            except Exception:
                continue
    except Exception:
        pass


def _smooth_scroll(driver, target_y, steps=6):
    """
    Scroll to target_y in small increments with random pauses,
    mimicking a real user scrolling with a mouse wheel or trackpad.
    """
    current = driver.execute_script("return window.pageYOffset;")
    delta   = target_y - current
    for i in range(1, steps + 1):
        pos = current + (delta * i / steps) + random.uniform(-10, 10)
        driver.execute_script(f"window.scrollTo(0, {max(0, pos)});")
        time.sleep(random.uniform(0.05, 0.18))


def _move_mouse_naturally(actions, driver, target_el=None):
    """
    Move the mouse in a curved/staggered path toward an element (or random point).
    Uses 2-3 intermediate waypoints, mimicking natural hand movement.
    """
    try:
        body = driver.find_element(By.TAG_NAME, "body")
        vw   = driver.execute_script("return window.innerWidth;")
        vh   = driver.execute_script("return window.innerHeight;")

        # Pick 2 random waypoints
        for _ in range(random.randint(1, 3)):
            wx = random.randint(50, max(51, vw - 50))
            wy = random.randint(50, max(51, vh - 50))
            ActionChains(driver).move_to_element_with_offset(
                body, wx - vw // 2, wy - vh // 2
            ).perform()
            time.sleep(random.uniform(0.05, 0.15))

        if target_el:
            ActionChains(driver).move_to_element(target_el).perform()
            time.sleep(random.uniform(0.1, 0.3))
    except Exception:
        pass


def _read_page_naturally(driver, stay_time):
    """
    Simulasi membaca halaman seperti manusia:
    - Scroll ke 100% halaman (penting: lazy-loaded ads HARUS di-trigger)
    - Jeda di setiap posisi scroll (memberi waktu iklan render)
    - Gerakan mouse sambil membaca
    - Kadang scroll balik ke atas (natural curiosity)
    - Total waktu ≈ stay_time detik
    """
    try:
        page_h     = driver.execute_script("return document.body.scrollHeight;")
        viewport_h = driver.execute_script("return window.innerHeight;")
        vw         = driver.execute_script("return window.innerWidth;")

        # Selalu scroll ke 100% halaman agar semua ad slot (termasuk yang
        # lazy-loaded di bawah fold) sempat load dan terhitung impression.
        max_scroll = page_h

        # Bangun path scroll: 6-10 titik berhenti
        step = max(100, max_scroll // 10)
        candidates = list(range(step, max_scroll + 1, step))
        if not candidates:
            candidates = [max_scroll]
        n_stops = min(random.randint(6, 10), len(candidates))
        stops = sorted(random.sample(candidates, n_stops))
        # Pastikan titik terakhir adalah dasar halaman
        if stops[-1] < max_scroll:
            stops.append(max_scroll)

        elapsed = 0.0
        body = driver.find_element(By.TAG_NAME, "body")

        for stop in stops:
            if elapsed >= stay_time:
                break
            _smooth_scroll(driver, stop)

            # Jeda di posisi ini — beri waktu iklan lazy-load
            pause = random.uniform(1.2, 3.5)
            elapsed += pause
            time.sleep(pause)

            # Gerakan mouse sambil "membaca"
            if random.random() < 0.6:
                try:
                    mx = random.randint(50, max(51, vw - 50))
                    my = random.randint(50, max(51, viewport_h - 50))
                    ActionChains(driver).move_to_element_with_offset(
                        body, mx - vw // 2, my - viewport_h // 2
                    ).pause(random.uniform(0.1, 0.3)).perform()
                except Exception:
                    pass

            # Hover atas link/heading (tampak alami)
            if random.random() < 0.4:
                try:
                    candidates_el = driver.find_elements(
                        By.CSS_SELECTOR, "a, button, h2, h3, h4, p, img")
                    if candidates_el:
                        el = random.choice(candidates_el[:15])
                        driver.execute_script(
                            "arguments[0].scrollIntoView({block:'nearest'});", el)
                        time.sleep(random.uniform(0.05, 0.2))
                        ActionChains(driver).move_to_element(el).pause(
                            random.uniform(0.2, 0.6)).perform()
                except Exception:
                    pass

            # Scroll balik sedikit (re-reading behaviour)
            if random.random() < 0.3:
                back = max(0, stop - random.randint(100, 350))
                _smooth_scroll(driver, back)
                back_pause = random.uniform(0.5, 1.2)
                elapsed += back_pause
                time.sleep(back_pause)

        # Isi sisa stay_time di posisi bawah halaman
        remaining = stay_time - elapsed
        if remaining > 0:
            time.sleep(remaining)

    except Exception:
        time.sleep(stay_time)


# ── Browser visitor ───────────────────────────────────────────────────────────

def visit_with_proxy(ip, port, target_url, timeout, stay_time, log_fn=print):
    """
    Open Firefox headless through the given proxy and visit target_url,
    behaving like a real human user:
      - Random user agent + screen size
      - Natural mouse movement (ActionChains waypoints)
      - Smooth, chunked scrolling with pauses
      - Hover over page elements (links, headings)
      - Variable stay time
    """
    ua     = random.choice(USER_AGENTS)
    width, height = random.choice(SCREEN_SIZES)
    is_mobile = width < 500

    options = Options()
    options.add_argument("--headless")
    options.add_argument(f"--width={width}")
    options.add_argument(f"--height={height}")

    # Identity
    options.set_preference("general.useragent.override", ua)
    options.set_preference("intl.accept_languages",
                           random.choice(["en-US,en;q=0.9",
                                          "en-GB,en;q=0.9",
                                          "id-ID,id;q=0.9,en;q=0.8"]))
    # Disable WebRTC IP leak (hides real IP behind proxy)
    options.set_preference("media.peerconnection.enabled", False)
    # Disable geolocation prompt
    options.set_preference("geo.enabled", False)
    options.set_preference("geo.provider.use_corelocation", False)
    # Reduce fingerprinting
    options.set_preference("privacy.resistFingerprinting", False)
    options.set_preference("dom.webdriver.enabled", False)

    # Proxy
    options.set_preference("network.proxy.type",      1)
    options.set_preference("network.proxy.http",      ip)
    options.set_preference("network.proxy.http_port", port)
    options.set_preference("network.proxy.ssl",       ip)
    options.set_preference("network.proxy.ssl_port",  port)
    options.set_preference("network.proxy.ftp",       ip)
    options.set_preference("network.proxy.ftp_port",  port)

    service = Service(log_output=subprocess.DEVNULL)
    driver  = None
    try:
        driver = webdriver.Firefox(options=options, service=service)
        driver.set_page_load_timeout(timeout)

        # ── [1] Organic referrer: singgah Google dulu ─────────────────────
        # Traffic yang datang dari Google dinilai lebih berkualitas oleh
        # ad network → lebih dipercaya → potensi CTR & CPM lebih tinggi.
        _set_organic_referrer(driver, timeout)
        log_fn(f"[REF] Google referrer set")

        # ── [2] Navigate ke target ────────────────────────────────────────
        driver.get(target_url)

        try:
            WebDriverWait(driver, min(timeout, 15)).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except Exception:
            pass

        # Jeda awal (manusia butuh waktu orientasi saat halaman baru terbuka)
        _human_delay(1.5, 3.5)

        # ── [3] Mouse masuk dari tepi layar ──────────────────────────────
        try:
            body = driver.find_element(By.TAG_NAME, "body")
            vw   = driver.execute_script("return window.innerWidth;")
            vh   = driver.execute_script("return window.innerHeight;")

            ActionChains(driver).move_to_element_with_offset(
                body,
                random.randint(-vw // 3, -vw // 6),
                random.randint(-vh // 3, -vh // 6),
            ).perform()
            _human_delay(0.1, 0.4)

            ActionChains(driver).move_to_element_with_offset(
                body,
                random.randint(-vw // 4, vw // 4),
                random.randint(-vh // 4, vh // 4),
            ).pause(random.uniform(0.1, 0.4)).perform()
        except Exception:
            pass

        # ── [4] Baca halaman utama (scroll 100%, jeda panjang) ────────────
        # stay_time default 25s + variasi acak → iklan punya cukup waktu
        # untuk load, render, dan terhitung sebagai impression yang valid.
        actual_stay = stay_time + random.uniform(2, 8)
        _read_page_naturally(driver, actual_stay)

        # ── [5] Multi-page: kunjungi 1-2 halaman dalam ────────────────────
        # Meningkatkan pageview depth per sesi → lebih banyak ad impression
        # dan sinyal engagement yang lebih kuat ke ad network.
        _visit_inner_pages(driver, target_url, log_fn)

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

        # ── Pipeline: validator feeds queue, visitor consumes immediately ─
        live_queue      = _queue.Queue(maxsize=300)
        validation_done = threading.Event()

        _lock    = threading.Lock()
        _alive   = [0]
        _dead    = [0]
        _checked = [0]

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
                            f"Hidup: {_alive[0]} | Mati: {_dead[0]}"
                        )

            with ThreadPoolExecutor(max_workers=VALIDATE_WORKERS) as exe:
                fts = [exe.submit(_check_and_push, ip, port) for ip, port in raw_proxies]
                for f in as_completed(fts):
                    if stop_event and stop_event.is_set():
                        exe.shutdown(wait=False, cancel_futures=True)
                        break
                    f.result()

            log_fn(f"[VALIDATE] Selesai — {_alive[0]} hidup, {_dead[0]} mati dihapus")
            validation_done.set()

        val_thread = threading.Thread(target=_validation_worker, daemon=True)
        val_thread.start()

        log_fn("[INFO] Menunggu proxy hidup pertama lalu langsung mulai kunjungan...")

        while not (stop_event and stop_event.is_set()):
            try:
                ip, port = live_queue.get(timeout=1)
            except _queue.Empty:
                if not validation_done.is_set():
                    continue
                if live_queue.empty():
                    break
                continue

            proxy_str = f"{ip}:{port}"
            stats['tried']        += 1
            stats['current_proxy'] = proxy_str

            # Pick random UA label for log (mobile vs desktop)
            ua_type = "Mobile" if random.random() < 0.3 else "Desktop"
            w, h    = random.choice(SCREEN_SIZES)
            log_fn(f"[TRY] {proxy_str} | {ua_type} | {w}x{h}")

            ok = visit_with_proxy(ip, port, target_url, timeout, stay_time, log_fn)
            if ok:
                stats['success'] += 1
                log_fn(f"[OK] {proxy_str} — kunjungan selesai")
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
