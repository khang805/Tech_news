# Tech Intelligence: Email + Website, Free

Every day a GitHub Action collects tech news from RSS feeds, labels each story **High Impact** or **Medium & Low Impact** (free Gemini AI, with rules as backup), and then:

- emails the **daily**, **weekly** and **monthly** digest to one or many addresses
- emails a separate **High Impact alert** for each new high-impact story
- updates the **website** (hosted free on Vercel) with the last 30 days of stories
- keeps everything in plain JSON files in this repository. No database is needed.

Each story has **one line** (the headline summary) and **one paragraph** (the detail), both copied from the source text. The AI never writes article text.

---

## 1. How the pieces fit

```
GitHub Actions (free, scheduled daily)
   -> collects RSS feeds -> labels impact with Gemini -> sends emails (Gmail)
   -> writes data/articles.json and docs/data/articles.json -> commits to GitHub
                                                       |
                       Vercel (free) redeploys docs/ -> your website
```

| Path | Purpose |
|---|---|
| `config/feeds.yaml` | Feed list |
| `config/settings.yaml` | Recipients, categories (NVIDIA first), limits, AI settings |
| `data/articles.json` | Full store: last 30 days plus duplicate-tracking IDs |
| `docs/index.html`, `docs/data/articles.json` | Website files (Vercel serves `docs/`) |
| `vercel.json` | Tells Vercel to serve the `docs` folder |
| `.github/workflows/daily_collect.yml` | Daily, weekly and monthly schedule |
| `src/newsintel/` | Python code |

---

## 2. Get your keys and accounts

