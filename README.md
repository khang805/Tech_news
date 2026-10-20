# Tech News

A free daily tech news collector.

- **Collects** stories from RSS feeds every day (GitHub Actions).
- **Stores** the last 30 days of stories in **Supabase** (free PostgreSQL).
- **Emails** a daily digest, a weekly digest (Sunday) and a monthly digest (1st of the month) through Gmail.
- **Shows** the stories on a website hosted on **Vercel** (or GitHub Pages). The page reads the stories from Supabase.

No server runs all the time. GitHub Actions runs the collector, Supabase stores the data, and the website is static.

---

## How the system fits together

| Part | Where it runs | What it does |
|---|---|---|
| Collector | GitHub Actions, once a day at 01:00 UTC (06:00 Pakistan) | Fetches feeds, labels impact, sends email, writes to Supabase, rebuilds `docs/index.html` |
| Database | Supabase (free) | Stores articles, seen IDs, and the last run time |
| Email | Gmail (SMTP) | Sends the digests to every recipient |
| AI labels | Google Gemini (free), Groq as backup | Labels High or Medium/Low impact, and picks important stories for weekly and monthly digests |
| Website | Vercel (or GitHub Pages) | Serves `docs/index.html`. The page reads stories from Supabase when it loads |

**Important:** a daily run does not change the website, so it does not trigger a new deployment. The stories reach visitors through Supabase, not through a new build.

---

## Part 1: Create the Supabase database

1. Go to https://supabase.com, sign up, and click **New project**.
2. Enter a name, set a database password (save it), choose the region closest to you, and click **Create new project**. Wait about two minutes.
3. In the left sidebar, click **SQL Editor**, then **New query**. Paste the SQL below and click **Run**. It should say "Success. No rows returned."

```sql
create table if not exists articles (
  id text primary key,
  published_utc timestamptz not null,
  data jsonb not null
);
create index if not exists articles_published_idx on articles (published_utc desc);

create table if not exists seen_ids (
  id text primary key,
  added_utc timestamptz not null
);

create table if not exists meta (
  key text primary key,
  value jsonb
);

alter table articles enable row level security;
alter table seen_ids enable row level security;
alter table meta enable row level security;

create policy "public read articles" on articles for select to anon using (true);
create policy "public read meta" on meta for select to anon using (true);
```

`seen_ids` has no public policy, so visitors cannot read it.

---

## Part 2: Get the Supabase keys

**Project URL**
1. In the Supabase dashboard, open the project.
2. In the left sidebar, under **INTEGRATIONS**, click **Data API**.
3. Copy **Project URL**, for example `https://abcdefghijklmnop.supabase.co`.

**Anon and service_role keys**
1. Click the gear icon (**Project Settings**) at the bottom of the sidebar, then **API Keys**.
2. Click the tab **Legacy anon, service_role API keys**.
3. Copy the **anon** key (starts with `eyJ...`).
4. Copy the **service_role** key (starts with `eyJ...`; click the reveal button first). It can write to your database, so keep it private.

If the Legacy tab is missing, tell the project maintainer. The code can be changed to use the newer publishable and secret keys.

---

## Part 3: Get the Gmail App Password

Gmail does not accept your normal password from scripts.

1. Go to https://myaccount.google.com and open **Security**.
2. Turn on **2-Step Verification** if it is not already on.
3. Go to https://myaccount.google.com/apppasswords (or search for "App passwords").
4. Create one named `NewsIntel`. Copy the 16-character code. Keep it private.

This password belongs to the account in `SMTP_USERNAME`. The emails are sent from that account.

---

## Part 4: Get the Gemini API key (free)

1. Go to https://aistudio.google.com and sign in.
2. Click **Get API key**, then **Create API key**.
3. Copy the key. It is free within the free-tier limits.

Optional backup: create a Groq key at https://console.groq.com under **API Keys**.

---

## Part 5: Add the GitHub secrets

1. Open the repository on GitHub, then **Settings > Secrets and variables > Actions**.
2. Click **New repository secret** for each row below. Names are case-sensitive.

| Secret name | Value | Required |
|---|---|---|
| `SMTP_USERNAME` | The Gmail address that sends the emails | Yes |
| `SMTP_PASSWORD` | The 16-character App Password (Part 3) | Yes |
| `GEMINI_API_KEY` | The Gemini key (Part 4) | Recommended |
| `GROQ_API_KEY` | The Groq key | Optional |
| `SUPABASE_URL` | Project URL (Part 2) | Yes |
| `SUPABASE_ANON_KEY` | anon key (Part 2) | Yes |
| `SUPABASE_SERVICE_KEY` | service_role key (Part 2) | Yes |
| `EMAIL_TO` | Recipient addresses, comma-separated | Optional (see Part 9) |

Delete any old secret named `VERCEL_DEPLOY_HOOK`. It is no longer used.

---

## Part 6: Set the repository permissions

1. Go to **Settings > Actions > General**.
2. Under **Workflow permissions**, select **Read and write permissions** and click **Save**.

The workflow needs this to commit the website file.

---

## Part 7: Host the website on Vercel

