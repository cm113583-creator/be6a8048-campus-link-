# CampusLink — Code Guide

This document explains how the CampusLink web application is put together: the
architecture, the database model, the marketplace rules, each Python module, the routes,
and the tests. It is written to support both maintenance and an academic project report.

---

## 1. What the system does

CampusLink is a two-sided marketplace for campus services. A **seeker** can either book a
published service or post a request that providers respond to with offers. A **provider**
can publish services and respond to requests. Money moves through a **simulated wallet and
escrow**: the seeker pays into escrow, the provider delivers, the seeker confirms, and the
provider is paid minus a 5% platform fee. Reviews feed a reputation score, and an
**administrator** moderates users, listings, bookings, disputes, and reports.

The system is web-only and payment-simulated. There is no mobile app, no real payment
gateway, and no real email delivery.

### At a glance

| Item | Detail |
| --- | --- |
| Framework | Flask 3.1 application factory |
| Database | SQLite via Flask-SQLAlchemy (`instance/campuslink.db`) |
| Auth | Flask-Login sessions, Werkzeug password hashing |
| Forms | Server-rendered HTML, Flask-WTF CSRF protection |
| Templates | Jinja2 with Bootstrap 5 layout and a custom dark theme |
| Blueprints | `main`, `auth`, `listings`, `requests`, `bookings`, `messages`, `admin` |
| Database tables | 13 |
| Business routes | 50+ |
| Tests | 25 pytest tests across auth, marketplace, and admin flows |

---

## 2. High-level architecture

```
Browser (HTML/CSS/JS)
   |
   |  HTTP request + session cookie
   v
Flask application factory  (app/__init__.py)
   |-- Flask-Login          identifies current_user, guards pages
   |-- Flask-WTF            validates CSRF tokens on POST requests
   |-- Blueprints            group related routes
   |-- Jinja templates       render pages with the current data
   |-- SQLAlchemy ORM        reads/writes SQLite tables
   |
   v
instance/campuslink.db      persistent demo data
instance/mail_outbox.log    simulated email messages
```

Almost every route follows the same pattern:

```
route function
  -> load objects and check permissions
  -> parse and validate form input
  -> call domain logic in marketplace.py when money/status is involved
  -> create notifications
  -> db.session.commit()
  -> flash a result message
  -> redirect to a detail page
```

GET routes only query and render; POST routes change state. The POST/redirect/GET pattern
prevents duplicate submissions when a page is refreshed.

---

## 3. Startup and configuration

### Entry points

- `run.py` creates the Flask app and starts the development server on port 5000.
- `seed.py` creates the app and calls `seed_database()`; pass `--reset` to drop and
  recreate all tables first.
- `app/__init__.py::create_app()` is the application factory. Tests call it with an
  override dictionary to use a temporary database.

### `create_app()` responsibilities

1. Load `app/config.py` and apply optional overrides.
2. Create the `instance/` directory.
3. Initialise SQLAlchemy, Flask-Login, and CSRF protection.
4. Register the seven blueprints.
5. Register the Flask-Login user loader.
6. Install a `before_request` hook that logs out suspended users.
7. Install a context processor that makes shared template data available on every page.
8. Register Jinja filters (`money`, `datetime`, `date`, `time`, `nl2br`).
9. Add security headers and friendly 403/404/500 pages.
10. Register the `flask seed` CLI command.

The context processor computes unread-message and unread-notification counts for every
authenticated request, plus the open-dispute count for administrators. These values drive
the badges in the navigation bar.

### Configuration (`app/config.py`)

