# FC-Harvest

UK Parliament & Government monitoring tool. Fetches daily from GOV.UK and Parliament APIs, filters by keyword topics, and publishes a static dashboard to GitHub Pages.

## Quick start (run locally)

```bash
# 1. Clone and install
git clone https://github.com/jack-founderscomms/FC-Harvest.git
cd FC-Harvest
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Run a harvest (fetches real data from GOV.UK and Parliament APIs)
python run.py harvest

# 3. Regenerate the static dashboard with real data
python run.py static

# 4. Commit and push the updated dashboard
git add docs/index.html
git commit -m "chore: refresh dashboard with real data"
git push origin main

# The live page updates at:
# https://htmlpreview.github.io/?https://raw.githubusercontent.com/jack-founderscomms/FC-Harvest/main/docs/index.html
```

## Commands

| Command | What it does |
|---|---|
| `python run.py harvest` | Fetch all sources, store new items in `harvest.db`, log errors |
| `python run.py static` | Generate `docs/index.html` from the database |
| `python run.py serve` | Start the live FastAPI dashboard at http://localhost:8000 |

## Configuration

All keywords, sources, and schedule live in **`config.yaml`** — no code changes needed.

### Adding a keyword

Edit `keyword_categories` in `config.yaml`:
```yaml
keyword_categories:
  energy:
    - energy
    - net zero
    - your new keyword here   # ← add here
```

### Adding a GOV.UK source

```yaml
govuk:
  - id: govuk_dfe
    label: "DfE"
    type: govuk_api
    params:
      filter_organisations: "department-for-education"
      filter_content_store_document_type:
        - news_story
        - press_release
        - policy_paper
      order: "-public_timestamp"
      count: 50
```

Find the organisation slug at: `https://www.gov.uk/government/organisations`

### Scheduled harvest

The harvest runs daily at 07:00 London time via APScheduler when the server is running (`python run.py serve`). Change the time in `config.yaml`:
```yaml
schedule:
  cron: "0 7 * * *"
  timezone: "Europe/London"
```

## Email digest

Set `enabled: true` in `config.yaml` under `email:`, then set these environment variables:

```bash
export SMTP_HOST=smtp.gmail.com
export SMTP_PORT=587
export SMTP_USER=you@gmail.com
export SMTP_PASSWORD=your-app-password
```

For Gmail, use an [App Password](https://myaccount.google.com/apppasswords) (requires 2FA).

## Why the links were fake

The GitHub Pages demo was seeded with synthetic data so the page had something to show before a real harvest ran. Once you run `python run.py harvest` from your own machine (GOV.UK blocks cloud datacenter IPs), all items will have real URLs from GOV.UK and Parliament.

## Sources

| Group | Sources |
|---|---|
| GOV.UK | DSIT, HM Treasury, Cabinet Office, No.10, DBT, DHSC, DESNZ, HMRC |
| Committees | SIT (Commons), Science & Tech (Lords), Business & Trade, Communications & Digital, Economic Affairs, Industry & Regulators, Treasury |
| Parliament | Committee Inquiries, Written Statements (Commons + Lords), Hansard (Commons + Lords), What's On |
