"""Indian trading calendar + market-section carry-forward for FINTRIX.

On days the Indian stock market is shut (weekends + NSE trading holidays) the
issue still publishes with that day's date: news refreshes as usual and the
market sections carry the last session's close, labelled with that date.
Holidays come from the NSE website's live holiday API; if NSE is unreachable,
the embedded official NSE circular for 2026 (NSE/CMTR/71775) is used instead.
"""

import json
import urllib.request
from datetime import datetime, timedelta

NSE_HOLIDAYS_EMBEDDED = {
    2026: {
        "01-26": "Republic Day", "03-03": "Holi", "03-26": "Shri Ram Navami",
        "03-31": "Shri Mahavir Jayanti", "04-03": "Good Friday",
        "04-14": "Dr. Baba Saheb Ambedkar Jayanti", "05-01": "Maharashtra Day",
        "05-28": "Bakri Id", "06-26": "Muharram", "09-14": "Ganesh Chaturthi",
        "10-02": "Mahatma Gandhi Jayanti", "10-20": "Dussehra",
        "11-10": "Diwali-Balipratipada",
        "11-24": "Prakash Gurpurb Sri Guru Nanak Dev", "12-25": "Christmas",
    },
}

_HOLIDAY_CACHE = {}


def _nse_holidays_live(year):
    """Trading holidays from NSE's own holiday API; raises on any problem."""
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
    opener.addheaders = [
        ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
        ("Accept-Language", "en-US,en;q=0.9"),
    ]
    opener.open("https://www.nseindia.com/", timeout=15).read()
    with opener.open("https://www.nseindia.com/api/holiday-master?type=trading",
                     timeout=15) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    blocks = [payload["CM"]] if isinstance(payload.get("CM"), list) else \
        [v for v in payload.values() if isinstance(v, list)]
    out = {}
    for row in blocks[0]:
        try:
            d = datetime.strptime(str(row.get("tradingDate", "")), "%d-%b-%Y").date()
        except (TypeError, ValueError):
            continue
        if d.year == year:
            out[d] = str(row.get("description") or "Trading holiday")
    if not out:
        raise RuntimeError("NSE holiday API returned no dates for %d" % year)
    return out


def nse_holidays(year):
    """{date: name}: live from NSE, else the embedded official list, else empty."""
    if year in _HOLIDAY_CACHE:
        return _HOLIDAY_CACHE[year]
    try:
        hol = _nse_holidays_live(year)
        print("  trading calendar: live NSE holiday list (%d holidays)" % len(hol))
    except Exception as e:
        emb = NSE_HOLIDAYS_EMBEDDED.get(year) or {}
        hol = {datetime.strptime("%d-%s" % (year, md), "%Y-%m-%d").date(): name
               for md, name in emb.items()}
        print("  trading calendar: NSE unreachable (%s) - embedded list: %d dates"
              % (e, len(hol)))
    _HOLIDAY_CACHE[year] = hol
    return hol


def indian_trading_day(d):
    """(True, "") on trading days, else (False, reason) for an IST date."""
    if d.weekday() >= 5:
        return False, "the weekend"
    name = nse_holidays(d.year).get(d)
    if name:
        return False, name
    return True, ""