| Setting | Default | Purpose |
| --- | --- | --- |
| `SECRET_KEY` | dev fallback | Signs session cookies; override in production |
| `SQLALCHEMY_DATABASE_URI` | `sqlite:///campuslink.db` | Database location under `instance/` |
| `PLATFORM_FEE_RATE` | `0.05` | Marketplace commission |
| `CURRENCY` | `ZMW` | Currency code |
| `SESSION_COOKIE_HTTPONLY` | `True` | JavaScript cannot read the session cookie |
| `SESSION_COOKIE_SAMESITE` | `Lax` | Reduces cross-site request exposure |
| `WTF_CSRF_TIME_LIMIT` | `None` | Tokens remain valid for the session |
| `MAIL_OUTBOX` | `mail_outbox.log` | File that receives simulated emails |

`SECRET_KEY`, `DATABASE_URL`, and `MAIL_OUTBOX` can be overridden with environment
variables.

---

## 4. Database model

The schema is defined in `app/models.py`. SQLite stores all tables in one file.

### Tables

| Model | Table | Purpose |
| --- | --- | --- |
| `User` | `users` | Students and administrators; profile, wallet, and cached reputation |
| `Category` | `categories` | Service categories with icon and colour |
| `Service` | `services` | A provider's published listing |
| `Booking` | `bookings` | A job agreed directly or through a request/offer |
| `ServiceRequest` | `service_requests` | A seeker's open brief that providers can bid on |
| `Offer` | `offers` | A provider's price/time proposal on a request |
| `Payment` | `payments` | The escrow record for one booking |
| `Review` | `reviews` | Three-dimension review after a completed booking |
| `Dispute` | `disputes` | A formal disagreement on a paid booking |
| `Conversation` | `conversations` | A one-to-one message thread |
| `Message` | `messages` | A single chat message |
| `Notification` | `notifications` | In-app event feed with optional email simulation |
| `WalletTransaction` | `wallet_transactions` | Append-only ledger of wallet movements |

### Relationships

```
User 1 ──< Service
User 1 ──< Review (received)
User 1 ──< Notification
User 1 ──< WalletTransaction

Category 1 ──< Service
Category 1 ──< ServiceRequest

Service 1 ──< Booking

ServiceRequest 1 ──< Offer
ServiceRequest 1 ──  Booking        (optional, when a request is awarded)
Offer          1 ──  Booking        (optional, the winning offer)

Booking 1 ──  Payment               (one escrow record)
Booking 1 ──  Review                (one review)
Booking 1 ──  Dispute               (one dispute)

Conversation 1 ──< Message
```

`Booking` has two user foreign keys, `seeker_id` and `provider_id`; both point to `users`.
`Review` also has two: `author_id` and `provider_id`. `Dispute` records `opened_by_id` and
`resolved_by_id`.

### Important model properties

- `User.is_admin`, `first_name`, `initials`, `skills_list`, `rating_display`.
- `Service.day_numbers`, `availability_summary`, `status_meta`, `is_live`, and
  `quote(minutes)`.
- `Booking.ends_at`, `status_meta`, `other_party(user)`, `quantity_label()`.
- `ServiceRequest.offer_count`, `has_offer_from(user_id)`.
- `Review.overall` is the rounded average of quality, timeliness, and communication.
- `Conversation.pair_ids()` sorts two user IDs so a pair always has one canonical order.
- `WalletTransaction.is_credit` checks whether an amount is positive.

### Status vocabularies

Defined in `app/constants.py` and used by templates through `status_meta`.

| Entity | Statuses |
| --- | --- |
| Service | `active`, `paused`, `suspended` |
| Request | `open`, `awarded`, `closed`, `cancelled` |
| Offer | `pending`, `accepted`, `declined`, `withdrawn` |
| Booking | `pending`, `accepted`, `in_escrow`, `delivered`, `completed`, `declined`, `cancelled`, `disputed`, `refunded` |
| Payment | `held`, `released`, `refunded` |
| Dispute | `open`, `resolved_refund`, `resolved_release` |

---

## 5. Core business rules

### 5.1 Pricing

- Listings use `per hour`, `per task`, `per session`, or `per day`.
- `Service.quote(minutes)` multiplies the price by minutes/60 for hourly services and
  returns the flat price otherwise.
