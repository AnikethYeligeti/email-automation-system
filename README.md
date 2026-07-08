# Mailflow — Email Marketing Automation System

Digital Marketing Capstone Project (SkillOrbit brief).

## Build status — ALL MODULES COMPLETE ✅

| Module | Status |
|---|---|
| 1. Subscriber Management | ✅ add, CSV import, groups, search/filter, unsubscribe toggle |
| 2. Email Campaign Creation | ✅ create/schedule campaigns, HTML content, campaign types |
| 3. Email Automation System | ✅ background scheduler auto-sends scheduled campaigns; welcome-email automation on new subscriber |
| 4. Campaign Analytics Dashboard | ✅ open/click rates, campaign performance chart, subscriber growth chart, engagement trend chart (Chart.js) |
| 5. Report Generation | ✅ CSV export (subscribers & campaigns), per-campaign PDF report (ReportLab) |

## Tech stack (as built)
- Backend: Python Flask + a background thread for scheduled automation
- Database: SQLite (drop-in swappable for MySQL via SQLAlchemy later)
- Frontend: Server-rendered HTML/CSS (Jinja2 templates) + Chart.js for analytics, no build step required
- Reports: CSV (stdlib) + PDF (ReportLab)
- Email sending: simulated (see note below)

## Running locally
```bash
pip install -r requirements.txt
python app.py
```
Then open http://localhost:5000

## Project structure
```
email-automation-system/
├── app.py              # Flask routes for all 5 modules + background scheduler
├── models.py            # SQLite schema + connection helper
├── templates/            # Jinja2 HTML templates (one per module/page)
├── static/css/           # Stylesheet
└── database.db           # Created automatically on first run
```

## What's simulated vs real
- Subscriber management, campaign storage, automation rules, and analytics all run against a real database — fully functional.
- The background scheduler is real: it runs on a daemon thread and checks every 15 seconds for campaigns whose `scheduled_time` has passed, then auto-sends them. Same for the on-subscribe welcome automation — it fires immediately when a new subscriber is added.
- Actual email delivery (SMTP/SendGrid) is simulated: "sending" records a delivery + randomized open/click engagement so the analytics dashboard and reports have realistic data to display. Swapping in real SMTP/SendGrid only requires replacing the body of `_simulate_send()` / `_send_single()` in `app.py` — the rest of the system (scheduling, storage, analytics, reporting) is unaffected. This mirrors the brief's own scope guidance to avoid building real-time bulk email servers.
