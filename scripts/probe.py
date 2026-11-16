import re, sys, urllib.request
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36", "Accept-Language": "en-IN,en;q=0.9", "Accept": "text/html,application/xhtml+xml"}
URLS = ["https://dhan.co/commodity/aluminium-futures-summary/", "https://www.indmoney.com/commodities/futures/aluminium", "https://mcxlive.org/aluminium/", "https://groww.in/commodities/futures/mcx_aluminium", "https://www.5paisa.com/commodity-trading/mcx-aluminium-price"]
PATS = [r"__NEXT_DATA__", r"(?i)last ?updated", r"(?i)as on", r"(?i)\"ltp\"", r"(?i)lastPrice|last_price|lastTradedPrice", r"(?i)prev(ious)?[ _.]?close", r"(?i)expiry", r"(?i)dayHigh|\"high\"", r"32\d\.\d", r"33\d\.\d"]
for u in URLS:
    print("=====", u)
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30)
        t = r.read().decode("utf-8", "replace")
    except Exception as e:
        print("ERR", repr(e)); continue
    print("status", r.status, "len", len(t))
    for p in PATS:
        ms = list(re.finditer(p, t))
        print("--", p, len(ms))
        for m in ms[:4]:
            a = max(0, m.start() - 140); print("   ", repr(t[a:m.end() + 220]))
