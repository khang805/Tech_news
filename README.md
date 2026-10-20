# Tech News

A free daily tech news collector. Every day it reads RSS feeds, writes a one-paragraph summary for each new story with Gemini, and sends you a digest by email. A website shows the stories, and they are stored in Supabase.

- **Email:** a daily digest (15 stories), a weekly digest on Sundays (20 stories), and a monthly digest on the 1st (25 stories). Each recipient gets their own copy.
- **Website:** the last 30 days of stories, with filters for period, impact, and category.
- **Free:** GitHub Actions runs the collector, Supabase stores the data, GitHub or Vercel hosts the site, and Gmail sends the email.

---

## How it works

| Part | Where it runs | What it does |
|---|---|---|
| Collector | GitHub Actions, daily at 01:00 UTC (06:00 Pakistan) | Fetches feeds, removes duplicates, labels impact, writes summaries, sends email, saves to the database |
| Database | Supabase (free PostgreSQL) | Holds the last 30 days of stories, the list of seen story IDs, and the last run time |
| AI | Google Gemini (free tier), Groq as a backup | Labels each story High or Medium/Low, writes its one-paragraph summary, and picks the important stories for the weekly and monthly digests |
| Email | Gmail (SMTP) | Sends the digests and the test email to every recipient |
| Website | GitHub Pages or Vercel | Serves `docs/index.html`, which reads stories from Supabase in the browser |

**Daily runs do not change the website files,** so they do not trigger a new deployment. Visitors see new stories because the page reads them from Supabase when it loads.

### Where each choice comes from

| Decision | Preferred | Backup |
|---|---|---|
| High or Medium/Low impact | Gemini | Rule-based score (0 to 100), with 70 or more = High |
| One-paragraph summary | Gemini, from the feed text | The feed text itself, cut to one paragraph |
| Weekly and monthly picks | Gemini chooses up to 20 or 25 | Top stories by rule-based score |
| Daily digest order | Rule-based score (always) | None needed |

If a Gemini batch fails, only that batch uses the backup. Other batches still use Gemini.

---

## Setup

Follow these steps in order.

### 1. Create the Supabase database

1. Sign up at https://supabase.com and click **New project**. Choose a database password and the region closest to you. Wait about two minutes.
2. Open **SQL Editor > New query**, paste the SQL below, and click **Run**. It should say "Success. No rows returned."

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

### 2. Get the Supabase keys

- **Project URL:** in the sidebar, under **INTEGRATIONS**, click **Data API**. Copy the URL (for example `https://abcdefghijklmnop.supabase.co`).
- **anon and service_role keys:** click the gear icon (**Project Settings**), then **API Keys**, then the tab **Legacy anon, service_role API keys**. Copy the **anon** key and the **service_role** key. Keep the service_role key private.

### 3. Get the other keys

- **Gmail App Password:** in your Google Account, turn on **2-Step Verification**, then go to **App passwords**, create one named `NewsIntel`, and copy the 16-character code.
- **Gemini API key:** at https://aistudio.google.com, click **Get API key** and copy it. It is free within the free-tier limits.
- **Groq API key (optional):** at https://console.groq.com, create a key under **API Keys**.

### 4. Add the GitHub secrets

Open the repository, then **Settings > Secrets and variables > Actions > New repository secret**. Names are case-sensitive.

| Secret | Value | Required |
|---|---|---|
| `SMTP_USERNAME` | Gmail address that sends the emails | Yes |
| `SMTP_PASSWORD` | Gmail App Password | Yes |
| `GEMINI_API_KEY` | Gemini key | Recommended |
| `GROQ_API_KEY` | Groq key | Optional |
| `SUPABASE_URL` | Project URL | Yes |
| `SUPABASE_ANON_KEY` | anon key | Yes |
| `SUPABASE_SERVICE_KEY` | service_role key | Yes |
| `EMAIL_TO` | Recipient addresses, separated by commas | Optional |

### 5. Set the workflow permissions

Go to **Settings > Actions > General**, choose **Read and write permissions** under **Workflow permissions**, and click **Save**.

### 6. Host the website

**Option A: Vercel (recommended if you use Vercel)**
1. Import the repository at https://vercel.com (**Add New > Project**).
2. Set **Root Directory** to `docs`. Leave the build, output, and install commands empty.
3. Click **Deploy**.

The file `docs/vercel.json` skips builds when `docs` is unchanged.

**Option B: GitHub Pages**
1. Go to **Settings > Pages**.
2. Set **Source** to **Deploy from a branch**, **Branch** to `main`, and the folder to `/docs`. Click **Save**.
3. The site is at `https://YOUR-USERNAME.github.io/REPOSITORY-NAME/`.

Use only one of the two options.

### 7. Run the first collection

1. Go to **Actions > Tech news collector > Run workflow**, leave the defaults, and click **Run workflow**.
2. Open the run and check the step **Collect, label impact, send email, save to database, build website** for:
   - `AI labelled impact for N and wrote M summaries`
   - `run complete`

---

## Email recipients

Each address gets its own message, so recipients cannot see one another.

**Option A (recommended):** add the secret `EMAIL_TO` with comma-separated addresses, for example `first@gmail.com,second@gmail.com`.

**Option B:** list the addresses in `config/settings.yaml`:

```yaml
email:
  to:
    - "first@gmail.com"
    - "second@gmail.com"
  subject_prefix: "[Tech News]"
```

If `EMAIL_TO` is set, it takes priority. Gmail allows about 500 messages a day for a personal account.

---

## Schedule

The workflow file is `.github/workflows/daily_collect.yml`.

