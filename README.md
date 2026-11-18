# CampusLink

A two-sided service marketplace for peer-to-peer campus contracting, built for the
Cavendish University Zambia project *“A Two-Sided Service Marketplace for Peer-to-Peer
Campus Contracting”* (Chama Mwelwa, 113-583).

Students can list skills, post requests for help, compare offers, book and pay through a
simulated escrow wallet, then review each other. An admin console handles verification,
moderation, disputes, reports, and CSV exports.

## Features

- **Accounts & profiles** — student registration, campus profile, verified-student badges.
- **Service listings** — nine categories, keyword search, campus/category filters, pricing
  units, weekly availability, pause/resume, owner management.
- **Requests & offers** — seekers post a brief and budget; providers submit offers with a
  proposed date, duration, and price; the seeker awards one offer.
- **Bookings & escrow** — `pending → accepted → in escrow → delivered → completed`, with a
  cancellable/disputable state machine and a 5% platform fee.
- **Demo wallet** — top-ups, escrow holds, releases, refunds, and itemised transactions.
- **Reviews & reputation** — quality, timeliness, and communication ratings feed a weighted
  reputation score that also accounts for completion rate.
- **Messaging & notifications** — per-booking conversations, in-app notifications, and
  simulated email written to `instance/mail_outbox.log`.
- **Admin console** — users and verification, listing and service moderation, booking and
  dispute resolution, platform reports, plus CSV exports for users and bookings.
- **Calendar** — download a booking as an `.ics` file.

## Tech stack

- Python 3 / Flask 3.1
- Flask-SQLAlchemy + SQLite
- Flask-Login, Flask-WTF (CSRF protection)
- Jinja2 templates, Bootstrap Icons, custom charcoal dark theme
- pytest

## Getting started

From the project root (Windows Git Bash shown):

```bash
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
python seed.py --reset
python run.py
```

Open <http://127.0.0.1:5000>.

`python seed.py` seeds a curated demo dataset; `--reset` first drops and recreates every
table. The SQLite database lives at `instance/campuslink.db`. To start from an empty
database instead, delete that file and run `python run.py`.

## Demo accounts

| Role | Email | Password |
| --- | --- | --- |
| Admin | `admin@campuslink.zm` | `Admin@12345` |
| Seeker | `chama@student.cavendish.ac.zm` | `Demo@123` |
| Provider (design) | `luyando@student.cavendish.ac.zm` | `Demo@123` |
| Provider (tutoring) | `natasha@student.cavendish.ac.zm` | `Demo@123` |
| Provider (photography) | `kabwe@student.cavendish.ac.zm` | `Demo@123` |

Every seeded student account uses `Demo@123`; the login page also lists the primary demo
logins. Other seeded students include Zondiwe, Kelvin, Naomi, Bwalya, Joseph, Grace,
Emmanuel, Chisomo, and Taonga (emails follow `firstname@student.cavendish.ac.zm`).

## Typical flow

1. Sign in as Chama and book a service (or post a request).
2. Sign in as the provider, accept the booking, and deliver it.
3. Sign in as Chama again, pay into escrow, then confirm completion to release funds
   (the provider receives 95%, the platform keeps 5%).
4. Leave a review — reputation updates automatically.
5. Sign in as the admin to inspect disputes, reports, moderation, and exports.

## Simulated payments

**No real money is involved.** Wallet top-ups, escrow holds, releases, refunds, and platform
fees are all bookkeeping entries in the local SQLite database. There is no mobile money,
card, or bank integration, and no payment credentials are collected. The app is a web-only
demonstration of the marketplace workflow.

## Documentation

A detailed technical guide is available at [docs/CODE_GUIDE.md](docs/CODE_GUIDE.md). It
covers the architecture, database model, status lifecycles, escrow and reputation formulas,
a module-by-module walkthrough, the full route map, security controls, and the test suite.

## Tests

```bash
pytest -q
```

The suite uses an isolated temporary SQLite database, disables CSRF, and covers
authentication, listings, the full escrow lifecycle, offers, reviews, messaging,
authorization boundaries, admin moderation, disputes, and CSV exports.

## Project layout

```
app/
  __init__.py          application factory
  models.py            users, categories, services, requests, offers, bookings, reviews...
  auth.py              registration, login, logout
  main.py              home, dashboard, profiles, wallet, notifications
  listings.py          browse, service detail, provider service management
  requests.py          requests, offers, awarding
  bookings.py          bookings, escrow, delivery, completion, reviews
  messages.py          conversations and threads
  admin.py             admin console, reports, disputes, CSV exports
  marketplace.py       domain services (escrow, wallet, offers, conversations)
  reputation.py        provider stats and reputation scoring
  seed_data.py         demo dataset
  templates/           Jinja2 templates
  static/css/app.css   charcoal dark theme
instance/              SQLite database and simulated mail log (created at runtime)
tests/                 pytest suite
seed.py                seed the database
run.py                 development server
```
