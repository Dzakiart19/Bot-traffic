# Bot — Web Traffic & YouTube View Generator

An open-source Python bot that uses Selenium with Firefox (headless) and public proxy lists to generate website traffic.

**Original author:** [tuhin1729](https://github.com/tuhin1729)

## Stack

- **Language:** Python 3
- **Browser automation:** Selenium + Firefox (headless) + Geckodriver
- **Proxy scraping:** requests + BeautifulSoup4

## How to Run

This is an **interactive command-line tool**. Open the Shell tab and run:

```bash
python3 Bot.py
```

You will be prompted for:
1. **Target URL** — the website you want to send traffic to (e.g. `https://example.com`)
2. **Timeout** — page load timeout in seconds (recommended: 100)
3. **Stay time** — how long to stay on the page per visit (in seconds)

The bot will then scrape public proxy lists and cycle through them, opening Firefox (headless) via each proxy to visit your target URL.

## Notes

- Some proxies may be dead or slow — this is expected.
- The target website may detect and block bot traffic.
- For educational purposes only.

## User Preferences

<!-- Add user preferences here -->