- Direct bookings use `service.quote(duration)`.
- Request-based bookings use the price in the accepted offer.
- `fee_for(amount)` calculates platform commission:
  `round(amount * 0.05, 2)`.
- The provider receives `amount - fee` on release.

Example: a K100 booking produces a K5.00 fee and a K95.00 provider payout.

### 5.2 Availability and conflicts

`availability_problem()` in `marketplace.py` rejects a proposed time when:

- it starts less than 30 minutes from now,
- it is more than 120 days in the future,
- the weekday is not in the provider's available days,
- the appointment would end on a different day,
- or it falls outside the provider's `available_from`–`available_to` window.

`conflict_problem()` checks the provider's booking calendar. It loads bookings within an
eight-hour window and compares intervals. Only `accepted`, `in_escrow`, `delivered`, and
`disputed` bookings block a slot; `pending` requests do not. When a provider accepts a
pending request, the conflict check is repeated with the booking itself excluded.

### 5.3 Booking state machine

```
                    provider accepts                 seeker pays
pending ───────────────────────────> accepted ─────────────────────> in_escrow
   |                                    |                               |
   | provider declines                  | seeker/provider cancel        | provider delivers
   v                                    v                               v
declined                            cancelled                        delivered
                                                                        |
                                                                        | seeker confirms
                                                                        v
                                                                    completed
                                                                        |
                                                                        | seeker reviews
                                                                        v
                                                                     Review

From in_escrow or delivered:
   participant opens dispute ──> disputed
       administrator refunds  ──> refunded
       administrator releases ──> completed
```

Cancellation details:

- A seeker may cancel `pending` or `accepted` bookings directly.
- A provider may cancel `pending`, `accepted`, or `in_escrow`.
- Cancelling an `in_escrow` booking calls `refund_escrow()` and returns the money.
- A cancelled booking records the actor in `cancelled_by_id` and a reason.
- Provider cancellations count against the provider's completion rate.

### 5.4 Escrow and wallet

The wallet is a local ledger, not a payment gateway.

1. `top_up(user, amount)` credits the wallet and records a `top_up` entry. The demo limit
   is K20,000 per transaction.
2. `hold_escrow(booking)` debits the seeker, creates a `Payment` row with status `held`,
   records the fee, and changes the booking to `in_escrow`.
3. `release_escrow(booking)` changes the payment to `released`, credits the provider with
   the net amount, marks the booking `completed`, and refreshes provider statistics.
4. `refund_escrow(booking)` changes the payment to `refunded`, credits the seeker with the
   full amount, and marks the booking `refunded`.

Every movement goes through `_wallet_entry()`, which updates `User.wallet_balance` and
stores the resulting balance in `WalletTransaction.balance_after`. There is no withdrawal
feature and no real money involved.

### 5.5 Reputation

`refresh_provider_stats()` in `app/reputation.py` recomputes cached values after money or
completion events.

```
rating_avg        = average(quality, timeliness, communication)
weighted_rating   = quality*0.5 + timeliness*0.3 + communication*0.2
completion_rate   = completed / (completed + provider_cancelled + refunded) * 100
reputation_score  = weighted_rating*0.7 + (completion_rate/100*5)*0.3
```

If there are no decided bookings, the completion component falls back to the weighted
rating. If there are no reviews, rating and reputation remain `None`, and the interface
shows “New provider”. Only providers with reviews have a rating and reputation score.

Example: quality 5, timeliness 4, communication 5 gives a weighted rating of 4.8 and an
overall rating of 4.67. With an 80% completion rate, the reputation score is
`4.8*0.7 + 4.0*0.3 = 4.56`.

---

## 6. Module-by-module walkthrough

### `app/__init__.py` — application factory

Creates and wires the app. Also defines global template context, currency/date filters,
security headers, error pages, and the seed CLI command. Blueprints are imported inside
the factory to avoid circular imports.

