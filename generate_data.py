#!/usr/bin/env python3
"""
FINTRIX daily content generator.

Regenerates EVERY daily section of the magazine once a day: the cover lines,
the Big Story, Finnexus Explains, Venture Vault, Market Watch, the Daily Brief
and the Geopolitics page. Only the Credits / authors page stays fixed.
The website (index.html) reads data.json when it loads.

Where the content comes from (all free, no paid tiers):
  * Market Watch NUMBERS come straight from Yahoo Finance's public chart feed
    and are computed here in Python. The AI never writes a number on that page.
  * STORIES are written by Gemini (free tier), but only from today's real news
    headlines pulled from Google News RSS. Every story must name the headline
    numbers it is based on, and any figure in the text must appear in those
    headlines or in the market data - otherwise the answer is thrown away.
    (Google Search grounding is not free on the Gemini 3.x models, so it is
    deliberately not used - it would bill if billing were ever turned on.)

Four steps run in sequence:
  1. market data  - index levels, commodities, Nifty 50 gainers/losers, sectors
  2. "features"    - Big Story + Explains + Venture Vault + their cover teasers
  3. "markets"     - Daily Brief + IPO desk + market/brief cover lines
  4. "geopolitics" - Geopolitics page + cover In Brief item 01 (same answer, so
                     the cover teaser always matches the story)

If anything goes wrong - a feed is down, the market data looks stale, Gemini
fails or answers with an unsupported figure - the script exits with an error
WITHOUT touching data.json, so the site keeps showing the previous day.

Needs one environment variable:
  GEMINI_API_KEY   a free key from https://aistudio.google.com/apikey

Optional:
  GEMINI_MODELS    comma-separated model fallbacks
                   (default: gemini-3.6-flash,gemini-3.5-flash-lite)

Runs on Python 3.9+ with no extra packages to install.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

IST = timezone(timedelta(hours=5, minutes=30))
TODAY = datetime.now(IST)
NOW_UTC = datetime.now(timezone.utc)
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")
UA = {"User-Agent": "Mozilla/5.0 (compatible; FINTRIX-daily/1.0)"}

DEFAULT_MODELS = "gemini-3.6-flash,gemini-3.5-flash-lite"
MODELS = [m.strip() for m in os.environ.get("GEMINI_MODELS", DEFAULT_MODELS).split(",") if m.strip()]

# Nifty 50 members (NSE symbols). NSE reshuffles the index twice a year
# (March and September) - update this list when that happens.
NIFTY50 = {
    "ADANIENT": "Adani Enterprises", "ADANIPORTS": "Adani Ports", "APOLLOHOSP": "Apollo Hospitals",
    "ASIANPAINT": "Asian Paints", "AXISBANK": "Axis Bank", "BAJAJ-AUTO": "Bajaj Auto",
    "BAJFINANCE": "Bajaj Finance", "BAJAJFINSV": "Bajaj Finserv", "BEL": "Bharat Electronics",
    "BHARTIARTL": "Bharti Airtel", "CIPLA": "Cipla", "COALINDIA": "Coal India",
    "DRREDDY": "Dr. Reddy's", "EICHERMOT": "Eicher Motors", "ETERNAL": "Eternal",
    "GRASIM": "Grasim", "HCLTECH": "HCLTech", "HDFCBANK": "HDFC Bank", "HDFCLIFE": "HDFC Life",
    "HINDALCO": "Hindalco", "HINDUNILVR": "Hindustan Unilever", "ICICIBANK": "ICICI Bank",
    "INDIGO": "InterGlobe Aviation", "INFY": "Infosys", "ITC": "ITC", "JIOFIN": "Jio Financial",
    "JSWSTEEL": "JSW Steel", "KOTAKBANK": "Kotak Mahindra Bank", "LT": "Larsen & Toubro",
    "M&M": "Mahindra & Mahindra", "MARUTI": "Maruti Suzuki", "MAXHEALTH": "Max Healthcare",
    "NESTLEIND": "Nestle India", "NTPC": "NTPC", "ONGC": "ONGC", "POWERGRID": "Power Grid",
    "RELIANCE": "Reliance Industries", "SBILIFE": "SBI Life", "SHRIRAMFIN": "Shriram Finance",
    "SBIN": "State Bank of India", "SUNPHARMA": "Sun Pharma", "TCS": "TCS",
    "TATACONSUM": "Tata Consumer", "TMPV": "Tata Motors PV", "TATASTEEL": "Tata Steel",
    "TECHM": "Tech Mahindra", "TITAN": "Titan", "TRENT": "Trent", "ULTRACEMCO": "UltraTech Cement",
    "WIPRO": "Wipro",
}

SECTORS = {"^CNXIT": "IT", "^CNXAUTO": "Auto", "^CNXFMCG": "FMCG", "^CNXPHARMA": "Pharma",
           "^CNXREALTY": "Realty", "^CNXMETAL": "Metal", "^CNXENERGY": "Energy",
           "^NSEBANK": "Banks", "^CNXPSUBANK": "PSU Banks", "^CNXMEDIA": "Media"}

NEWS_QUERIES = {
    "india_business": "India economy OR RBI OR Sensex OR Nifty when:1d",
    "india_corporate": "India company results OR acquisition OR deal crore when:1d",
    "startups": "Indian startup raises funding when:2d",
    "ipo": "IPO India subscription OR listing OR price band when:2d",
    "geopolitics": "India foreign policy OR trade deal OR tariffs OR summit when:1d",
    "global": "global markets OR oil prices OR Federal Reserve OR gold prices when:1d",
}

HEADLINE_BLOCK_NOTE = """Today's real news headlines (numbered; source outlet and publish time in brackets):
{headlines}