### a) Gmail App Password (for sending email)
1. Open https://myaccount.google.com > **Security** and turn on **2-Step Verification**.
2. Search for **App passwords** (or go to https://myaccount.google.com/apppasswords).
3. Create one named `NewsIntel` and copy the 16-character code. Keep it private.

### b) Gemini API key (free AI labels)
1. Open https://aistudio.google.com and sign in with your Google account.
2. Click **Get API key** > **Create API key**. Copy it.
3. It is free within the free-tier limits (no billing needed).

### c) Groq API key (optional backup AI, free)
1. Open https://console.groq.com, sign up, go to **API Keys**, create one.

### d) GitHub account and Vercel account (free)
- GitHub: https://github.com (sign up)
- Vercel: https://vercel.com (sign up with GitHub)

---

## 3. Where to put the keys

| Key | Local (VS Code terminal) | GitHub Actions (online) |
|---|---|---|
| `SMTP_USERNAME` (your Gmail) | `$env:SMTP_USERNAME = "you@gmail.com"` | Secret |
| `SMTP_PASSWORD` (App Password) | `$env:SMTP_PASSWORD = "xxxx xxxx xxxx xxxx"` | Secret |
| `GEMINI_API_KEY` | `$env:GEMINI_API_KEY = "AIza..."` | Secret |
| `GROQ_API_KEY` (optional) | `$env:GROQ_API_KEY = "gsk_..."` | Secret |
| `EMAIL_TO` (optional, comma-separated) | `$env:EMAIL_TO = "a@x.com,b@y.com"` | Secret |
| `VERCEL_DEPLOY_HOOK` (optional) | not needed | Secret (see step 6) |

**Add GitHub secrets:** your repository > **Settings** > **Secrets and variables** > **Actions** > **New repository secret**. Enter the name exactly as shown (uppercase, underscores) and paste the value.

Never paste keys into code or into `settings.yaml`. The `.gitignore` file already excludes `.env` files.

---

## 4. Run it on your computer (VS Code, Windows PowerShell)

1. Install **Python 3.11+** (python.org, tick "Add to PATH") and the **Python** extension in VS Code.
2. **File > Open Folder** > `news-intel`.
3. **Terminal > New Terminal**, then:

```powershell
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pip install -e .
```

If activation is blocked: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then try again.

4. Test with the built-in sample feed (no internet, no email):
```powershell
python -m newsintel --fixture tests/fixtures/sample_feed.xml --ignore-age --dry-run --no-ai --verbose
```
5. Run the real feeds and save data (no email):
```powershell
python -m newsintel --no-email --verbose
```
6. Set your keys for this terminal session, then send the emails:
```powershell
$env:SMTP_USERNAME = "abdurrahmank084@gmail.com"
$env:SMTP_PASSWORD = "your-app-password"
$env:GEMINI_API_KEY = "your-gemini-key"
python -m newsintel --digest --period day
```
7. View the website locally. Run this in a second terminal and open http://localhost:8000:
```powershell
python -m http.server 8000 --directory docs
```
8. Run the tests: `pytest -q`

**Command options:** `--period day|week|month` (digest window), `--no-ai` (skip Gemini), `--no-email` (save only), `--dry-run` (no writes, no email), `--feed "NAME"` (one feed), `--fixture FILE` (local XML), `--ignore-age`, `--verbose`.

---

## 5. Put it on GitHub

In the project folder:

```bash
git init
git add .
git commit -m "Tech intelligence project"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/news-intel.git
git push -u origin main
```

(Create the empty `news-intel` repository on github.com first, without a README. If Git asks for a password, use a Personal Access Token from GitHub > Settings > Developer settings.)

Then:
1. **Settings > Actions > General > Workflow permissions**: choose **Read and write permissions** and save. The workflow needs this to commit the data.
2. Add the secrets from section 3: `SMTP_USERNAME`, `SMTP_PASSWORD`, `GEMINI_API_KEY`, and optionally `GROQ_API_KEY` and `EMAIL_TO`.
3. **Actions** tab > **Tech news collector** > **Run workflow**. Choose `day` first and check your inbox. Run `week` or `month` later to test those digests.

**Schedule (UTC):** every day at 01:00 (06:00 Pakistan), every Sunday (weekly digest), and the 1st of each month (monthly digest).

---

## 6. Put the website on Vercel (free)

1. Sign in at https://vercel.com with GitHub.
2. **Add New > Project**, then import your `news-intel` repository.
3. Leave the settings as they are. Framework: **Other**. Build command: empty. Output directory: `docs` (already set in `vercel.json`). Click **Deploy**.
4. You get a URL such as `https://news-intel-xxxx.vercel.app`. Each commit from the daily workflow redeploys it automatically.

**Optional backup:** in Vercel, open your project > **Settings** > **Git** > **Deploy Hooks**. Create a hook named `daily`, copy the URL, and add it as the GitHub secret `VERCEL_DEPLOY_HOOK`. The workflow then calls it after each data update.

**Privacy:** the website is public. Anyone with the link can read the news, but not your email. If the repository is public, your recipient address is visible in `settings.yaml`. To hide it, delete the address there and use the `EMAIL_TO` secret.

---

## 7. Where the data lives (JSON, no database)

- `data/articles.json` holds articles from the last **30 days**, plus IDs of recently seen articles (to avoid duplicates). Old articles are removed automatically.
- `docs/data/articles.json` is the copy the website reads.
- Size estimate: roughly 150 to 300 new stories a day, about 1 to 2 KB each. The file stays around 5 to 15 MB. Git history grows by roughly the same amount per day as the file changes, so the repository will reach a few hundred MB after a year. GitHub recommends repositories under 1 GB.
- **Do you need a database?** Not for this. JSON is enough for one user and 30 days of news, and it costs nothing. Consider a free database (Neon or Supabase PostgreSQL) only if you want search across years, several separate user accounts, or the repository grows beyond about 500 MB. Moving later is straightforward because the code only reads and writes one file.

---

## 8. Free-tier limits

- **Gemini:** free-tier requests per minute and per day apply and can change. The collector makes one request per 25 new stories and one per weekly or monthly digest, pausing 4 seconds between calls. If the limit is reached, the run uses rule-based levels and logs a warning. Limits: https://ai.google.dev/gemini-api/docs/rate-limits. If a model name stops working, change `gemini_model` in `settings.yaml`.
- **GitHub Actions:** unlimited minutes for public repositories; 2,000 minutes a month for private ones. Each run takes a few minutes.
- **GitHub schedules** may start a few minutes late. A public repository's schedule pauses after 60 days with no commits.
- **Vercel Hobby plan:** free for personal, non-commercial use. Deployments and bandwidth are well within the limits for a personal site.
- **Gmail:** about 500 emails a day for a personal account. This project sends about 3 to 12 a day, more with several recipients.

---

## 9. Troubleshooting

| Message | Fix |
|---|---|
| `SMTP login failed` | Use the 16-character App Password (not your Gmail password) in `SMTP_PASSWORD`. |
| `email not configured` | `SMTP_USERNAME` or `SMTP_PASSWORD` is missing. Add it locally or as a GitHub secret. |
| `AI impact labels unavailable` | Check `GEMINI_API_KEY`, or the free quota may be used up. Rule-based levels are used instead. |
| `feed failed ... http_404` | The feed URL changed. Fix it in `feeds.yaml` or set `enabled: false`. |
| Website says "Could not load data" | Open it through the Vercel URL or `python -m http.server`. Double-clicking `index.html` does not work. |
| Workflow error `Permission denied` on push | Set workflow permissions to **Read and write** (section 5). |
| Vercel site did not update | Check the Actions log for "Vercel redeploy requested", or redeploy from the Vercel dashboard. |
| `ModuleNotFoundError: newsintel` | Run `pip install -e .` inside the activated `.venv`. |

---

## 10. Tests

`pytest -q` runs 44 tests offline: links, cleaning, scoring, duplicates, storage and recovery, one-line/paragraph rules, feed parsing, retries, multi-recipient email, digest groups, AI fallback, and the day/week/month windows.

## 11. Check Repositry size

curl -s https://api.github.com/repos/khang805/Tech_news | grep '"size"' | awk -F': ' '{printf "Repository size: %.1f MB\n", $2/1024}'