### `app/config.py` and `app/constants.py`

`config.py` holds environment-driven settings. `constants.py` holds display dictionaries
and shared option lists: campus areas, programmes, weekdays, durations, price units, status
labels/colours, and the `BOOKING_ACTIVE`/`BOOKING_BLOCKING` tuples used in queries.

### `app/models.py` — schema and small domain helpers

Defines all 13 models and their relationships. Most business logic lives elsewhere; models
mainly expose computed properties such as availability text, booking end time, status
metadata, and wallet sign.

### `app/marketplace.py` — domain service layer

This is the most important module to understand. It contains:

- `MarketplaceError` and `InsufficientFunds` exception types.
- `fee_for()`, `availability_problem()`, `conflict_problem()`, `next_reference()`.
- `_wallet_entry()`, `top_up()`, `debit()` — wallet invariants.
- `hold_escrow()`, `release_escrow()`, `refund_escrow()` — money lifecycle.
- `get_or_create_conversation()` — canonical one-to-one chat creation.

Routes call these functions instead of duplicating money and status rules.

### `app/auth.py` — registration, login, logout

- Registration validates name, email format/uniqueness, student number, phone, programme,
  year, campus, password strength, and confirmation.
- New users are created as students, logged in, and sent a welcome notification.
- Login lowercases email, tracks up to five failed attempts in a five-minute window, and
  uses `safe_next_url()` for the post-login destination.
- Logout is POST-only and CSRF-protected.

### `app/main.py` — public site, dashboard, profile, wallet, notifications

- `home()` builds featured services, category counts, platform stats, recent requests, and
  testimonials for the landing page.
- `dashboard()` collects active bookings, action counts (accept/pay/deliver/confirm),
  listings, suggested services, notifications, open requests, and the seeker's escrow
  total. Administrators are redirected to the admin console.
- `profile()` hides non-active listings from other users and exposes reviews and rating
  breakdowns.
- `edit_profile()` validates editable profile fields.
- `wallet()` handles demo top-ups and paginates the ledger; it can return to a `next` URL.
- Notification routes list items, mark all read, and open a single item safely.

### `app/listings.py` — service discovery and provider management

- `browse()` supports keyword search, category, campus area, minimum/maximum price, minimum
  rating, and five sort modes. It excludes paused/suspended listings and suspended
  providers. “Recommended” favours verified users, then non-null reputation, then recency.
- `detail()` returns 404 for non-live listings unless the viewer is the owner or an admin.
  It also loads recent reviews, the provider's other services, and similar listings.
- `create()` and `edit()` share `_collect_service_form()` and `_service_errors()`.
  Validation covers title, category, description, price, pricing unit, duration, campus
  area, available days, and opening hours. Administrators cannot create listings.
- `toggle()` pauses or reactivates a listing. A listing suspended by an admin cannot be
  re-enabled by its owner.
- `my_services()` shows the provider's listings and active booking counts.

### `app/requests.py` — request and offer workflow

- `index()` lists open requests or, with `?mine=1`, the current user's requests. It
  supports search, category filtering, and pagination.
- `create()` validates title, category, description, budget, campus area, and needed-by
  date. Administrators cannot post requests.
- `detail()` shows offers only to the request owner or an admin; other users see their own
  offer. Closed/cancelled requests are private to the owner and admins.
- `make_offer()` validates price, future time, duration, and a written approach. A provider
  can update their own pending offer; the unique constraint allows only one offer per
  provider per request.
- `accept_offer()` creates a booking already in `accepted` state, marks the request
  `awarded`, accepts the winning offer, declines the others, and notifies everyone.
- `withdraw_offer()` withdraws a pending offer; `close()` closes an open request and
  declines the remaining offers.

### `app/bookings.py` — direct bookings, escrow actions, reviews, disputes