HARD RULES about facts:
- Write ONLY about stories that appear in the headlines above. Do not invent companies,
  people, deals, funding rounds, events or dates.
- Every figure you write (amounts, percentages, index levels, counts) must appear in the
  headlines or market data above. If a figure is not there, describe it without a number.
- You may add general background knowledge to explain concepts, but no new specific facts.
- Each story object has a "sources" list: the headline numbers it is based on.
"""

FEATURES_PROMPT = """You are the features editor of FINTRIX, a college finance club magazine in India.
Today is {today} (India time).

{headline_block}
Pick ONE big-story topic from the headlines: an Indian business, finance, markets or economy
theme (policy, a sector shift, a major corporate move, a consumer or tech trend with a money angle).

Reply with ONLY a JSON object (no markdown fences, no commentary) in exactly this shape:

{{
  "cover": {{
    "big_story_teaser": "one line, max 90 characters, cover teaser for the big story",
    "venture_teaser": "one line, max 90 characters, cover teaser for the venture story"
  }},
  "big_story": {{
    "sources": [1, 2],
    "headline": "max 40 characters, short punchy magazine headline",
    "subhead": "max 90 characters, ALL CAPS standfirst expanding on the headline",
    "paragraphs": [
      "paragraph 1, 3-4 sentences, sets the scene with the real detail from the headlines",
      "paragraph 2, 3-4 sentences, the context and why it is happening",
      "paragraph 3, 3-4 sentences, what it means and what to watch"
    ],
    "pullbox": "max 220 characters, one sharp 'big idea' takeaway from the story"
  }},
  "explains": {{
    "title": "max 45 characters, 'What is X?' style title for the key concept in the big story",
    "paragraphs": [
      "paragraph 1, 2-3 sentences, plain-English origin/definition of the concept",
      "paragraph 2, 2-3 sentences, how it plays out in practice"
    ]
  }},
  "venture_vault": {{
    "sources": [3],
    "paragraphs": [
      "paragraph 1, 2-3 sentences, a REAL startup funding or growth story from the headlines (prefer Indian startups): who, how much, what they do",
      "paragraph 2, 2-3 sentences, the backers, the founders' bet, why it matters"
    ]
  }}
}}

Rules:
- The explains box must explain the central concept of THIS big story (they appear side by side).
- Venture Vault must be a different story from the big story, about a real named startup in the headlines.
- cover.big_story_teaser must describe THIS big story, and cover.venture_teaser must name the SAME
  startup as the venture_vault paragraphs - they appear together.
- Tone: a smart college finance magazine - plain English, no jargon dumps, Indian-market focus.
- Every string must be plain text. No HTML tags, no markdown, no links.
- Use the actual ₹ character (not HTML entities) where a rupee amount appears.
"""

MARKETS_PROMPT = """You are the markets editor of FINTRIX, a college finance club magazine in India.
Today is {today} (India time).

Verified market data for the last completed session (already on the page - do not change it):
{market_summary}

{headline_block}
Reply with ONLY a JSON object (no markdown fences, no commentary) in exactly this shape:

