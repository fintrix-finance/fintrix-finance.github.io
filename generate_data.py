#!/usr/bin/env python3
"""
FINTRIX daily content generator.

Calls the Gemini API free tier once a day and regenerates EVERY daily section
of the magazine: the cover teasers, the Big Story feature article, the
Finnexus Explains box, the Venture Vault startup story, Market Watch stats,
the Daily Brief, and the Geopolitics page. The website (index.html) reads
data.json when it loads. (Only the Credits / authors page stays fixed.)

Three Gemini calls run in sequence:
  1. "features"    - Big Story + Explains + Venture Vault + their cover teasers
  2. "markets"     - Market Watch + Daily Brief + their cover teasers
  3. "geopolitics" - Geopolitics page + cover In Brief item 01, generated in
                     the SAME answer so the cover teaser always matches the story
Three calls a day sits comfortably inside the free tier's daily request caps.

If anything goes wrong - no API key, rate limit hit, weird answer - the
script exits with an error WITHOUT touching data.json, so the site keeps
showing the previous day's content.

Needs one environment variable:
  GEMINI_API_KEY   a free key from https://aistudio.google.com/apikey

Optional:
  GEMINI_MODELS    comma-separated model fallbacks
                   (default: gemini-3.6-flash,gemini-3.5-flash-lite)

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

FEATURES_PROMPT = """You are the features editor of FINTRIX, a college finance club magazine in India.

Today is {today} (India time). Write TODAY'S feature package, grounded in real,
recent business and finance news - use Google Search grounding; do not invent
companies, funding rounds, or events.

Pick ONE timely big-story topic: a real Indian business, finance, markets or
economy theme that is in the news this week (policy, a sector shift, a major
corporate move, a consumer or tech trend with a money angle).

Reply with ONLY a JSON object (no markdown fences, no commentary) in exactly this shape:

{{
  "cover": {{
    "big_story_teaser": "one line, max 90 characters, cover teaser for the big story",
    "venture_teaser": "one line, max 90 characters, cover teaser for the venture story"
  }},
  "big_story": {{
    "headline": "max 40 characters, short punchy magazine headline",
    "subhead": "max 90 characters, ALL CAPS standfirst expanding on the headline",
    "paragraphs": [
      "paragraph 1, 3-4 sentences, sets the scene with real detail",
      "paragraph 2, 3-4 sentences, the numbers and the context",
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
    "paragraphs": [
      "paragraph 1, 2-3 sentences, a REAL startup funding or growth story from the last few weeks (prefer Indian startups): who, how much, what they do",
      "paragraph 2, 2-3 sentences, the backers, the founders' bet, why it matters"
    ]
  }}
}}

Rules:
- The explains box must explain the central concept of THIS big story (they appear side by side).
- Venture Vault must be a different story from the big story, about a real named startup.
- cover.big_story_teaser must describe THIS big story, and cover.venture_teaser must refer to
  the SAME startup (same company name) as the venture_vault paragraphs - they appear together.
- Tone: a smart college finance magazine - plain English, no jargon dumps, Indian-market focus.
- Every string must be plain text. No HTML tags, no markdown, no links.
- Use the actual ₹ character (not HTML entities) where a rupee amount appears.
"""

MARKETS_PROMPT = """You are the markets editor of FINTRIX, a college finance club magazine in India.

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

GEOPOLITICS_PROMPT = """You are the geopolitics editor of FINTRIX, a college finance club magazine in India.

Today is {today} (India time). Write TODAY'S Geopolitics page, grounded in real, recent
news - use Google Search grounding; do not invent summits, deals, visits or events.

Pick ONE timely geopolitical story from this week that matters for India's economy,
trade or markets: power, trade and strategic relationships shaping business (for example
India's ties with China, the US, Russia, the Gulf or the EU; trade deals and tariffs;
sanctions; conflicts affecting oil or shipping; summits).
{avoid}
Reply with ONLY a JSON object (no markdown fences, no commentary) in exactly this shape:

{{
  "cover": {{
    "inbrief_1": "max 35 characters, ultra-short cover label teasing THIS geopolitics story"
  }},
  "geopolitics": {{
    "kicker": "max 30 characters, e.g. India x China or India | Trade",
    "headline": "max 60 characters, magazine headline for the story",
    "paragraphs": [
      "paragraph 1, 3-4 sentences, what is happening, with real names, dates and numbers",
      "paragraph 2, 3-4 sentences, what is still unsettled and why it matters for business"
    ],
    "world_60": [
      "max 90 characters, one-line world headline with a money angle",
      "max 90 characters, another one",
      "max 90 characters, another one",
      "max 90 characters, another one"
    ]
  }}
}}

Rules:
- cover.inbrief_1 sits on the cover and links to this page, so it MUST be about the SAME
  story as the geopolitics headline and paragraphs - name the same country, leader or deal.
- "world_60" is a quick 4-item round-up of other real global headlines of the last day or two
  (oil, gold, bonds, central banks, global markets, conflicts), different from the main story.
- Tone: a smart college finance magazine - plain English, no jargon dumps, Indian angle.
- Every string must be plain text. No HTML tags, no markdown, no links.
- Use the actual ₹ and $ characters (not HTML entities) where amounts appear.
"""

STOPWORDS = {"with", "from", "that", "this", "into", "over", "amid", "after", "about",
             "their", "they", "what", "will", "than", "more", "near", "nears", "talks",
             "deal", "visit", "india", "indian", "india's", "global", "world", "trade"}


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
    """Per-attempt check for the geopolitics call: the cover teaser must share at
    least one real keyword with the story it links to. Returns an error string
    (so the next model/grounding option is tried) or None if it looks consistent."""
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
    """Run one prompt through the model fallbacks (grounding on, then off).
    If a check function is given and it returns an error string, that answer is
    discarded and the next option is tried.
    Returns parsed JSON dict, or None if every attempt failed."""
    last_err = None
    for model in MODELS:
        for use_grounding in (True, False):
            try:
                print("Trying %s with model %s (grounding: %s)..."
                      % (label, model, "on" if use_grounding else "off"))
                result = call_gemini(api_key, model, use_grounding, prompt)
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
                # 400/404/429 etc: try the next option
            except (RuntimeError, ValueError, urllib.error.URLError, TimeoutError) as e:
                last_err = "%s: %s" % (model, e)
                print("  " + str(last_err))
    print("All Gemini attempts for %s failed. Last error: %s" % (label, last_err))
    return None


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
    """Hard-fail on anything that would break the page layout. Only shape and
    length are checked here; the page itself also ignores missing/extra fields."""
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


def main():
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        fail("GEMINI_API_KEY is not set. Add it as a repository secret (see README step 4).")

    last_close = TODAY - timedelta(days=1)
    while last_close.weekday() >= 5:  # skip weekends for the "close of" label
        last_close -= timedelta(days=1)
    close_label = (last_close.strftime("%b %-d").upper() if os.name != "nt"
                   else last_close.strftime("%b %d").upper().replace(" 0", " "))
    today_str = TODAY.strftime("%A, %d %B %Y")

    features_prompt = FEATURES_PROMPT.format(today=today_str)
    markets_prompt = MARKETS_PROMPT.format(
        today=today_str,
        month_label=TODAY.strftime("%b %Y").upper(),
        close_label=close_label,
    )

    features = generate(api_key, features_prompt, "features (big story, explains, venture vault)")
    if features is None:
        fail("could not generate the features package - leaving data.json untouched.")
    markets = generate(api_key, markets_prompt, "markets (market watch, daily brief)")
    if markets is None:
        fail("could not generate the markets package - leaving data.json untouched.")

    # geopolitics runs last so it can steer clear of stories already used today
    taken = []
    for s in ((markets.get("daily_brief") or {}).get("story_1"),
              (markets.get("daily_brief") or {}).get("story_2")):
        if isinstance(s, dict) and isinstance(s.get("headline"), str):
            taken.append(s["headline"])
    bs = features.get("big_story")
    if isinstance(bs, dict) and isinstance(bs.get("headline"), str):
        taken.append(bs["headline"])
    avoid = ""
    if taken:
        avoid = ("\nOther pages of today's issue already cover these stories - pick a DIFFERENT one:\n"
                 + "\n".join("- " + t for t in taken) + "\n")
    geo_prompt = GEOPOLITICS_PROMPT.format(today=today_str, avoid=avoid)
    geo = generate(api_key, geo_prompt, "geopolitics (geopolitics page, in brief 01)",
                   check=check_geopolitics_pkg)
    if geo is None:
        fail("could not generate the geopolitics package - leaving data.json untouched.")

    # merge both packages into one data.json
    data = {
        "cover": {},
        "big_story": features.get("big_story"),
        "explains": features.get("explains"),
        "venture_vault": features.get("venture_vault"),
        "market_watch": markets.get("market_watch"),
        "daily_brief": markets.get("daily_brief"),
        "geopolitics": geo.get("geopolitics"),
    }
    for src in (features, markets, geo):
        c = src.get("cover")
        if isinstance(c, dict):
            data["cover"].update(c)

    validate(data)

    # keep only the fields the site uses, in a stable order
    out = {"updated_ist": TODAY.strftime("%Y-%m-%d")}
    out.update(data)
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, DATA_FILE)
    print("Wrote %s for %s" % (DATA_FILE, out["updated_ist"]))


if __name__ == "__main__":
    main()