The site is the `docs` folder. Vercel must build only that folder.

1. Sign in at https://vercel.com with your GitHub account.
2. Click **Add New > Project**, find the repository, and click **Import**.
3. On the setup screen:
   - **Root Directory:** click **Edit**, enter `docs`, and confirm.
   - **Framework Preset:** Other.
   - **Build Command, Output Directory, Install Command:** leave empty, with no overrides.
4. Click **Deploy**.

The file `docs/vercel.json` already tells Vercel not to build when nothing in `docs` changed, so the daily runs do not trigger deployments.

If the Root Directory is not set to `docs`, the build fails with `PYTHON_ENTRYPOINT_NOT_FOUND`, because Vercel sees the Python files in the root. Check the setting under **Settings > Build and Deployment**.

**Optional: change the project name** under **Settings > General**. This changes the address to `https://YOUR-NAME.vercel.app`.

### Alternative: GitHub Pages

If you prefer no Vercel project:
1. Go to **Settings > Pages**.
2. Set **Source** to **Deploy from a branch**, **Branch** to `main`, and the folder to `/docs`. Save.
3. The site is at `https://YOUR-USERNAME.github.io/REPOSITORY-NAME/`.

Use only one of Vercel or GitHub Pages, not both.

---

## Part 8: First run and data migration

If you have an old `data/articles.json` file from before Supabase, the first run imports it automatically.

1. Make sure `data/articles.json` is still committed in the repository. Do not remove it yet.
2. Go to **Actions > Tech news collector > Run workflow**, leave the defaults, and click **Run workflow**.
3. Open the run. In the step **Collect, label impact, send email, save to database, build website**, look for:
   - `migrating N articles` (the old file was imported)
   - `run complete`
4. Check the database in Supabase: **SQL Editor** > run `select count(*) from articles;`.
5. After the count matches, remove the old file from Git (keep a backup on your computer first):

```bash
git rm -r --cached data docs/data
git commit -m "Remove old JSON storage"
git pull --rebase origin main
git push origin main
```

If there is no old file, the first run simply starts with an empty database.

---

## Part 9: Set the email recipients

You can send to one or many addresses. Each address receives its own message, so recipients cannot see each other.

**Option A (recommended): GitHub secret.** Keeps addresses out of the public repository.
1. Add or edit the secret `EMAIL_TO`.
2. Enter all addresses separated by commas, for example `first@gmail.com,second@gmail.com`.

**Option B: settings file.** In `config/settings.yaml`:

```yaml
email:
  to:
    - "first@gmail.com"
    - "second@gmail.com"
  subject_prefix: "[Tech News]"
```

If `EMAIL_TO` is set, it overrides the list in the settings file.

**Sender:** emails are sent from the `SMTP_USERNAME` account. Gmail allows about 500 messages a day for a personal account.

---

## Part 10: Change the name

The name appears in three places:

1. `config/settings.yaml`: `subject_prefix: "[Tech News]"`
2. `src/newsintel/site.py`: the `<title>` and the `<h1>` inside `TEMPLATE`
3. `README.md`: the first line

The website name changes after the next workflow run rebuilds `docs/index.html`.

---

## Part 11: Daily operation and schedule

### When things run

| Time (UTC) | Time (Pakistan) | What runs |
|---|---|---|
| 01:00 every day | 06:00 | Collector and digest |

The digest type is chosen by date:
- **1st of the month:** monthly digest (last 30 days, up to 25 stories)
- **Sunday:** weekly digest (last 7 days, up to 20 stories)
- **Any other day:** daily digest (last 24 hours, up to 15 stories)

Each day sends exactly one digest, to every recipient.

GitHub may start a run a few minutes late, and occasionally much later when its servers are busy.

### Check that the schedule works

1. Go to **Actions > Tech news collector**.
2. Filter by **Event: schedule** to see only scheduled runs.
3. Open the newest run and check that the collector step ends with `run complete`, and the email line says `emailed N recipient(s)`.

### Test without waiting

1. Go to **Actions > Tech news collector > Run workflow**.
2. Tick **test_email** and click **Run workflow**. You should receive a test message within a few minutes.

Manual digest runs send an email too. Choose `day`, `week`, or `month` in the dropdown. Be careful with `month`, because it sends a full monthly digest immediately.

### Keep the schedule active

