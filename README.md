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
| Real email delivery | ✅ real SMTP sending via Mailtrap (or any SMTP provider), configured from the in-app Settings page |

## Real email sending (Mailtrap)
1. Sign up free at [mailtrap.io](https://mailtrap.io) → Email Testing → Inboxes → SMTP Settings
2. Copy the host, port, username, and password shown there
3. In the app, go to **Settings**, paste them in, and click **Save settings**, then **Test connection**
4. From then on, "Send now" and scheduled/automated campaigns deliver real emails into your Mailtrap sandbox inbox — safe for testing since nothing reaches real recipients
5. If Settings is left empty, the app automatically falls back to simulated sending (no real emails, randomized engagement) so the analytics dashboard still has data to show

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
- **Email delivery is real** once SMTP is configured in Settings (tested against Mailtrap's sandbox SMTP server). Failed sends are recorded with the actual SMTP error message.
- Open/click engagement tracking is still simulated (randomized) even with real SMTP, since true tracking needs pixel + link-redirect infrastructure — out of scope per the brief's own guidance to avoid advanced tracking/CRM complexity. This is clearly separated from delivery status in the database (`delivery_status` vs `opened`/`clicked`).
