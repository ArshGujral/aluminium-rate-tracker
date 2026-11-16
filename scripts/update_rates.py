#!/usr/bin/env python3
"""Fetch the MCX aluminium (near-month futures) rate and record it in data.json.

Run by .github/workflows/update-rates.yml. Two kinds of run, chosen from the time and the pages themselves:

  postclose  the market is shut: record the finished session's last traded price with its day low and high.
  official   the market is open: the pages show the previous session's official close, so set that
             session's rate to it. Today's price so far is also recorded, marked "live".

A rate is written only when at least two sources agree. Nothing is ever estimated.
"""
import datetime as dt
import json
import os
import re
import sys
import urllib.request

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data.json")
UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
}
MON = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
MON_NAME = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def log(*a):
    print(*a, flush=True)


def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
            return r.read().decode("utf-8", "replace")
    except Exception as e:  # a source being down is expected now and then
        log("  fetch failed:", url, repr(e))
        return None


def walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v)


def next_data(html):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    return json.loads(m.group(1)) if m else None


def num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and 150 < v < 600 else None


def clock(h, mi, ap):
    h = int(h)
    if ap.upper() == "PM" and h < 12:
        h += 12
    if ap.upper() == "AM" and h == 12:
        h = 0
    return h, int(mi)


def dhan():
    html = get("https://dhan.co/commodity/aluminium-futures-summary/")
    if not html:
        return None
    m = re.search(r"as on(?:<!-- -->|\s)*(\d{1,2}) ([A-Za-z]{3}) (\d{4})(?:<!-- -->|\s)*at(?:<!-- -->|\s)*(\d{1,2}):(\d{2}) ([AP]M)", html)
    nd = next_data(html)
    if not m or not nd:
        return None
    h, mi = clock(m.group(4), m.group(5), m.group(6))
    stamp = dt.datetime(int(m.group(3)), MON[m.group(2).lower()], int(m.group(1)), h, mi, tzinfo=IST)
    best = None
    for d in walk(nd):
        if d.get("sym") != "ALUMINIUM" or num(d.get("Ltp")) is None:
            continue
        t = re.fullmatch(r"ALUMINIUM(\d{2})([A-Za-z]{3})-FUT", str(d.get("t_sym", "")))
        if not t:
            continue
        mon, day = MON[t.group(2).lower()], int(t.group(1))
        year = stamp.year + (1 if mon < stamp.month else 0)
        exp = dt.date(year, mon, day)
        if exp >= stamp.date() and (best is None or exp < best[0]):
            best = (exp, d)
    if not best:
        return None
    exp, d = best
    return {"name": "Dhan", "stamp": stamp, "ltp": num(d.get("Ltp")), "high": num(d.get("hg")), "low": num(d.get("lo")),
            "prev": num(d.get("cl")), "contract": "%d %s %d" % (exp.day, MON_NAME[exp.month - 1], exp.year)}


def groww():
    html = get("https://groww.in/commodities/futures/mcx_aluminium")
    nd = next_data(html) if html else None
    if not nd:
        return None
    for d in walk(nd):
        lp = d.get("livePriceDetails")
        if isinstance(lp, dict) and num(lp.get("ltp")) is not None and lp.get("tsInMillis"):
            ts = float(lp["tsInMillis"])
            if ts > 1e11:
                ts /= 1000.0
            return {"name": "Groww", "stamp": dt.datetime.fromtimestamp(ts, IST), "ltp": num(lp.get("ltp")),
                    "high": num(lp.get("high")), "low": num(lp.get("low")), "prev": num(lp.get("close")), "contract": None}
    return None