{{
  "cover": {{
    "market_watch_teaser": "one line, max 90 characters, cover teaser for the market page, consistent with the market data (up/down direction must match)",
    "daily_brief_teaser": "one line, max 90 characters, mentions both daily brief stories",
    "inbrief_2": "max 35 characters, ultra-short label for story_1",
    "inbrief_3": "max 35 characters, ultra-short label for story_2"
  }},
  "ipo_desk": [
    {{"name": "Company", "note": "max 45 chars, e.g. ₹680 cr issue closes Friday", "sources": [4]}}
  ],
  "daily_brief": {{
    "story_1": {{
      "sources": [5],
      "kicker": "India | Monetary Policy style label, max 35 chars",
      "headline": "max 60 chars, magazine headline",
      "paragraphs": ["paragraph 1, 3-4 sentences", "paragraph 2, 2-3 sentences"]
    }},
    "story_2": {{
      "sources": [6],
      "kicker": "Global | Markets style label, max 35 chars",
      "headline": "max 60 chars",
      "paragraphs": ["paragraph 1", "paragraph 2"]
    }}
  }}
}}

Rules:
- "ipo_desk": 1 to 3 live or upcoming Indian IPOs named in the headlines. If none are in the
  headlines, return exactly one item: {{"name": "IPO desk", "note": "No major issues open today", "sources": []}}.
- daily_brief: two short finance/business stories of the day, at least one India-focused
  (RBI, policy, Indian corporate); the other can be global (AI, US markets, oil, geopolitics).
  Avoid the big story already chosen for today: {avoid}
- Tone: a smart college finance magazine - plain English, no jargon dumps.
- Use the actual ₹ character, not HTML entities. Plain text only - no HTML, markdown or links.
"""

GEOPOLITICS_PROMPT = """You are the geopolitics editor of FINTRIX, a college finance club magazine in India.
Today is {today} (India time).

{headline_block}
Pick ONE geopolitical story from the headlines that matters for India's economy, trade or
markets: power, trade and strategic relationships shaping business (India's ties with China,
the US, Russia, the Gulf or the EU; trade deals and tariffs; sanctions; conflicts affecting oil
or shipping; summits).
{avoid}
Reply with ONLY a JSON object (no markdown fences, no commentary) in exactly this shape:

{{
  "cover": {{
    "inbrief_1": "max 35 characters, ultra-short cover label teasing THIS geopolitics story"
  }},
  "geopolitics": {{
    "sources": [7],
    "kicker": "max 30 characters, e.g. India x China or India | Trade",
    "headline": "max 60 characters, magazine headline for the story",
    "paragraphs": [
      "paragraph 1, 3-4 sentences, what is happening, with the real names and details from the headlines",
      "paragraph 2, 3-4 sentences, what is still unsettled and why it matters for business"
    ],
    "world_60": [
      "max 90 characters, one-line world headline with a money angle",
      "max 90 characters, another one",
      "max 90 characters, another one",
      "max 90 characters, another one"
    ],
    "world_60_sources": [8, 9, 10, 11]
  }}
}}

Rules:
- cover.inbrief_1 sits on the cover and links to this page, so it MUST be about the SAME
  story as the geopolitics headline and paragraphs - name the same country, leader or deal.
- "world_60" is a quick 4-item round-up of OTHER real global headlines from the list
  (oil, gold, bonds, central banks, global markets, conflicts), different from the main story.