GitHub pauses scheduled workflows in public repositories after 60 days with no repository activity. A daily run that changes nothing in Git does not count. To avoid that, the workflow can commit a small heartbeat file each day (see `status/heartbeat.log` in the workflow's optional step). If the schedule is paused, GitHub shows a banner on the Actions page, and you can click **Enable workflow**.

---

## Part 12: Run locally (optional)

Use this for testing on your computer.

**Windows PowerShell**
```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pip install -e .
pytest -q
```

**Linux, macOS, or Fedora**
```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pip install -e .
pytest -q
```

**Run without changing any data:**
```bash
python -m newsintel --dry-run --no-ai --verbose
```

**Run and save locally (no email):**
```bash
python -m newsintel --no-email --no-ai
```

Without the Supabase variables, the collector saves to `data/articles.json` on your computer.

**Send a test email locally:**
```powershell
$env:SMTP_USERNAME = "you@gmail.com"
$env:SMTP_PASSWORD = "your-app-password"
python -m newsintel --test-email
```

**Preview the website locally:** the page reads Supabase, so set the URL and anon key first:
```powershell
$env:SUPABASE_URL = "https://YOUR-PROJECT.supabase.co"
$env:SUPABASE_ANON_KEY = "your-anon-key"
python -m newsintel --no-email --no-ai
python -m http.server 8000 --directory docs
```
Then open http://localhost:8000.

Never commit `.venv`, `data/`, `logs/`, or any file containing a key. `.gitignore` already excludes them.

---

## Part 13: Add, disable, or fix a feed

Feeds are listed in `config/feeds.yaml`. Each entry has a name, URL, category, priority, and an `enabled` flag.

```yaml
  - name: "My source"
    url: "https://example.com/feed.xml"
    category: "NLP & LLMs"
    source_priority: 3
    enabled: true
```

- To turn a feed off, set `enabled: false`.
- Google News search feeds (`news.google.com/rss/search?q=...`) collect coverage from many outlets and need no key.
- Test one feed locally:
```powershell
  python -m newsintel --feed "NAME OF FEED" --dry-run --no-ai --verbose
```

Feeds that fail are skipped and the run continues. The failure appears in the log, and in the digest footer as `Feeds that failed`.

---

## Part 14: Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Run is red, step **Commit website** shows `rejected (fetch first)` | Remote has commits the run lacks (usually a manual push) | Fix permissions (Part 6). Run the workflow again. |
| Run is red, `DIGEST EMAIL WAS NOT SENT` | Missing or wrong SMTP secret, or Gmail rejected the login | Check `SMTP_USERNAME` and `SMTP_PASSWORD`. Use an App Password, not your normal password. |
| `email not configured` in the log | `SMTP_USERNAME` or `SMTP_PASSWORD` is missing | Add the secret (Part 5). |
| `SMTP login failed` | Wrong App Password, or 2-Step Verification is off | Create a new App Password (Part 3). |
| `could not read storage` or `could not save data` | Wrong `SUPABASE_URL` or key, or the tables are missing | Check the secrets (Part 5), and run the SQL in Part 1. |
| Website says "not connected to its database" | Supabase secrets were missing when the page was built | Add the secrets, then run the workflow again so the page is rebuilt. |
| Website says "Could not load the stories" | Policies missing in Supabase, or wrong anon key | Re-run the SQL in Part 1 and check `SUPABASE_ANON_KEY`. |
| Vercel build fails with `PYTHON_ENTRYPOINT_NOT_FOUND` | Root Directory is not `docs` | Set it under Build and Deployment (Part 7). |
| Vercel emails about failed deployments | Same cause as above | Fix the Root Directory. |
| Many feeds fail with HTTP 503 | Google News rate limit | Temporary. The collector spaces requests and retries automatically. |
| Some feed fails with HTTP 403, 404, 410, or `invalid_xml` | Feed was moved, removed, or blocks automated access | Update or disable it (Part 13). |
| Scheduled runs stopped | 60-day pause, or the workflow was disabled | Click **Enable workflow** on the Actions page. |
| Supabase project paused | Free projects pause after about a week without activity | Click **Restore** in the Supabase dashboard. |

---

## Part 15: Free-tier limits

| Service | Limit | What it means here |
|---|---|---|
| GitHub Actions | Unlimited for public repositories; 2,000 minutes a month for private | One run takes a few minutes a day |
| GitHub repository | About 1 GB recommended | Daily runs commit almost nothing, so it grows very slowly |
| Supabase database | 500 MB storage | About 15 MB needed for 30 days |
| Supabase egress | 5 GB a month | Each visit downloads about 5 to 8 MB; about 600 to 1,000 visits a month |
| Supabase projects | Paused after about a week of inactivity | The daily run keeps the project active |
| Gmail | About 500 messages a day for a personal account | A few messages a day per recipient |
| Gemini | Requests per minute and per day (changes over time) | The collector pauses between calls and falls back to rule-based labels if the quota is reached |
| Vercel Hobby | Personal, non-commercial use | Fine for this project |

Check the current limits on each provider's pricing or limits page, because they change over time.

---

## Project files

| Path | Purpose |
|---|---|
| `config/feeds.yaml` | Feed list |
| `config/settings.yaml` | Limits, categories, email recipients, subject prefix, AI settings |
| `src/newsintel/` | Python code: collection, AI labels, digests, storage, website builder |
| `src/newsintel/supabase_store.py` | Reads and writes Supabase |
| `src/newsintel/store.py` | Chooses Supabase or local storage |
| `src/newsintel/site.py` | Builds `docs/index.html` |
| `docs/index.html` | The website (generated) |
| `docs/vercel.json` | Vercel settings for the website |
| `docs/.nojekyll` | Tells GitHub Pages not to process the files |
| `.github/workflows/daily_collect.yml` | Daily, weekly, and monthly schedule |
| `tests/` | Automated tests (`pytest -q`) |