def mcxlive():
    html = get("https://mcxlive.org/aluminium/")
    if not html:
        return None
    a = re.search(r"As on \w+, \d{1,2} [A-Za-z]{3} (\d{4})", html)
    lt = re.search(r"Last Trade on (\d{1,2}) ([A-Za-z]{3}) (\d{1,2}):(\d{2}) ([AP]M)", html)
    p = re.search(r'class="main-change[^"]*">(?:\s*<i[^>]*></i>)?\s*([\d.]+)\s*</td>', html)
    if not (a and lt and p):
        return None
    h, mi = clock(lt.group(3), lt.group(4), lt.group(5))
    stamp = dt.datetime(int(a.group(1)), MON[lt.group(2).lower()], int(lt.group(1)), h % 24, mi, tzinfo=IST)
    hl = re.search(r'<td class="main-sub">\s*([\d.]+)</td>\s*<td class="main-sub">\s*([\d.]+)</td>', html)
    c = re.search(r'<h2 class="main-head">MCX Aluminium (\d{1,2} [A-Za-z]{3} \d{4})</h2>', html)
    return {"name": "MCX Live", "stamp": stamp, "ltp": num(float(p.group(1))), "high": num(float(hl.group(1))) if hl else None,
            "low": num(float(hl.group(2))) if hl else None, "prev": None, "contract": c.group(1) if c else None}


def fivepaisa_prev(today):
    """5paisa's previous close, used only as one more vote for the official close. None unless the page is dated today."""
    html = get("https://www.5paisa.com/commodity-trading/mcx-aluminium-price")
    if not html:
        return None
    d = re.search(r"As on (\d{1,2}) ([A-Za-z]+),? (\d{4})", html)
    p = re.search(r'id="prev_close"[^>]*>\s*([\d.]+)\s*<', html)
    if not (d and p) or d.group(2)[:3].lower() not in MON:
        return None
    if dt.date(int(d.group(3)), MON[d.group(2)[:3].lower()], int(d.group(1))) != today:
        return None
    return num(float(p.group(1)))


def agree(values, tol):
    """The first value that at least one other value matches within tol, else None."""
    for i, v in enumerate(values):
        if any(j != i and abs(v - w) <= tol for j, w in enumerate(values)):
            return v
    return None