- `create()` handles a direct listing booking: validates the date/time/location/description,
  checks availability and conflicts, snapshots the service data into the booking, and
  creates a `pending` request.
- `index()` shows bookings where the user is seeker or provider, with active/history tabs;
  admins see all bookings.
- `detail()` computes which action buttons each viewer may see and returns 403 to
  non-participants.
- `accept()`, `decline()`, `pay()`, `deliver()`, `confirm()` perform the state transitions.
- `cancel()` enforces role-specific cancellation windows and refunds escrow when needed.
- `dispute()` opens one dispute per booking and alerts the other party plus all admins.
- `review()` is seeker-only, completed-booking-only, and once per booking. It stores three
  ratings, refreshes reputation, and notifies the provider.
- `calendar()` downloads an `.ics` file built by `utils.build_ics()`.

### `app/messages.py` — private conversations

- The inbox lists conversations ordered by last message time, with the other user, unread
  count, and latest message.
- `start()` reuses an existing conversation or creates one from a sorted user pair.
- `thread()` checks that the viewer is a participant, validates message length, stores the
  message, updates `last_message_at`, notifies the recipient, and marks the other person's
  messages read when the thread is opened.

### `app/notifications.py` — notification and email helper

`notify()` writes an in-app `Notification` row and optionally appends a plain-text email to
the simulated outbox. `notify_admins()` fans a notification out to every active admin.

### `app/reputation.py` — provider statistics

`refresh_provider_stats()` recalculates review count, rating average, completed bookings,
completion rate, and reputation score. `provider_breakdown()` returns the three component
averages for profile and listing pages.

### `app/admin.py` — moderation, disputes, reports, exports

- A `before_request` hook protects the entire blueprint; unauthenticated users are sent to
  login and non-admins receive 403.
- The dashboard aggregates users, listings, booking statuses, escrow held, released GMV,
  platform fees, monthly revenue, open disputes, recent bookings, and recent users.
- User actions toggle verification, suspend accounts, and reinstate accounts. Suspending a
  user also suspends their active listings; reinstating does not automatically restore
  them.
- Listing actions suspend and restore listings. A listing cannot be restored while its
  provider is suspended.
- Dispute resolution accepts `refund` or `release`, requires a note, calls the same escrow
  functions used by normal bookings, records the resolver and timestamp, and notifies both
  parties.
- Reports support 30, 90, 365, or all-time windows. They calculate completed bookings,
  released payments, GMV, fees, escrow held, new users, average value, category revenue,
  top providers, monthly revenue, and booking status counts.
- `_csv_response()` writes UTF-8 CSV with a BOM so Excel opens Zambian text correctly.
  Exports exist for bookings and users.

### `app/utils.py` — input parsing and formatting

Central helpers:

- `safe_next_url()` blocks absolute and protocol-relative redirects.
- `parse_decimal()`, `parse_int()`, `parse_date()`, `parse_time()`, `parse_datetime()`.
- `log_email()` writes the simulated outbox.
- `build_ics()` generates calendar content.
- Formatting helpers such as `minutes_label()`, `human_join()`, and `time_range_label()`.

### `app/seed_data.py` — demo dataset

Drops (optionally) and rebuilds the demo database: categories, users, services, requests,
offers, bookings, payments, reviews, conversations, messages, notifications, and wallet
entries. It prints demo credentials at the end. The dataset is designed to exercise every
status: pending, accepted, in escrow, delivered, completed, disputed, refunded, declined,
and cancelled.

### Templates and static assets

- `templates/base.html` provides the navigation, flash messages, footer, CSRF meta tag, and
  content block. Every page extends it.
- `templates/partials/macros.html` contains reusable cards, avatars, rating stars, status
  badges, form errors, and pagination.
- Feature templates mirror the blueprint names: `auth/`, `services/`, `requests/`,
  `bookings/`, `messages/`, `admin/`, `main/`, plus `errors/`.