On days the Indian stock market is shut (weekends + NSE trading holidays) the
issue still publishes with that day's date: news refreshes as usual and the
market sections carry the last session's close, labelled with that date.
Holidays come from the NSE website's live holiday API; if NSE is unreachable,
the embedded official NSE circular for 2026 (NSE/CMTR/71775) is used instead.
"""

import json
import urllib.request
from datetime import datetime, timedelta

NSE_HOLIDAYS_EMBEDDED = {
    2026: {
        "01-26": "Republic Day", "03-03": "Holi", "03-26": "Shri Ram Navami",
        "03-31": "Shri Mahavir Jayanti", "04-03": "Good Friday",
        "04-14": "Dr. Baba Saheb Ambedkar Jayanti", "05-01": "Maharashtra Day",
        "05-28": "Bakri Id", "06-26": "Muharram", "09-14": "Ganesh Chaturthi",
        "10-02": "Mahatma Gandhi Jayanti", "10-20": "Dussehra",
        "11-10": "Diwali-Balipratipada",
        "11-24": "Prakash Gurpurb Sri Guru Nanak Dev", "12-25": "Christmas",
    },
}

_HOLIDAY_CACHE = {}


def _nse_holidays_live(year):
    """Trading holidays from NSE's own holiday API; raises on any problem."""
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
    opener.addheaders = [
        ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
        ("Accept-Language", "en-US,en;q=0.9"),
    ]
    opener.open("https://www.nseindia.com/", timeout=15).read()
    with opener.open("https://www.nseindia.com/api/holiday-master?type=trading",
                     timeout=15) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    blocks = [payload["CM"]] if isinstance(payload.get("CM"), list) else \
        [v for v in payload.values() if isinstance(v, list)]
    out = {}
    for row in blocks[0]:
        try:
            d = datetime.strptime(str(row.get("tradingDate", "")), "%d-%b-%Y").date()
        except (TypeError, ValueError):
            continue
        if d.year == year:
            out[d] = str(row.get("description") or "Trading holiday")
    if not out:
        raise RuntimeError("NSE holiday API returned no dates for %d" % year)
    return out


def nse_holidays(year):
    """{date: name}: live from NSE, else the embedded official list, else empty."""
    if year in _HOLIDAY_CACHE:
        return _HOLIDAY_CACHE[year]
    try:
        hol = _nse_holidays_live(year)
        print("  trading calendar: live NSE holiday list (%d holidays)" % len(hol))
    except Exception as e:
        emb = NSE_HOLIDAYS_EMBEDDED.get(year) or {}
        hol = {datetime.strptime("%d-%s" % (year, md), "%Y-%m-%d").date(): name
               for md, name in emb.items()}
        print("  trading calendar: NSE unreachable (%s) - embedded list: %d dates"
              % (e, len(hol)))
    _HOLIDAY_CACHE[year] = hol
    return hol


def indian_trading_day(d):
    """(True, "") on trading days, else (False, reason) for an IST date."""
    if d.weekday() >= 5:
        return False, "the weekend"
    name = nse_holidays(d.year).get(d)
    if name:
        return False, name
    return True, ""


def last_trading_day(d):
    """Most recent trading day strictly before d (for the carried label)."""
    cur = d - timedelta(days=1)
    for _ in range(15):
        if indian_trading_day(cur)[0]:
            return cur
        cur -= timedelta(days=1)
    return cur


def asof_close_label(session_date):
    """e.g. AS OF FRIDAY'S CLOSE, SEP 25 - carried market sections wear this."""
    return "AS OF %s'S CLOSE, %s %d" % (session_date.strftime("%A").upper(),
                                        session_date.strftime("%b").upper(),
                                        session_date.day)


def load_previous_data(data_file):
    """The existing data.json, if it exists and has the market sections."""
    try:
        with open(data_file, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict) and isinstance(d.get("market_watch"), dict) \
                and isinstance(d.get("data_desk"), dict):
            return d
    except (OSError, ValueError):
        pass
    return None


def carried_market_summary(mw, session_date, reason):
    """Market figures Gemini may cite on a closed day, with a shut-today note."""
    lines = ["NOTE: Indian markets are CLOSED today (%s). The figures below are "
             "the last completed trading session (%s), and the page labels them "
             "exactly that way. The market_watch_teaser must present them as "
             "that session's close (markets shut today), never as today's live "
             "trading." % (reason, session_date.strftime("%A, %d %B %Y"))]
    for group in ("indian", "asian", "european", "global"):
        for row in mw.get(group) or []:
            if isinstance(row, dict):
                lines.append("%s: %s (%s)" % (row.get("name"), row.get("value"),
                                              row.get("dir")))
    lines.append("Top Nifty gainers: " + ", ".join(mw.get("winners") or []))
    lines.append("Top Nifty losers: " + ", ".join(mw.get("losers") or []))
    lines.append("Sectors: " + str(mw.get("snapshot_strip") or ""))
    return "\n".join(lines)