def main():
    forced = os.environ.get("MODE", "").strip()
    dry = os.environ.get("DRY_RUN", "").strip().lower() == "true"
    now = dt.datetime.now(IST)
    today = now.date()
    srcs = []
    for fn in (dhan, groww, mcxlive):
        try:
            s = fn()
        except Exception as e:
            log("  parse failed:", fn.__name__, repr(e))
            s = None
        if s and s["ltp"] is not None:
            srcs.append(s)
            log("  %-8s ltp %.2f  high %s  low %s  prev close %s  at %s  contract %s" % (
                s["name"], s["ltp"], s["high"], s["low"], s["prev"], s["stamp"].strftime("%d %b %Y %H:%M"), s["contract"]))
    if len(srcs) < 2:
        log("Fewer than two sources answered. Nothing written.")
        return 1

    main_src = srcs[0]
    trade_date = main_src["stamp"].date()
    srcs = [s for s in srcs if s["stamp"].date() == trade_date]
    if len(srcs) < 2:
        log("Sources disagree on the trading date. Nothing written.")
        return 1
    contract = next((s["contract"] for s in srcs if s["name"] == "MCX Live" and s["contract"]), None) or main_src["contract"] or ""

    open_now = now.weekday() < 5 and dt.time(9, 0) <= now.time() < dt.time(23, 30) and trade_date == today
    mode = forced or ("official" if open_now else "postclose")
    log("Now %s IST. Last trade %s. Mode: %s%s" % (now.strftime("%d %b %Y %H:%M"), main_src["stamp"].strftime("%d %b %H:%M"), mode, " (dry run)" if dry else ""))

    with open(DATA, encoding="utf-8") as f:
        data = json.load(f)
    before = json.dumps(data["rates"], sort_keys=True) + str(data.get("updatedAt"))
    rates = sorted(data["rates"], key=lambda r: r["date"])
    by_date = {r["date"]: r for r in rates}

    def sane(d, v):
        earlier = [r for r in rates if r["date"] < d]
        return not earlier or abs(v - earlier[-1]["mcx"]) / earlier[-1]["mcx"] <= 0.12

    if mode == "official":
        prevs = [s["prev"] for s in srcs if s["prev"] is not None]
        try:
            fp = fivepaisa_prev(today)
        except Exception as e:
            log("  parse failed: 5paisa", repr(e))
            fp = None
        if fp is not None:
            log("  5paisa   prev close %.2f" % fp)
            prevs.append(fp)
        pc = agree(prevs, 0.05)
        if pc is None:
            log("Previous close not confirmed by two sources. Nothing written.")
            return 1
        earlier = [r for r in rates if r["date"] < today.isoformat()]
        last = earlier[-1] if earlier else None
        if last and (today - dt.date.fromisoformat(last["date"])).days <= 5 and abs(last["mcx"] - pc) <= 1.0:
            if abs(last["mcx"] - pc) > 0.004 or last.get("closeType") != "official":
                log("Official close for %s: %.2f (was %.2f)" % (last["date"], pc, last["mcx"]))
                last["mcx"], last["closeType"] = pc, "official"
        else:
            # The post-close run missed the last session. Its close is known; date it to the previous weekday.
            d = today - dt.timedelta(days=1)
            while d.weekday() >= 5:
                d -= dt.timedelta(days=1)
            ds = d.isoformat()
            if ds not in by_date and sane(ds, pc):
                log("Adding missed session %s: %.2f" % (ds, pc))
                rates.append({"date": ds, "mcx": pc, "contract": contract, "source": main_src["name"], "closeType": "official"})
            else:
                log("Previous close %.2f does not fit the log; nothing changed." % pc)
        # Today's price so far, from whichever agreeing source traded most recently. The post-close run replaces it.
        live = agree([s["ltp"] for s in srcs], 1.0)
        if live is not None and trade_date == today:
            fresh = max((s for s in srcs if abs(s["ltp"] - live) <= 1.0), key=lambda s: s["stamp"])
            ts, v, low, high = today.isoformat(), fresh["ltp"], fresh["low"], fresh["high"]
            r = by_date.get(ts)
            if sane(ts, v) and (r is None or r.get("closeType") == "live"):
                if r is None:
                    r = {"date": ts}
                    rates.append(r)
                r.update({"mcx": v, "contract": contract, "source": fresh["name"], "closeType": "live", "asOf": fresh["stamp"].strftime("%H:%M")})
                if low is not None and high is not None and low <= v <= high:
                    r["low"], r["high"] = low, high
                log("Live %s: %.2f as of %s" % (ts, v, r["asOf"]))
    else:
        ltp = agree([s["ltp"] for s in srcs], 0.3 if not forced else 1.0)
        if ltp is None:
            log("Last traded price not confirmed by two sources. Nothing written.")
            return 1
        if not forced and (now - main_src["stamp"]) < dt.timedelta(minutes=10):
            log("The market still looks open. Nothing written.")
            return 0
        if (today - trade_date).days > 4:
            log("Last trade is more than 4 days old. Nothing written.")
            return 1
        ds = trade_date.isoformat()
        low, high = main_src["low"], main_src["high"]
        if low is None or high is None or not (low <= ltp <= high):
            low = high = None
        if not sane(ds, ltp):
            log("Price %.2f is more than 12%% away from the previous day. Nothing written." % ltp)
            return 1
        r = by_date.get(ds)
        if r is None:
            r = {"date": ds, "mcx": ltp, "contract": contract, "source": main_src["name"], "closeType": "last"}
            rates.append(r)
            log("Adding %s: %.2f" % (ds, ltp))
        elif r.get("closeType") != "official" and (abs(r["mcx"] - ltp) > 0.004 or r.get("closeType") == "live"):
            log("Closing %s: %.2f (was %.2f)" % (ds, ltp, r["mcx"]))
            r["mcx"], r["closeType"], r["source"] = ltp, "last", main_src["name"]
            r.pop("asOf", None)
        if low is not None and (r.get("low") != low or r.get("high") != high) and low <= r["mcx"] <= high:
            r["low"], r["high"] = low, high

    data["rates"] = sorted(rates, key=lambda r: r["date"])
    data["updatedAt"] = today.isoformat()
    data["updatedTime"] = now.strftime("%H:%M")
    if json.dumps(data["rates"], sort_keys=True) + str(data.get("updatedAt")) == before:
        log("No change.")
        return 0
    if dry:
        log("Dry run. Would write:", json.dumps(data["rates"][-3:]))
        return 0
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.write("\n")
    log("data.json written. Latest:", json.dumps(data["rates"][-1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