- `static/css/app.css` is the custom charcoal theme and layout system.
- `static/js/app.js` adds password visibility toggles, one-click demo login, confirmation
  dialogs, auto-submitting filters, wallet quick amounts, a live booking quote, automatic
  chat scroll, and the admin suspension modal.

---

## 7. Route map

### Public and account routes

| Methods | Path | Endpoint | Purpose |
| --- | --- | --- | --- |
| GET | `/` | `main.home` | Landing page |
| GET, POST | `/register` | `auth.register` | Create a student account |
| GET, POST | `/login` | `auth.login` | Sign in |
| POST | `/logout` | `auth.logout` | Sign out |

### Student dashboard and account

| Methods | Path | Endpoint | Purpose |
| --- | --- | --- | --- |
| GET | `/dashboard` | `main.dashboard` | Role-aware dashboard |
| GET | `/profile/<user_id>` | `main.profile` | Public student profile |
| GET, POST | `/settings/profile` | `main.edit_profile` | Edit own profile |
| GET, POST | `/wallet` | `main.wallet` | Wallet ledger and demo top-up |
| GET | `/notifications` | `main.notifications` | Notification list |
| POST | `/notifications/read-all` | `main.read_all_notifications` | Mark all read |
| GET | `/notifications/<id>/open` | `main.open_notification` | Open and mark one read |

### Services

| Methods | Path | Endpoint | Purpose |
| --- | --- | --- | --- |
| GET | `/services` | `listings.browse` | Search and filter listings |
| GET | `/services/<service_id>` | `listings.detail` | Listing detail |
| GET, POST | `/services/new` | `listings.create` | Publish a service |
| GET, POST | `/services/<service_id>/edit` | `listings.edit` | Edit own listing |
| POST | `/services/<service_id>/toggle` | `listings.toggle` | Pause or reactivate |
| GET | `/my-services` | `listings.my_services` | Provider listing manager |
| POST | `/services/<service_id>/book` | `bookings.create` | Book a listing |

### Requests and offers

| Methods | Path | Endpoint | Purpose |
| --- | --- | --- | --- |
| GET | `/requests` | `requests.index` | Browse open requests |
| GET, POST | `/requests/new` | `requests.create` | Post a request |
| GET | `/requests/<request_id>` | `requests.detail` | Request detail and offers |
| POST | `/requests/<request_id>/offers` | `requests.make_offer` | Submit/update an offer |
| POST | `/requests/<id>/offers/<offer_id>/accept` | `requests.accept_offer` | Award an offer |
| POST | `/requests/<id>/offers/<offer_id>/withdraw` | `requests.withdraw_offer` | Withdraw an offer |
| POST | `/requests/<request_id>/close` | `requests.close` | Close a request |

### Bookings and escrow

| Methods | Path | Endpoint | Purpose |
| --- | --- | --- | --- |
| GET | `/bookings` | `bookings.index` | My bookings |
| GET | `/bookings/<booking_id>` | `bookings.detail` | Booking detail and actions |
| POST | `/bookings/<id>/accept` | `bookings.accept` | Provider accepts |
| POST | `/bookings/<id>/decline` | `bookings.decline` | Provider declines |
| POST | `/bookings/<id>/pay` | `bookings.pay` | Seeker pays into escrow |
| POST | `/bookings/<id>/deliver` | `bookings.deliver` | Provider marks delivered |
| POST | `/bookings/<id>/confirm` | `bookings.confirm` | Seeker releases escrow |
| POST | `/bookings/<id>/cancel` | `bookings.cancel` | Cancel with refund rules |
| POST | `/bookings/<id>/dispute` | `bookings.dispute` | Open a dispute |
| POST | `/bookings/<id>/review` | `bookings.review` | Review a provider |
| GET | `/bookings/<id>/calendar.ics` | `bookings.calendar` | Download calendar file |

### Messaging

