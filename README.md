# Tech Intelligence

Daily tech news collector. Stories are stored in Supabase (free PostgreSQL), emails are sent through Gmail,
and the website is hosted on GitHub Pages (`docs/index.html`) and reads the stories from Supabase.

- Setup steps: see the step-by-step guide provided with this project (Parts 1 to 7).
- Run locally: `python -m newsintel --no-email --no-ai` (uses `data/articles.json` if Supabase variables are not set).
- Tests: `pytest -q`
- Schedule: `.github/workflows/daily_collect.yml` (daily 01:00 UTC; weekly on Sunday; monthly on the 1st).

