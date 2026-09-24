#!/usr/bin/env python3
"""
FINTRIX daily content generator.

Calls the Gemini API free tier once a day, asks for that day's Market Watch
and Daily Brief content as JSON, checks the answer carefully, and rewrites
data.json. The website (index.html) reads data.json when it loads.

If anything goes wrong - no API key, rate limit hit, weird answer - the
script exits with an error WITHOUT touching data.json, so the site keeps
showing the previous day's content.

Needs one environment variable:
  GEMINI_API_KEY   a free key from https://aistudio.google.com/apikey

Optional:
  GEMINI_MODELS    comma-separated model fallbacks
                   (default: gemini-2.5-flash,gemini-2.0-flash,gemini-2.5-flash-lite)

Runs on Python 3.9+ with no extra packages to install.
"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
TODAY = datetime.now(IST)
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")

DEFAULT_MODELS = "gemini-3.6-flash,gemini-3.5-flash-lite"
MODELS = [m.strip() for m in os.environ.get("GEMINI_MODELS", DEFAULT_MODELS).split(",") if m.strip()]

PROMPT = """You are the markets editor of FINTRIX, a college finance club magazine in India.

Today is {today} (India time). Write TODAY'S daily market content, using the most recent
trading session's closing data (if today is a weekend or market holiday, use the last
trading day). Use Google Search grounding to get real closing levels and real news -
do not invent index levels or events.

Reply with ONLY a JSON object (no markdown fences, no commentary) in exactly this shape:

{{
  "cover": {{
    "market_watch_teaser": "one line, max 90 characters, cover teaser for the market page",
    "daily_brief_teaser": "one line, max 90 characters, mentions both daily brief stories",
    "inbrief_2": "max 35 characters, ultra-short label for story_1",
    "inbrief_3": "max 35 characters, ultra-short label for story_2"
  }},
  "market_watch": {{
    "date_label": "e.g. {month_label}",
    "close_label": "e.g. CLOSE OF {close_label}",
    "indian": [
      {{"name": "Sensex", "value": "80,123.45 ▲ 0.42%", "dir": "up"}},
      {{"name": "Nifty 50", "value": "24,567.80 ▼ 0.18%", "dir": "down"}},
      {{"name": "Nifty Bank", "value": "which sectors led and lagged, max 45 chars", "dir": ""}}
    ],
    "asian": [
      {{"name": "Nikkei 225", "value": "level ▲/▼ pct", "dir": "up or down"}},
      {{"name": "Hang Seng", "value": "level ▲/▼ pct", "dir": "up or down"}},
      {{"name": "Shanghai Comp.", "value": "level ▲/▼ pct", "dir": "up or down"}}
    ],
    "european": [
      {{"name": "FTSE 100", "value": "level ▲/▼ pct", "dir": "up or down"}},
      {{"name": "DAX", "value": "level ▲/▼ pct", "dir": "up or down"}},
      {{"name": "CAC 40", "value": "level ▲/▼ pct", "dir": "up or down"}}
    ],
    "global": [
      {{"name": "Dollar Index", "value": "▲/▼ pct", "dir": "up or down"}},
      {{"name": "Brent Crude", "value": "e.g. $87/bbl or > $90/bbl", "dir": "up, down or empty"}},
      {{"name": "Gold", "value": "e.g. ~$2,650/oz", "dir": "up, down or empty"}}
    ],
    "losers": ["Nifty stock 1", "Nifty stock 2", "Nifty stock 3"],
    "winners": ["Nifty stock 1", "Nifty stock 2", "Nifty stock 3"],
    "snapshot_strip": "one sentence, max 110 chars, which sectors dragged or lifted the index",
    "ipo_desk": [
      {{"name": "Company", "note": "max 45 chars, e.g. ₹680 cr issue closes Friday"}}
    ]
  }},
  "daily_brief": {{
    "story_1": {{
      "kicker": "India | Monetary Policy style label, max 35 chars",
      "headline": "max 60 chars, magazine headline",
      "paragraphs": ["paragraph 1, 3-4 sentences", "paragraph 2, 2-3 sentences"]
    }},
    "story_2": {{
      "kicker": "Global | Markets style label, max 35 chars",
      "headline": "max 60 chars",
      "paragraphs": ["paragraph 1", "paragraph 2"]
    }}
  }}
}}