| Methods | Path | Endpoint | Purpose |
| --- | --- | --- | --- |
| GET | `/messages` | `messages.inbox` | Conversation list |
| POST | `/messages/start/<user_id>` | `messages.start` | Start/reuse a conversation |
| GET, POST | `/messages/<conversation_id>` | `messages.thread` | Read and send messages |

### Administration

| Methods | Path | Endpoint | Purpose |
| --- | --- | --- | --- |
| GET | `/admin/` | `admin.dashboard` | Platform overview |
| GET | `/admin/users` | `admin.users` | User list and filters |
| POST | `/admin/users/<id>/verify` | `admin.verify_user` | Toggle verification |
| POST | `/admin/users/<id>/suspend` | `admin.suspend_user` | Suspend account |
| POST | `/admin/users/<id>/unsuspend` | `admin.unsuspend_user` | Reinstate account |
| GET | `/admin/listings` | `admin.listings` | Listing moderation |
| POST | `/admin/listings/<id>/suspend` | `admin.suspend_listing` | Suspend listing |
| POST | `/admin/listings/<id>/restore` | `admin.restore_listing` | Restore listing |
| GET | `/admin/disputes` | `admin.disputes` | Dispute queue |
| GET | `/admin/disputes/<id>` | `admin.dispute_detail` | Dispute detail |
| POST | `/admin/disputes/<id>/resolve` | `admin.resolve_dispute` | Refund or release |
| GET | `/admin/reports` | `admin.reports` | Metrics and reports |
| GET | `/admin/reports/bookings.csv` | `admin.export_bookings` | Booking export |
| GET | `/admin/reports/users.csv` | `admin.export_users` | User export |

---

## 8. End-to-end flows

### Flow A — direct booking

1. A seeker opens a service and submits the booking form.
2. `bookings.create()` validates time and availability, then creates a `pending` booking
   with a reference such as `CML-2026-00017`.
3. The provider sees the request, accepts it, and the booking becomes `accepted`.
4. The seeker pays. `hold_escrow()` debits the wallet, creates a `Payment`, and moves the
   booking to `in_escrow`.
5. The provider delivers; the booking becomes `delivered`.
6. The seeker confirms. `release_escrow()` pays the provider 95%, keeps 5%, and completes
   the booking.
7. The seeker leaves a review; provider statistics update.

### Flow B — request, offer, award

1. A seeker posts an open request with a budget.
2. Providers submit offers with price, time, duration, and a message.
3. The seeker compares offers and accepts one.
4. `requests.accept_offer()` creates a booking already in `accepted` state, links it to the
   request and offer, marks the request `awarded`, declines other pending offers, and
   notifies all providers.
5. The seeker pays into escrow; the rest matches Flow A.

### Flow C — dispute

1. While a booking is `in_escrow` or `delivered`, either participant opens a dispute.
2. The booking becomes `disputed`; funds remain held.
3. An administrator reviews both sides in `/admin/disputes/<id>`.
4. Refund calls `refund_escrow()`, returning money to the seeker and recording
   `resolved_refund`.
5. Release calls `release_escrow()`, paying the provider and recording `resolved_release`.
6. Both parties are notified with the administrator's note.

---

## 9. Security and authorization

| Control | Where it is implemented |
| --- | --- |
| Password hashing | `User.set_password()` / `check_password()` |
| Session management | Flask-Login; session cookies are HTTP-only and SameSite=Lax |
| Login throttling | Session list of timestamps; five failures per five minutes |
| Suspended accounts | `before_request` logout and login-time rejection |
| CSRF | `CSRFProtect` globally; every POST form includes `csrf_token()` |
| Role guard | Admin blueprint `before_request`; admin-only routes |
| Ownership checks | Each route verifies seeker/provider/owner before acting |
| State checks | Actions reject invalid status transitions |
| Input validation | Explicit checks plus `parse_*` helpers |
| Open redirects | `safe_next_url()` allows only relative paths |
| SQL injection | SQLAlchemy parameterised queries; no raw SQL |
| XSS | Jinja autoescaping; `nl2br` escapes before adding line breaks |
| Response headers | `nosniff`, `SAMEORIGIN`, referrer policy, permissions policy |
| Destructive actions | POST-only, CSRF-protected, confirmation dialogs in the UI |