| Run | When (UTC) | Digest sent |
|---|---|---|
| Daily | Every day at 01:00 (06:00 Pakistan) | Day digest, unless it is the 1st or a Sunday |
| Sunday | Same run, detected by date | Weekly digest |
| 1st of the month | Same run, detected by date | Monthly digest |

Each run sends exactly one digest. GitHub can start a run a few minutes late.

**Test without waiting:** go to **Actions > Tech news collector > Run workflow**, tick **test_email**, and click **Run workflow**. You will receive a test message within a few minutes.

**Send a digest manually:** choose `day`, `week`, or `month` in the dropdown. Choosing `month` sends the monthly digest immediately.

---

## Running on your computer

Use Python 3.11 or 3.12.

```bash
python3.11 -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pip install -e .
pytest -q                          # expect 56 passed
```

Useful commands:

```bash
# Process feeds without saving or sending anything
python -m newsintel --dry-run --no-ai --verbose

# Save to local data/articles.json, no email (needs no Supabase variables)
python -m newsintel --no-email --no-ai

# Test one feed
python -m newsintel --feed "Google Cloud AI news search" --dry-run --no-ai --verbose

# Send a test email (set SMTP_USERNAME and SMTP_PASSWORD first)
python -m newsintel --test-email
```

Without the Supabase variables, the collector saves to `data/articles.json` on your computer.

---

## Configuration

| File | What it controls |
|---|---|
| `config/feeds.yaml` | Feed list. Set `enabled: false` to turn a feed off. |
| `config/settings.yaml` | Story limits, digest sizes, categories, keywords, AI settings, email recipients |
| `src/newsintel/` | Code: collection, scoring, AI, digests, storage, website |
| `docs/index.html` | The website (generated by the workflow) |
| `docs/vercel.json` | Vercel settings for the website |

Digest sizes are set in `settings.yaml`:

```yaml
period_top_n:
  day: 15
  week: 20
  month: 25
```

To add or fix a feed, copy an existing entry in `feeds.yaml`:

```yaml
  - name: "My source"
    url: "https://example.com/feed.xml"
    category: "NLP & LLMs"
    source_priority: 3
    enabled: true
```

---

## Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| Run is red, `DIGEST EMAIL WAS NOT SENT` | Missing or wrong SMTP secret, or Gmail rejected the login | Check `SMTP_USERNAME` and `SMTP_PASSWORD`. Use an App Password. |
| `email not configured` in the log | `SMTP_USERNAME` or `SMTP_PASSWORD` is missing | Add the secret. |
| `AI enrichment unavailable` | `GEMINI_API_KEY` missing, or Gemini quota used up | Check the secret and the Gemini quota. Stories keep feed text and rule-based labels. |
| Stories show "rules impact" | Stored before Gemini was working, or Gemini didn't run in that batch | Wait for new stories, or run the workflow again. |
| `could not read storage` or `could not save data` | Wrong Supabase URL or key, or tables missing | Check the three Supabase secrets, and run the SQL in Step 1. |
| Website says "not connected to its database" | Supabase secrets were missing when the page was built | Add the secrets, then run the workflow again. |
| Website says "Could not load the stories" | Missing policies in Supabase, or wrong anon key | Re-run the SQL, and check `SUPABASE_ANON_KEY`. |
| Vercel build fails with `PYTHON_ENTRYPOINT_NOT_FOUND` | Root Directory is not `docs` | Set **Root Directory** to `docs` in Vercel. |
| `rejected (fetch first)` on push | Remote has commits your folder lacks | Run `git pull --rebase origin main`, then push. |
| Many feeds fail with HTTP 503 | Google News rate limit | Temporary. The collector spaces requests and retries. |
| Some feeds fail with 403, 404, 410, or `invalid_xml` | Feed moved, removed, or blocks automated access | Update or disable it in `feeds.yaml`. |
| Scheduled runs stopped | GitHub paused the schedule after 60 days without activity, or the workflow was disabled | Click **Enable workflow** on the Actions page. |
| Supabase project paused | Free projects pause after about a week without activity | Click **Restore** in the Supabase dashboard. |

---

## Free-tier limits

| Service | Limit | Effect on this project |
|---|---|---|
| GitHub Actions | Unlimited for public repositories; 2,000 minutes a month for private | One short run a day |
| GitHub repository | About 1 GB recommended | Daily runs commit almost nothing |
| Supabase database | 500 MB | About 15 MB needed for 30 days of stories |
| Supabase egress | 5 GB a month | Each website visit downloads about 5 to 8 MB |
| Gmail | About 500 messages a day | A few messages a day per recipient |
| Gemini | Requests per minute and per day (changes over time) | The collector pauses between requests and falls back to rules if the quota is reached |
| Vercel Hobby | Personal, non-commercial use | Suitable for this project |

Check each provider's current limits, because they change over time.

---

## Project files

| Path | Purpose |
|---|---|
| `src/newsintel/pipeline.py` | Runs one collection, from fetch to save |
| `src/newsintel/enrich.py` | Gemini impact labels and one-paragraph summaries |
| `src/newsintel/impact.py` | AI providers (Gemini, Groq) and the weekly and monthly selection |
| `src/newsintel/scoring.py` | Rule-based score and categories |
| `src/newsintel/digest.py` | Digest and alert emails |
| `src/newsintel/emailer.py` | Sends email to one or more recipients |
| `src/newsintel/supabase_store.py` | Reads and writes Supabase |
| `src/newsintel/store.py` | Chooses Supabase or local storage |
| `src/newsintel/site.py` | Builds the website page |
| `.github/workflows/daily_collect.yml` | Daily schedule and the run steps |
| `tests/` | Automated tests (`pytest -q`) |

## License

Personal project. Use and modify it for your own purposes.
