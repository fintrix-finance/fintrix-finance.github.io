"""Create ONE Brevo campaign DRAFT for today's FINTRIX issue. Never sends.
Uses only the campaign-create and campaign-list endpoints. No scheduledAt, no send call."""
import json, os, sys, urllib.request, datetime

API = "https://api.brevo.com/v3"
KEY = os.environ["BREVO_API_KEY"]
LIST_ID = int(os.environ["BREVO_LIST_ID"])

def call(method, path, body=None):
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(body).encode() if body else None,
        headers={"api-key": KEY, "content-type": "application/json", "accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}

ist = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
today = ist.strftime("%Y-%m-%d")
issue = json.load(open("data.json")).get("updated_ist", "")

if issue != today:
    sys.exit(f"Issue on disk is {issue or 'none'}, not {today}. No draft created.")
if ist.weekday() >= 5:
    sys.exit("Weekend. No draft (market days only).")

name = f"FINTRIX issue {today}"
existing = call("GET", "/emailCampaigns?limit=50&sort=desc")
if any(c.get("name") == name for c in existing.get("campaigns", [])):
    sys.exit(f"Draft '{name}' already exists. Nothing to do.")

html = """<div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;color:#111">
<p>Hi,</p>
<p>Your latest FINTRIX issue is ready.</p>
<p><a href="https://fintrix-finance.github.io/">Read the issue</a></p>
<p>Markets, commodities, funds and the stories behind the numbers, in one place.</p>
<p><strong>FINTRIX</strong></p>
<p style="font-size:12px;color:#666">You're receiving this because you subscribed to FINTRIX updates.
<a href="{{ unsubscribe }}">Unsubscribe</a><br>129 sector 16A, Chandigarh 160015</p>
</div>"""

res = call("POST", "/emailCampaigns", {
    "name": name,
    "subject": "FINTRIX | Your market-day issue is ready",
    "sender": {"name": "FINTRIX", "email": "mahleenkw@gmail.com"},
    "replyTo": "mahleenkw@gmail.com",
    "recipients": {"listIds": [LIST_ID]},
    "htmlContent": html,
})
print(f"Draft created: {name} (campaign id {res.get('id')}). Not sent.")