Administrators are deliberately excluded from student actions: they cannot book, publish
listings, or post requests. They can still browse and moderate.

### Known limitations

This is a local academic demo, not a production deployment.

- `run.py` uses Flask's development server with `debug=True`.
- The default `SECRET_KEY` must be replaced for any real deployment.
- SQLite is single-writer and not suitable for high concurrency.
- Dates and times are stored as naive local datetimes; there is no timezone handling.
- Payments, top-ups, fees, and refunds are ledger entries only.
- Email is written to a log file instead of being sent.
- There is no password reset, email verification, account deletion, or file upload.
- Schema changes require recreating the database; there are no migrations.
- Rate limiting exists only for login attempts.

---

## 10. Testing

Run the suite from the project root:

```bash
.venv/Scripts/python.exe -m pytest -q
```

Current result: **25 passed**.

### Test setup

`tests/conftest.py` builds a fresh application with:

- a temporary SQLite file per test,
- CSRF disabled,
- a fixed precomputed password hash for speed,
- an admin, seeker (K500 balance), provider, rival, one category, and one active service.

Fixtures:

- `client` — Flask test client.
- `login` — posts credentials to `/login`.
- `accounts` — the seeded IDs.
- `make_booking` — creates an accepted booking and optionally holds escrow.

### Coverage

| File | Focus |
| --- | --- |
| `tests/test_auth_and_pages.py` | Public/protected pages, registration, login, logout, weak passwords, duplicate email, suspended login, wallet limits, listing lifecycle, ownership 403s |
| `tests/test_marketplace.py` | Full escrow lifecycle, fee/payout values, insufficient funds, authorization, cancellation, offer flow, request privacy, messaging read state, admin booking visibility |
| `tests/test_admin.py` | Admin access control, dashboard/report pages, CSV exports, verification, suspension, listing moderation, dispute refund/release, resolution-note validation |

The tests act as executable documentation of the expected rules. If a status transition or
permission changes, the tests describe what should still hold.

---

## 11. Where to change things

| Goal | Files to edit |
| --- | --- |
| Change the platform fee | `app/config.py` (`PLATFORM_FEE_RATE`) |
| Add/edit categories | `app/seed_data.py`; reseed with `python seed.py --reset` |
| Add a campus area or programme | `app/constants.py` |
| Change booking rules | `app/marketplace.py` and `app/bookings.py` |
| Change reputation weights | `app/reputation.py` |
| Add a new status | `app/constants.py`, model defaults, route guards, templates |
| Change the visual theme | `app/static/css/app.css` and `app/templates/base.html` |
| Add a page | New route in the relevant blueprint plus a template |
| Add a new admin tool | `app/admin.py` plus `app/templates/admin/` |

After changing models or seed data, rebuild the demo database:

```bash
python seed.py --reset
```

---

## 12. Report-ready summary

CampusLink is a Flask web application that implements a two-sided campus service
marketplace. It separates presentation (Jinja templates), transport (blueprints and
routes), domain rules (the `marketplace` service layer), and persistence (SQLAlchemy
models). A booking is a state machine. Money is represented by an append-only wallet
ledger and a per-booking escrow record. A 5% platform fee is deducted on release. Reviews
combine three service dimensions with completion history to produce a reputation score.
Role-based authorization separates students, providers, and administrators, while CSRF
protection, ownership checks, and status validation protect every mutation. The system is
intentionally web-only and uses simulated payments and email, making the full marketplace
workflow demonstrable on a single local machine.
