# FINTRIX - daily auto-updating magazine

This site updates its **Market Watch** and **Daily Brief** sections by itself
every morning, using Google's free Gemini AI. Everything here is free: GitHub
hosts the site, GitHub Actions runs the daily update, and the Gemini API free
tier writes the content.

## The files

| File | What it does |
|---|---|
| `index.html` | The magazine itself. Do not edit the marked daily sections by hand. |
| `data.json` | Today's Market Watch and Daily Brief content. The robot rewrites this file daily. |
| `generate_data.py` | The script that asks Gemini for new content and writes `data.json`. |
| `.github/workflows/daily-update.yml` | Tells GitHub to run the script every day at 9:00 AM IST. |

## Setup (about 15 minutes, no coding needed)

**1. Create a GitHub account** at https://github.com if you don't have one.

**2. Create a new repository**
   - Click the **+** (top right) > **New repository**.
   - Name it anything, e.g. `fintrix`. Leave it **Public** (required for free hosting).
   - Click **Create repository**.

**3. Upload the files**
   - On your new repo page, click **uploading an existing file**.
   - Drag in `index.html`, `data.json`, `generate_data.py`, and the whole
     `.github` folder (it must keep the exact path
     `.github/workflows/daily-update.yml`).
   - Click **Commit changes**.

**4. Get a free Gemini API key**
   - Go to https://aistudio.google.com/apikey and sign in with a Google account.
   - Click **Create API key** and copy it. It looks like `AIza...`.

**5. Save the key as a secret in your repo**
   - In your repo, go to **Settings** > **Secrets and variables** > **Actions**.
   - Click **New repository secret**.
   - Name: `GEMINI_API_KEY` (exactly this, all caps).
   - Value: paste the key. Click **Add secret**.

**6. Turn on GitHub Pages (the free hosting)**
   - In your repo, go to **Settings** > **Pages**.
   - Under **Source**, pick **Deploy from a branch**.
   - Under **Branch**, pick **main** and folder **/ (root)**, then **Save**.
   - Wait 2-3 minutes. Your site appears at
     `https://<your-username>.github.io/<repo-name>/`.

**7. Test the daily updater once by hand**
   - Go to the **Actions** tab in your repo.
   - Click **Update Market Watch and Daily Brief** on the left, then
     **Run workflow** > **Run workflow**.
   - After about a minute it should show a green tick. Open your site -
     Market Watch and Daily Brief will show fresh content.

Done. From now on it updates itself every day at 9:00 AM IST.

## Good to know

- **If a day's update fails** (API hiccup, rate limit, odd answer), nothing is
  published - the site simply keeps showing the previous day's content and
  tries again the next morning. You can see what happened in the Actions tab.
- **Free tier limits:** the Gemini free tier allows a limited number of
  requests per day. This setup uses 1-2 requests a day, far below the limit.
  The script also retries with backup models automatically.
- **The AI writes the news:** Gemini summarizes real market data and news
  (it uses Google Search grounding), but it can occasionally get a number
  wrong. Worth a glance at the site in the morning if it is going out to a
  big audience that day.
- **To change the update time**, edit the `cron:` line in
  `.github/workflows/daily-update.yml`. `30 3 * * *` means 03:30 UTC = 9:00 AM IST.
- **To change which AI model writes it**, add a repo variable named
  `GEMINI_MODELS` with a model name - the default list already covers the
  current free-tier models.