- Tone: a smart college finance magazine - plain English, no jargon dumps, Indian angle.
- Every string must be plain text. No HTML tags, no markdown, no links.
"""

STOPWORDS = {"with", "from", "that", "this", "into", "over", "amid", "after", "about",
             "their", "they", "what", "will", "than", "more", "near", "nears", "talks",
             "deal", "visit", "india", "indian", "india's", "global", "world", "trade"}


def fail(msg):
    print("ERROR: " + msg, file=sys.stderr)
    print("data.json was NOT changed - the site keeps yesterday's content.", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------- HTTP helpers

def http_get(url, timeout=30, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError("GET failed for %s: %s" % (url, last))


# ---------------------------------------------------------------- market data

def _chart(symbol, rng):
    enc = urllib.parse.quote(symbol, safe="")
    last_err = None
    for host in ("query1", "query2"):
        url = "https://%s.finance.yahoo.com/v8/finance/chart/%s?range=%s&interval=1d" % (host, enc, rng)
        try:
            return json.loads(http_get(url, tries=2).decode("utf-8"))["chart"]["result"][0]
        except Exception as e:  # noqa: BLE001 - any feed problem means try the other host
            last_err = e
    raise RuntimeError("%s: %s" % (symbol, last_err))


def quote(symbol):
    """Last completed session for a Yahoo Finance symbol.
    Returns dict(last, prev, pct, date) or raises RuntimeError."""
    r = _chart(symbol, "15d")
    meta = r.get("meta") or {}
    gmtoff = meta.get("gmtoffset") or 0

    def local_date(t):
        return datetime.fromtimestamp(t + gmtoff, timezone.utc).date()

    ts = r.get("timestamp") or []
    closes = (((r.get("indicators") or {}).get("quote") or [{}])[0].get("close")) or []
    bars = [[t, c] for t, c in zip(ts, closes)]
    # Yahoo sometimes leaves the latest daily close empty and only reports it as
    # regularMarketPrice - use that for its session day
    rmp, rmt = meta.get("regularMarketPrice"), meta.get("regularMarketTime")
    if isinstance(rmp, (int, float)) and isinstance(rmt, int):
        if not bars or local_date(rmt) > local_date(bars[-1][0]):
            bars.append([rmt, float(rmp)])
        elif local_date(rmt) == local_date(bars[-1][0]):
            bars[-1][1] = float(rmp)
    # drop today's bar until that market has closed (pre-open or live prices
    # are not a close yet)
    reg = (meta.get("currentTradingPeriod") or {}).get("regular") or {}
    now = int(time.time())
    dropped = False
    if bars and reg.get("end") and now < reg["end"] and local_date(bars[-1][0]) >= local_date(now):
        bars = bars[:-1]
        dropped = True
    if not bars or bars[-1][1] is None:
        raise RuntimeError("%s: no usable latest close" % symbol)
    t1, last = bars[-1]
    prev = bars[-2][1] if len(bars) >= 2 else None
    if prev is None:
        # previous day's close missing from the daily bars: ask for the 1-day
        # chart, whose chartPreviousClose is the prior session's close
        if dropped:
            # market is mid-session: fall back to the nearest earlier close
            earlier = [c for _, c in bars[:-1] if c is not None]
            if not earlier:
                raise RuntimeError("%s: previous close missing" % symbol)
            prev = earlier[-1]
            return {"last": last, "prev": prev, "pct": (last - prev) / prev * 100.0,
                    "date": local_date(t1)}
        r1 = _chart(symbol, "1d")
        m1 = r1.get("meta") or {}
        if m1.get("regularMarketTime") and local_date(m1["regularMarketTime"]) == local_date(t1):
            prev = m1.get("chartPreviousClose")
        if not isinstance(prev, (int, float)) or prev <= 0:
            raise RuntimeError("%s: previous close missing" % symbol)
    return {"last": last, "prev": prev, "pct": (last - prev) / prev * 100.0, "date": local_date(t1)}


def arrow(pct):
    return "\u25b2" if pct >= 0 else "\u25bc"


def dir_of(pct):
    return "up" if pct >= 0 else "down"


def fmt_level(q):
    return "%s %s %.2f%%" % ("{:,.2f}".format(q["last"]), arrow(q["pct"]), abs(q["pct"]))


def market_data():
    """Everything numeric on the Market Watch page, computed from real quotes."""
    indices = {
        "indian": [("Sensex", "^BSESN"), ("Nifty 50", "^NSEI"), ("Nifty Bank", "^NSEBANK")],
        "asian": [("Nikkei 225", "^N225"), ("Hang Seng", "^HSI"), ("Shanghai Comp.", "000001.SS")],
        "european": [("FTSE 100", "^FTSE"), ("DAX", "^GDAXI"), ("CAC 40", "^FCHI")],
    }
    mw = {}
    q = {}
    for group, rows in indices.items():
        out = []
        for name, sym in rows:
            try:
                q[sym] = quote(sym)
            except RuntimeError as e:
                fail("market feed: %s" % e)
            out.append({"name": name, "value": fmt_level(q[sym]), "dir": dir_of(q[sym]["pct"])})
        mw[group] = out

    try:
        dxy, brent, gold = quote("DX-Y.NYB"), quote("BZ=F"), quote("GC=F")
    except RuntimeError as e:
        fail("market feed: %s" % e)
    mw["global"] = [
        {"name": "Dollar Index", "value": "%.2f %s %.2f%%" % (dxy["last"], arrow(dxy["pct"]), abs(dxy["pct"])),
         "dir": dir_of(dxy["pct"])},
        {"name": "Brent Crude", "value": "$%.2f/bbl" % brent["last"], "dir": dir_of(brent["pct"])},
        {"name": "Gold", "value": "${:,.0f}/oz".format(gold["last"]), "dir": dir_of(gold["pct"])},
    ]

    # freshness: the Indian close must be from the last few days, or the feed is stale
    india_date = q["^BSESN"]["date"]
    if (TODAY.date() - india_date).days > 5:
        fail("market feed looks stale (last Sensex close %s)" % india_date)

    # Nifty 50 gainers / losers
    moves = []
    for sym, name in NIFTY50.items():
        try:
            s = quote(sym + ".NS")
            if s["date"] == india_date:
                moves.append((s["pct"], name))
        except RuntimeError as e:
            print("  skipping %s: %s" % (sym, e))
    if len(moves) < 40:
        fail("only %d of 50 Nifty stocks returned data - not enough for gainers/losers" % len(moves))
    moves.sort()
    mw["losers"] = [n for _, n in moves[:3]]
    mw["winners"] = [n for _, n in moves[::-1][:3]]

    # sector leaders / laggards for the snapshot strip
    secs = []
    for sym, label in SECTORS.items():
        try:
            s = quote(sym)
            if s["date"] == india_date:
                secs.append((s["pct"], label))
        except RuntimeError as e:
            print("  skipping sector %s: %s" % (sym, e))
    nifty = q["^NSEI"]
    if len(secs) >= 4:
        secs.sort()
        up = [l for p, l in secs[::-1][:2] if p > 0]
        down = [l for p, l in secs[:2] if p < 0]
        parts = []
        if up:
            parts.append(" and ".join(up) + " led")
        if down:
            parts.append(" and ".join(down) + " lagged")
        strip = "; ".join(parts) or "Sectors moved in a narrow range"
        strip += " as the Nifty %s %.2f%%" % ("rose" if nifty["pct"] >= 0 else "fell", abs(nifty["pct"]))
    else:
        strip = "The Nifty %s %.2f%% in the last session" % ("rose" if nifty["pct"] >= 0 else "fell",
                                                             abs(nifty["pct"]))
    mw["snapshot_strip"] = strip[:130]

    mw["date_label"] = india_date.strftime("%b %Y").upper()
    mw["close_label"] = "CLOSE OF %s %d" % (india_date.strftime("%b").upper(), india_date.day)

    summary_lines = ["Session date: %s" % india_date.isoformat()]
    for group in ("indian", "asian", "european", "global"):
        for row in mw[group]:
            summary_lines.append("%s: %s (%s)" % (row["name"], row["value"], row["dir"]))
    summary_lines.append("Brent change: %s %.2f%%; Gold change: %s %.2f%%"
                         % (arrow(brent["pct"]), abs(brent["pct"]), arrow(gold["pct"]), abs(gold["pct"])))
    summary_lines.append("Top Nifty gainers: " + ", ".join(mw["winners"]))
    summary_lines.append("Top Nifty losers: " + ", ".join(mw["losers"]))
    summary_lines.append("Sectors: " + mw["snapshot_strip"])
    return mw, "\n".join(summary_lines)


# ---------------------------------------------------------------- news headlines

def headlines():
    """Recent real headlines from Google News RSS, de-duplicated and numbered."""
    items, seen = [], set()
    cutoff = NOW_UTC - timedelta(hours=48)
    failures = 0
    for topic, q in NEWS_QUERIES.items():
        url = ("https://news.google.com/rss/search?q=%s&hl=en-IN&gl=IN&ceid=IN:en"
               % urllib.parse.quote(q))
        try:
            root = ET.fromstring(http_get(url))
        except (RuntimeError, ET.ParseError) as e:
            print("  news feed '%s' failed: %s" % (topic, e))
            failures += 1
            continue
        for it in list(root.iter("item"))[:12]:
            title = (it.findtext("title") or "").strip()
            source = (it.findtext("source") or "").strip()
            try:
                pub = parsedate_to_datetime(it.findtext("pubDate") or "")
            except (TypeError, ValueError):
                continue
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
            if not title or pub < cutoff:
                continue
            if source and title.endswith(" - " + source):
                title = title[: -len(" - " + source)]
            key = re.sub(r"\W+", " ", title.lower()).strip()[:80]
            if key in seen:
                continue
            seen.add(key)
            items.append({"topic": topic, "title": title, "source": source,
                          "published": pub.astimezone(IST).strftime("%d %b %H:%M IST")})
    if failures > 2 or len(items) < 15:
        fail("news feed returned too little (%d headlines, %d feeds failed)" % (len(items), failures))
    for i, it in enumerate(items, 1):
        it["id"] = i
    return items


def headline_block(items):
    lines = ["[%d] %s (%s, %s)" % (it["id"], it["title"], it["source"] or "unknown", it["published"])
             for it in items]
    return HEADLINE_BLOCK_NOTE.format(headlines="\n".join(lines))


# ---------------------------------------------------------------- Gemini

def call_gemini(api_key, model, prompt):
    """One generateContent call (no Search grounding - not free on Gemini 3.x).
    Returns parsed JSON dict or raises."""
    url = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % model
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "response_mime_type": "application/json"},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    candidates = body.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini returned no candidates: %s" % json.dumps(body)[:400])
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise RuntimeError("Gemini returned empty text (finish reason: %s)"
                           % candidates[0].get("finishReason"))
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


def generate(api_key, prompt, label, check=None):
    """Run one prompt through the model fallbacks (two tries per model).
    If a check function returns an error string, that answer is discarded and
    the next try is made. Returns parsed JSON dict, or None if every try failed."""
    last_err = None
    for model in MODELS:
        for attempt in (1, 2):
            try:
                print("Trying %s with model %s (try %d)..." % (label, model, attempt))
                result = call_gemini(api_key, model, prompt)
                problem = check(result) if check else None
                if problem:
                    raise ValueError(problem)
                return result
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:300]
                last_err = "HTTP %s from %s: %s" % (e.code, model, detail)
                print("  " + last_err)
                if e.code in (401, 403):
                    fail("Gemini rejected the API key. Check the GEMINI_API_KEY secret.")
                if e.code in (404,):
                    break  # model not available - go to the next one
                time.sleep(5)
            except (RuntimeError, ValueError, urllib.error.URLError, TimeoutError) as e:
                last_err = "%s: %s" % (model, e)
                print("  " + str(last_err))
    print("All Gemini attempts for %s failed. Last error: %s" % (label, last_err))
    return None


# ---------------------------------------------------------------- fact checks

YEAR = re.compile(r"^(19|20)\d\d$")


def numbers_in(text):
    """Figures worth checking: stand-alone numbers with 2+ digits (commas removed).
    Skips years, labels glued to letters (FY27, G20, Q2) and phrases like
    '10-year', and small whole numbers up to 31."""
    out = set()
    for m in re.finditer(r"(?<![A-Za-z\d.])\d[\d,]*(?:\.\d+)?(?![A-Za-z\d])", text):
        t = m.group(0).replace(",", "").rstrip(".")
        if re.match(r"-[A-Za-z]", text[m.end():m.end() + 2]):
            continue
        if len(re.sub(r"\D", "", t)) < 2 or YEAR.match(t):
            continue
        if t.isdigit() and int(t) <= 31:
            continue
        out.add(t)
    return out


def strings_in(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k not in ("sources", "world_60_sources"):
                yield from strings_in(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from strings_in(v)


def make_fact_check(allowed_text, n_items):
    allowed = numbers_in(allowed_text)
    # also allow decimals written without trailing zeros, e.g. 0.50 -> 0.5
    allowed |= {a.rstrip("0").rstrip(".") for a in allowed if "." in a}

    def check(pkg):
        if not isinstance(pkg, dict):
            return "not a JSON object"
        bad = set()
        for s in strings_in(pkg):
            for n in numbers_in(s):
                if n not in allowed and n.rstrip("0").rstrip(".") not in allowed:
                    bad.add(n)
        if bad:
            return "figures not found in the headlines/market data: %s" % ", ".join(sorted(bad)[:8])
        for srcs in _source_lists(pkg):
            if not isinstance(srcs, list) or not all(isinstance(i, int) and 1 <= i <= n_items for i in srcs):
                return "a story has an invalid 'sources' list"
        return None
    return check


def _source_lists(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("sources", "world_60_sources"):
                yield v
            else:
                yield from _source_lists(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _source_lists(v)


def keywords(text):
    words = []
    for w in text.lower().replace("\u2019", "'").split():
        w = w.strip(".,:;!?\"'()[]-|")
        if w.endswith("'s"):
            w = w[:-2]
        if len(w) >= 3 and w not in STOPWORDS:
            words.append(w)
    return set(words)


def check_geopolitics_pkg(pkg):
    """The cover teaser must share at least one real keyword with the story it links to."""
    if not isinstance(pkg, dict):
        return "not a JSON object"
    teaser = (pkg.get("cover") or {}).get("inbrief_1")
    g = pkg.get("geopolitics")
    if not isinstance(teaser, str) or not isinstance(g, dict):
        return "missing cover.inbrief_1 or geopolitics"
    story = " ".join([str(g.get("kicker", "")), str(g.get("headline", ""))]
                     + [str(p) for p in (g.get("paragraphs") or [])])
    if not keywords(teaser) & keywords(story):
        return "cover.inbrief_1 (%r) does not match the geopolitics story" % teaser
    return None


def both(*checks):
    def run(pkg):
        for c in checks:
            p = c(pkg)
            if p:
                return p
        return None
    return run


# ---------------------------------------------------------------- validation

def is_str(x, lo=1, hi=600):
    return isinstance(x, str) and lo <= len(x.strip()) <= hi


def check_stat(row, what):
    if not isinstance(row, dict):
        fail("%s: not an object" % what)
    if not is_str(row.get("value"), 1, 80):
        fail("%s: bad 'value'" % what)
    if row.get("dir", "") not in ("up", "down", ""):
        fail("%s: dir must be up/down/empty" % what)


def check_story(s, what):
    if not isinstance(s, dict):
        fail("%s: not an object" % what)
    if not is_str(s.get("kicker"), 1, 45):
        fail("%s: bad kicker" % what)
    if not is_str(s.get("headline"), 5, 80):
        fail("%s: bad headline" % what)
    ps = s.get("paragraphs")
    if not isinstance(ps, list) or not (1 <= len(ps) <= 3) or not all(is_str(p, 40, 900) for p in ps):
        fail("%s: needs 1-3 paragraphs of plain text" % what)


def check_paragraphs(s, what, count, lo, hi):
    if not isinstance(s, dict):
        fail("%s: not an object" % what)
    ps = s.get("paragraphs")
    if not isinstance(ps, list) or len(ps) != count or not all(is_str(p, lo, hi) for p in ps):
        fail("%s: needs exactly %d paragraphs of %d-%d chars" % (what, count, lo, hi))


def validate(d):
    """Hard-fail on anything that would break the page layout."""
    if not isinstance(d, dict):
        fail("top level is not a JSON object")
    cover = d.get("cover")
    if not isinstance(cover, dict):
        fail("missing 'cover'")
    for key, hi in (("big_story_teaser", 100), ("venture_teaser", 100),
                    ("market_watch_teaser", 100), ("daily_brief_teaser", 100),
                    ("inbrief_1", 40), ("inbrief_2", 40), ("inbrief_3", 40)):
        if not is_str(cover.get(key), 3, hi):
            fail("cover.%s missing or too long (max %d chars)" % (key, hi))
    bs = d.get("big_story")
    if not isinstance(bs, dict):
        fail("missing 'big_story'")
    if not is_str(bs.get("headline"), 3, 60):
        fail("big_story.headline bad (max 60 chars)")
    if not is_str(bs.get("subhead"), 5, 110):
        fail("big_story.subhead bad (max 110 chars)")
    check_paragraphs(bs, "big_story", 3, 100, 900)
    if not is_str(bs.get("pullbox"), 20, 260):
        fail("big_story.pullbox bad (max 260 chars)")
    ex = d.get("explains")
    if not isinstance(ex, dict):
        fail("missing 'explains'")
    if not is_str(ex.get("title"), 3, 60):
        fail("explains.title bad (max 60 chars)")
    check_paragraphs(ex, "explains", 2, 80, 900)
    vv = d.get("venture_vault")
    check_paragraphs(vv, "venture_vault", 2, 80, 900)
    mw = d.get("market_watch")
    if not isinstance(mw, dict):
        fail("missing 'market_watch'")
    if not is_str(mw.get("date_label"), 3, 20):
        fail("market_watch.date_label bad")
    if not is_str(mw.get("close_label"), 3, 30):
        fail("market_watch.close_label bad")
    for group in ("indian", "asian", "european", "global"):
        rows = mw.get(group)
        if not isinstance(rows, list) or len(rows) != 3:
            fail("market_watch.%s must have exactly 3 rows" % group)
        for i, row in enumerate(rows):
            check_stat(row, "market_watch.%s[%d]" % (group, i))
    for key in ("losers", "winners"):
        lst = mw.get(key)
        if not isinstance(lst, list) or len(lst) != 3 or not all(is_str(x, 2, 40) for x in lst):
            fail("market_watch.%s must be 3 short names" % key)
    if not is_str(mw.get("snapshot_strip"), 10, 130):
        fail("market_watch.snapshot_strip bad")
    ipo = mw.get("ipo_desk")
    if not isinstance(ipo, list) or not (1 <= len(ipo) <= 3):
        fail("market_watch.ipo_desk must have 1-3 items")
    for i, item in enumerate(ipo):
        if not isinstance(item, dict) or not is_str(item.get("name"), 2, 40) or not is_str(item.get("note"), 2, 60):
            fail("market_watch.ipo_desk[%d] bad" % i)
    db = d.get("daily_brief")
    if not isinstance(db, dict):
        fail("missing 'daily_brief'")
    check_story(db.get("story_1"), "daily_brief.story_1")
    check_story(db.get("story_2"), "daily_brief.story_2")
    geo = d.get("geopolitics")
    if not isinstance(geo, dict):
        fail("missing 'geopolitics'")
    if not is_str(geo.get("kicker"), 2, 40):
        fail("geopolitics.kicker bad (max 40 chars)")
    if not is_str(geo.get("headline"), 5, 80):
        fail("geopolitics.headline bad (max 80 chars)")
    check_paragraphs(geo, "geopolitics", 2, 100, 900)
    w60 = geo.get("world_60")
    if not isinstance(w60, list) or not (3 <= len(w60) <= 4) or not all(is_str(x, 10, 110) for x in w60):
        fail("geopolitics.world_60 must be 3-4 one-liners of 10-110 chars")
    problem = check_geopolitics_pkg({"cover": cover, "geopolitics": geo})
    if problem:
        fail(problem)


# ---------------------------------------------------------------- main

def main():
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        fail("GEMINI_API_KEY is not set. Add it as a repository secret (see README step 4).")
    today_str = TODAY.strftime("%A, %d %B %Y")

    print("Fetching market data...")
    mw, market_summary = market_data()
    print(market_summary)

    print("Fetching news headlines...")
    items = headlines()
    print("  %d headlines" % len(items))
    block = headline_block(items)
    all_headline_text = "\n".join(it["title"] for it in items)
    fact_check = make_fact_check(all_headline_text + "\n" + market_summary, len(items))

    features = generate(api_key, FEATURES_PROMPT.format(today=today_str, headline_block=block),
                        "features (big story, explains, venture vault)", check=fact_check)
    if features is None:
        fail("could not generate the features package - leaving data.json untouched.")

    bs = features.get("big_story") or {}
    avoid_bs = bs.get("headline", "") if isinstance(bs, dict) else ""
    markets = generate(api_key, MARKETS_PROMPT.format(today=today_str, headline_block=block,
                                                      market_summary=market_summary,
                                                      avoid=avoid_bs or "none"),
                       "markets (daily brief, ipo desk, cover lines)", check=fact_check)
    if markets is None:
        fail("could not generate the markets package - leaving data.json untouched.")

    taken = [t for t in [avoid_bs] if t]
    for s in ((markets.get("daily_brief") or {}).get("story_1"),
              (markets.get("daily_brief") or {}).get("story_2")):
        if isinstance(s, dict) and isinstance(s.get("headline"), str):
            taken.append(s["headline"])
    avoid = ""
    if taken:
        avoid = ("\nOther pages of today's issue already cover these stories - pick a DIFFERENT one:\n"
                 + "\n".join("- " + t for t in taken) + "\n")
    geo = generate(api_key, GEOPOLITICS_PROMPT.format(today=today_str, headline_block=block, avoid=avoid),
                   "geopolitics (geopolitics page, in brief 01)",
                   check=both(fact_check, check_geopolitics_pkg))
    if geo is None:
        fail("could not generate the geopolitics package - leaving data.json untouched.")

    mw["ipo_desk"] = [{"name": i.get("name"), "note": i.get("note")}
                      for i in (markets.get("ipo_desk") or []) if isinstance(i, dict)]
    data = {
        "cover": {},
        "big_story": features.get("big_story"),
        "explains": features.get("explains"),
        "venture_vault": features.get("venture_vault"),
        "market_watch": mw,
        "daily_brief": markets.get("daily_brief"),
        "geopolitics": geo.get("geopolitics"),
    }
    for src in (features, markets, geo):
        c = src.get("cover")
        if isinstance(c, dict):
            data["cover"].update(c)

    validate(data)

    # record which real headlines each story was written from (not shown on the page)
    by_id = {it["id"]: it for it in items}

    def cite(ids):
        return [{"title": by_id[i]["title"], "source": by_id[i]["source"]}
                for i in (ids or []) if isinstance(i, int) and i in by_id]
    g = data["geopolitics"]
    sources = {
        "big_story": cite(data["big_story"].pop("sources", [])),
        "venture_vault": cite(data["venture_vault"].pop("sources", [])),
        "daily_brief_1": cite(data["daily_brief"]["story_1"].pop("sources", [])),
        "daily_brief_2": cite(data["daily_brief"]["story_2"].pop("sources", [])),
        "geopolitics": cite(g.pop("sources", [])),
        "world_60": cite(g.pop("world_60_sources", [])),
        "ipo_desk": [x for i in (markets.get("ipo_desk") or []) if isinstance(i, dict)
                     for x in cite(i.get("sources"))],
        "market_data": "Yahoo Finance (computed, session %s)" % mw["close_label"].replace("CLOSE OF ", ""),
    }
    print("Sources used:")
    print(json.dumps(sources, ensure_ascii=False, indent=1))

    out = {"updated_ist": TODAY.strftime("%Y-%m-%d")}
    out.update(data)
    out["sources"] = sources
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, DATA_FILE)
    print("Wrote %s for %s" % (DATA_FILE, out["updated_ist"]))


if __name__ == "__main__":
    main()
