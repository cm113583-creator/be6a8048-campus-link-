import os
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from functools import wraps

from flask import abort, current_app, flash, redirect, request, url_for
from flask_login import current_user


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login", next=request.full_path))
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def safe_next_url(target):
    if not target:
        return None
    if not target.startswith("/") or target.startswith("//") or "\\" in target:
        return None
    return target


def parse_decimal(raw, minimum=None):
    try:
        value = Decimal(str(raw).replace(",", "").strip())
    except (InvalidOperation, AttributeError, ValueError):
        return None
    if not value.is_finite():
        return None
    value = value.quantize(Decimal("0.01"))
    if minimum is not None and value < Decimal(str(minimum)):
        return None
    return value


def parse_int(raw, minimum=None, maximum=None, default=None):
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    if minimum is not None and value < minimum:
        return default
    if maximum is not None and value > maximum:
        return default
    return value


def parse_date(raw):
    try:
        return datetime.strptime(str(raw).strip(), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def parse_time(raw):
    try:
        return datetime.strptime(str(raw).strip(), "%H:%M").time()
    except (TypeError, ValueError):
        return None


def parse_datetime(date_raw, time_raw):
    d = parse_date(date_raw)
    t = parse_time(time_raw)
    if not d or not t:
        return None
    return datetime.combine(d, t)


def flash_form_error(errors, message="Please check the highlighted fields."):
    flash(message, "danger")
    return errors


def log_email(to_address, subject, body):
    target_dir = current_app.instance_path
    os.makedirs(target_dir, exist_ok=True)
    path = os.path.join(target_dir, current_app.config.get("MAIL_OUTBOX", "mail_outbox.log"))
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = (
        f"=== {stamp} ===\n"
        f"To: {to_address}\n"
        f"Subject: {subject}\n\n"
        f"{body}\n\n"
    )
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(entry)
    except OSError:
        current_app.logger.warning("Could not write simulated email to %s", path)


def seed_initial(name):
    return "".join(part[0] for part in name.split()[:2]).upper() if name else "?"


def time_range_label(start, end):
    if isinstance(start, time) and isinstance(end, time):
        return f"{start.strftime('%H:%M')}–{end.strftime('%H:%M')}"
    return f"{start}–{end}"


def minutes_label(minutes):
    minutes = int(minutes or 60)
    if minutes % 60 == 0:
        return f"{minutes // 60} hour{'s' if minutes != 60 else ''}"
    hours, mins = divmod(minutes, 60)
    return f"{hours}h {mins}m" if hours else f"{mins} minutes"


def human_join(items, conjunction="and"):
    items = [str(i) for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + f" {conjunction} " + items[-1]


def build_ics(booking):
    dt_format = "%Y%m%dT%H%M%S"
    start = booking.scheduled_at.strftime(dt_format)
    end = booking.ends_at.strftime(dt_format)
    stamp = datetime.utcnow().strftime(dt_format)
    summary = f"CampusLink: {booking.title}".replace("\n", " ")
    description = (
        f"Booking {booking.reference} with {booking.provider.full_name}. "
        f"Amount K{booking.price}. Status: {booking.status_meta['label']}."
    ).replace("\n", " ")
    location = (booking.location or "Campus").replace("\n", " ")
    return "\r\n".join(
        [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//CampusLink//Campus Marketplace//EN",
            "BEGIN:VEVENT",
            f"UID:{booking.reference}@campuslink.zm",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{start}",
            f"DTEND:{end}",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{description}",
            f"LOCATION:{location}",
            "END:VEVENT",
            "END:VCALENDAR",
            "",
        ]
    )