Rules:
- "losers" and "winners" are the day's 3 biggest Nifty 50 fallers and gainers (company names only).
- "ipo_desk" has 1 to 3 live or upcoming Indian IPO/NFO items; if none are notable, one line saying so.
- daily_brief stories: two short finance/business stories of the day, at least one India-focused
  (RBI, policy, Indian corporate); the other can be global (AI, US markets, oil, geopolitics).
  Match the tone of a smart college finance magazine: plain English, no jargon dumps.
- "value" strings must include the ▲ or ▼ arrow when dir is "up" or "down".
- Use the actual ₹, ▲, ▼ characters, not HTML entities.
- Every string must be plain text. No HTML tags, no markdown, no links.
"""


def fail(msg):
    print("ERROR: " + msg, file=sys.stderr)
    print("data.json was NOT changed - the site keeps yesterday's content.", file=sys.stderr)
    sys.exit(1)


def call_gemini(api_key, model, use_grounding, prompt):
    """One generateContent call. Returns parsed JSON dict or raises."""
    url = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % model
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.4,
            "response_mime_type": "application/json",
        },
    }
    if use_grounding:
        payload["tools"] = [{"google_search": {}}]
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
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


def validate(d):
    """Hard-fail on anything that would break the page layout. Only shape and
    length are checked here; the page itself also ignores missing/extra fields."""
    if not isinstance(d, dict):
        fail("top level is not a JSON object")
    cover = d.get("cover")
    if not isinstance(cover, dict):
        fail("missing 'cover'")
    for key, hi in (("market_watch_teaser", 100), ("daily_brief_teaser", 100),
                    ("inbrief_2", 40), ("inbrief_3", 40)):
        if not is_str(cover.get(key), 3, hi):
            fail("cover.%s missing or too long (max %d chars)" % (key, hi))
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


def main():
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        fail("GEMINI_API_KEY is not set. Add it as a repository secret (see README step 4).")

    last_close = TODAY - timedelta(days=1)
    while last_close.weekday() >= 5:  # skip weekends for the "close of" label
        last_close -= timedelta(days=1)
    prompt = PROMPT.format(
        today=TODAY.strftime("%A, %d %B %Y"),
        month_label=TODAY.strftime("%b %Y").upper(),
        close_label=last_close.strftime("%b %-d").upper() if os.name != "nt"
                    else last_close.strftime("%b %d").upper().replace(" 0", " "),
    )

    data = None
    last_err = None
    for model in MODELS:
        for use_grounding in (True, False):
            try:
                print("Trying model %s (grounding: %s)..." % (model, "on" if use_grounding else "off"))
                data = call_gemini(api_key, model, use_grounding, prompt)
                break
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:300]
                last_err = "HTTP %s from %s: %s" % (e.code, model, detail)
                print("  " + last_err)
                if e.code in (401, 403):
                    fail("Gemini rejected the API key. Check the GEMINI_API_KEY secret.")
                # 400/404/429 etc: try the next option
            except (RuntimeError, ValueError, urllib.error.URLError, TimeoutError) as e:
                last_err = "%s: %s" % (model, e)
                print("  " + str(last_err))
        if data is not None:
            break

    if data is None:
        fail("all Gemini attempts failed. Last error: %s" % last_err)

    validate(data)

    # keep only the fields the site uses, in a stable order
    out = {
        "updated_ist": TODAY.strftime("%Y-%m-%d"),
        "cover": data["cover"],
        "market_watch": data["market_watch"],
        "daily_brief": data["daily_brief"],
    }
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, DATA_FILE)
    print("Wrote %s for %s" % (DATA_FILE, out["updated_ist"]))


if __name__ == "__main__":
    main()
