import csv
import io
from datetime import datetime, timedelta
from decimal import Decimal

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from .constants import BOOKING_STATUSES
from .extensions import db
from .marketplace import MarketplaceError, refund_escrow, release_escrow
from .models import Booking, Category, Dispute, Payment, Service, ServiceRequest, User
from .notifications import notify
from .utils import parse_int

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.before_request
def require_admin():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login", next=request.full_path))
    if not current_user.is_admin:
        abort(403)
    return None


def _month_bounds(offset):
    today = datetime.now()
    year, month = today.year, today.month - offset
    while month <= 0:
        month += 12
        year -= 1
    start = datetime(year, month, 1)
    end_year, end_month = (year + 1, 1) if month == 12 else (year, month + 1)
    end = datetime(end_year, end_month, 1)
    return start, end


def _monthly_revenue():
    series = []
    for offset in range(5, -1, -1):
        start, end = _month_bounds(offset)
        amount = (
            db.session.query(func.coalesce(func.sum(Payment.amount), 0))
            .filter(Payment.status == "released", Payment.released_at >= start, Payment.released_at < end)
            .scalar()
            or 0
        )
        series.append({"label": start.strftime("%b"), "full": start.strftime("%B %Y"), "amount": Decimal(amount)})
    return series


def _completed_category_stats(since=None):
    query = (
        db.session.query(
            Category.name,
            Category.color,
            func.count(Booking.id),
            func.coalesce(func.sum(Booking.price), 0),
        )
        .join(Booking, Booking.category_id == Category.id)
        .filter(Booking.status == "completed")
    )
    if since:
        query = query.filter(Booking.completed_at >= since)
    rows = query.group_by(Category.id).order_by(func.sum(Booking.price).desc()).all()
    stats = [
        {"name": name, "color": color, "jobs": jobs, "revenue": Decimal(revenue or 0)}
        for name, color, jobs, revenue in rows
    ]
    max_revenue = max((item["revenue"] for item in stats), default=Decimal("0"))
    for item in stats:
        item["percent"] = float(item["revenue"] / max_revenue * 100) if max_revenue else 0
    return stats


def _top_providers(since=None):
    query = (
        db.session.query(
            User,
            func.count(Booking.id).label("jobs"),
            func.coalesce(func.sum(Booking.price), 0).label("earned"),
        )
        .join(Booking, Booking.provider_id == User.id)
        .filter(Booking.status == "completed")
    )
    if since:
        query = query.filter(Booking.completed_at >= since)
    return (
        query.group_by(User.id)
        .order_by(func.count(Booking.id).desc(), func.sum(Booking.price).desc())
        .limit(5)
        .all()
    )


@bp.get("/")
def dashboard():
    totals = {
        "students": User.query.filter_by(role="student").count(),
        "verified": User.query.filter_by(role="student", is_verified=True).count(),
        "unverified": User.query.filter_by(role="student", is_verified=False).count(),
        "suspended": User.query.filter_by(is_suspended=True).count(),
        "active_listings": Service.query.filter_by(status="active").count(),
        "paused_listings": Service.query.filter_by(status="paused").count(),
        "suspended_listings": Service.query.filter_by(status="suspended").count(),
        "open_requests": ServiceRequest.query.filter_by(status="open").count(),
    }
    status_counts = dict(db.session.query(Booking.status, func.count(Booking.id)).group_by(Booking.status).all())
    escrow_held = (
        db.session.query(func.coalesce(func.sum(Payment.amount), 0)).filter(Payment.status == "held").scalar()
        or 0
    )
    gmv = (
        db.session.query(func.coalesce(func.sum(Payment.amount), 0))
        .filter(Payment.status == "released")
        .scalar()
        or 0
    )
    fees = (
        db.session.query(func.coalesce(func.sum(Payment.platform_fee), 0))
        .filter(Payment.status == "released")
        .scalar()
        or 0
    )
    open_disputes = (
        Dispute.query.filter_by(status="open")
        .options(joinedload(Dispute.booking).joinedload(Booking.seeker), joinedload(Dispute.booking).joinedload(Booking.provider))
        .order_by(Dispute.created_at.asc())
        .all()
    )
    recent_bookings = (
        Booking.query.options(joinedload(Booking.seeker), joinedload(Booking.provider))
        .order_by(Booking.created_at.desc())
        .limit(6)
        .all()
    )
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    monthly = _monthly_revenue()
    max_month = max((m["amount"] for m in monthly), default=Decimal("0"))
    for month in monthly:
        month["percent"] = float(month["amount"] / max_month * 100) if max_month else 0
    return render_template(
        "admin/dashboard.html",
        totals=totals,
        status_counts=status_counts,
        escrow_held=escrow_held,
        gmv=gmv,
        fees=fees,
        dispute_queue=open_disputes,
        recent_bookings=recent_bookings,
        recent_users=recent_users,
        monthly=monthly,
        booking_statuses=BOOKING_STATUSES,
    )


@bp.get("/users")
def users():
    q = request.args.get("q", "").strip()
    state = request.args.get("state", "all")
    page = parse_int(request.args.get("page"), minimum=1, default=1)
    query = User.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(
                User.full_name.ilike(like),
                User.email.ilike(like),
                User.student_number.ilike(like),
            )
        )
    if state == "verified":
        query = query.filter(User.is_verified.is_(True), User.is_suspended.is_(False))
    elif state == "unverified":
        query = query.filter(User.is_verified.is_(False), User.is_suspended.is_(False))
    elif state == "suspended":
        query = query.filter(User.is_suspended.is_(True))
    else:
        state = "all"
    pagination = query.order_by(User.created_at.desc()).paginate(page=page, per_page=15, error_out=False)
    counts = {
        "all": User.query.count(),
        "verified": User.query.filter_by(is_verified=True).count(),
        "unverified": User.query.filter_by(is_verified=False).count(),
        "suspended": User.query.filter_by(is_suspended=True).count(),
    }
    return render_template(
        "admin/users.html", pagination=pagination, users=pagination.items, q=q, state=state, counts=counts
    )


@bp.post("/users/<int:user_id>/verify")
def verify_user(user_id):
    user = db.get_or_404(User, user_id)
    if user.is_admin:
        abort(403)
    user.is_verified = not user.is_verified
    notify(
        user,
        "Student verification updated",
        "Your student status is now verified. A verified badge appears on your profile."
        if user.is_verified
        else "Your verified student badge was removed. Contact the admin office if this is unexpected.",
        link=f"/profile/{user.id}",
        category="account",
        email=True,
    )
    db.session.commit()
    flash(f"{user.full_name} is now {'verified' if user.is_verified else 'unverified'}.", "success")
    return redirect(request.referrer or url_for("admin.users"))


@bp.post("/users/<int:user_id>/suspend")
def suspend_user(user_id):
    user = db.get_or_404(User, user_id)
    if user.is_admin:
        abort(403)
    reason = request.form.get("reason", "").strip()
    user.is_suspended = True
    for service in user.listings.all():
        if service.status == "active":
            service.status = "suspended"
    notify(
        user,
        "Account suspended",
        f"Your account was suspended by an administrator. Reason: {reason or 'policy violation'}.",
        category="account",
        email=True,
    )
    db.session.commit()
    flash(f"{user.full_name}'s account was suspended.", "warning")
    return redirect(request.referrer or url_for("admin.users"))


@bp.post("/users/<int:user_id>/unsuspend")
def unsuspend_user(user_id):
    user = db.get_or_404(User, user_id)
    if user.is_admin:
        abort(403)
    user.is_suspended = False
    notify(
        user,
        "Account reinstated",
        "Your account is active again. Listings suspended by an administrator can now be reviewed.",
        link="/dashboard",
        category="account",
        email=True,
    )
    db.session.commit()
    flash(f"{user.full_name}'s account was reinstated.", "success")
    return redirect(request.referrer or url_for("admin.users"))


@bp.get("/listings")
def listings():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "all")
    page = parse_int(request.args.get("page"), minimum=1, default=1)
    query = (
        Service.query.options(joinedload(Service.provider), joinedload(Service.category))
        .join(User, Service.provider_id == User.id)
    )
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(Service.title.ilike(like), User.full_name.ilike(like)))
    if status in ("active", "paused", "suspended"):
        query = query.filter(Service.status == status)
    else:
        status = "all"
    pagination = query.order_by(Service.created_at.desc()).paginate(page=page, per_page=15, error_out=False)
    counts = dict(db.session.query(Service.status, func.count(Service.id)).group_by(Service.status).all())
    return render_template(
        "admin/listings.html",
        pagination=pagination,
        services=pagination.items,
        q=q,
        status=status,
        counts=counts,
    )


@bp.post("/listings/<int:service_id>/suspend")
def suspend_listing(service_id):
    service = db.get_or_404(Service, service_id)
    service.status = "suspended"
    notify(
        service.provider,
        "Listing suspended",
        f"Your listing “{service.title}” was suspended by an administrator pending review.",
        link=f"/services/{service.id}",
        category="moderation",
        email=True,
    )
    db.session.commit()
    flash("Listing suspended.", "warning")
    return redirect(request.referrer or url_for("admin.listings"))


@bp.post("/listings/<int:service_id>/restore")
def restore_listing(service_id):
    service = db.get_or_404(Service, service_id)
    if service.provider.is_suspended:
        flash("Reinstate the provider's account before restoring their listing.", "danger")
        return redirect(request.referrer or url_for("admin.listings"))
    service.status = "active"
    notify(
        service.provider,
        "Listing restored",
        f"Your listing “{service.title}” is live again.",
        link=f"/services/{service.id}",
        category="moderation",
        email=True,
    )
    db.session.commit()
    flash("Listing restored.", "success")
    return redirect(request.referrer or url_for("admin.listings"))


@bp.get("/disputes")
def disputes():
    state = request.args.get("state", "open")
    page = parse_int(request.args.get("page"), minimum=1, default=1)
    query = Dispute.query.options(
        joinedload(Dispute.booking).joinedload(Booking.seeker),
        joinedload(Dispute.booking).joinedload(Booking.provider),
        joinedload(Dispute.opened_by),
    )
    if state == "open":
        query = query.filter(Dispute.status == "open")
    elif state == "resolved":
        query = query.filter(Dispute.status != "open")
    else:
        state = "all"
    pagination = query.order_by(Dispute.created_at.asc()).paginate(page=page, per_page=10, error_out=False)
    open_count = Dispute.query.filter_by(status="open").count()
    return render_template(
        "admin/disputes.html", pagination=pagination, disputes=pagination.items, state=state, open_count=open_count
    )


@bp.get("/disputes/<int:dispute_id>")
def dispute_detail(dispute_id):
    dispute = db.get_or_404(Dispute, dispute_id)
    return render_template("admin/dispute_detail.html", dispute=dispute, booking=dispute.booking)


@bp.post("/disputes/<int:dispute_id>/resolve")
def resolve_dispute(dispute_id):
    dispute = db.get_or_404(Dispute, dispute_id)
    if dispute.status != "open":
        flash("This dispute is already resolved.", "info")
        return redirect(url_for("admin.dispute_detail", dispute_id=dispute.id))
    action = request.form.get("action", "").strip()
    note = request.form.get("resolution_note", "").strip()
    if action not in ("refund", "release"):
        flash("Choose a resolution.", "danger")
        return redirect(url_for("admin.dispute_detail", dispute_id=dispute.id))
    if len(note) < 5:
        flash("Add a short resolution note for both parties.", "danger")
        return redirect(url_for("admin.dispute_detail", dispute_id=dispute.id))
    booking = dispute.booking
    try:
        if action == "refund":
            booking.cancelled_by_id = booking.provider_id
            refund_escrow(booking, reason=f"Dispute resolved in seeker's favour: {note}")
            dispute.status = "resolved_refund"
        else:
            release_escrow(booking, note=f"Dispute resolved in provider's favour: {note}")
            dispute.status = "resolved_release"
    except MarketplaceError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("admin.dispute_detail", dispute_id=dispute.id))
    dispute.resolution_note = note
    dispute.resolved_by_id = current_user.id
    dispute.resolved_at = datetime.now()
    outcome = "refunded to the seeker" if action == "refund" else "released to the provider"
    for party in (booking.seeker, booking.provider):
        notify(
            party,
            "Dispute resolved",
            f"Dispute on {booking.reference} was resolved by an administrator. "
            f"Funds were {outcome}. Note: {note}",
            link=f"/bookings/{booking.id}",
            category="dispute",
            email=True,
        )
    db.session.commit()
    flash(f"Dispute resolved — funds {outcome}.", "success")
    return redirect(url_for("admin.dispute_detail", dispute_id=dispute.id))


@bp.get("/reports")
def reports():
    days = parse_int(request.args.get("days"), default=30)
    if days not in (30, 90, 365, 0):
        days = 30
    since = datetime.now() - timedelta(days=days) if days else None
    payment_query = Payment.query.filter(Payment.status == "released")
    booking_query = Booking.query.filter(Booking.status == "completed")
    user_query = User.query
    if since:
        payment_query = payment_query.filter(Payment.released_at >= since)
        booking_query = booking_query.filter(Booking.completed_at >= since)
        user_query = user_query.filter(User.created_at >= since)
    released_count = payment_query.count()
    gmv = payment_query.with_entities(func.coalesce(func.sum(Payment.amount), 0)).scalar() or 0
    fees = payment_query.with_entities(func.coalesce(func.sum(Payment.platform_fee), 0)).scalar() or 0
    held = (
        db.session.query(func.coalesce(func.sum(Payment.amount), 0)).filter(Payment.status == "held").scalar() or 0
    )
    stats = {
        "completed": booking_query.count(),
        "released": released_count,
        "gmv": gmv or 0,
        "fees": fees,
        "held": held,
        "new_users": user_query.count(),
        "avg_value": (Decimal(gmv or 0) / released_count) if released_count else Decimal("0"),
    }
    categories = _completed_category_stats(since)
    top_providers = _top_providers(since)
    monthly = _monthly_revenue()
    max_month = max((m["amount"] for m in monthly), default=Decimal("0"))
    for month in monthly:
        month["percent"] = float(month["amount"] / max_month * 100) if max_month else 0
    status_counts = dict(db.session.query(Booking.status, func.count(Booking.id)).group_by(Booking.status).all())
    return render_template(
        "admin/reports.html",
        stats=stats,
        categories=categories,
        top_providers=top_providers,
        monthly=monthly,
        days=days,
        status_counts=status_counts,
        booking_statuses=BOOKING_STATUSES,
    )


def _csv_response(rows, headers, filename):
    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.writer(buffer)
    writer.writerow(headers)
    writer.writerows(rows)
    return Response(
        buffer.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@bp.get("/reports/bookings.csv")
def export_bookings():
    bookings = (
        Booking.query.options(joinedload(Booking.seeker), joinedload(Booking.provider))
        .order_by(Booking.created_at.desc())
        .all()
    )
    rows = []
    for booking in bookings:
        rows.append(
            [
                booking.reference,
                booking.created_at.strftime("%Y-%m-%d %H:%M"),
                booking.scheduled_at.strftime("%Y-%m-%d %H:%M"),
                booking.seeker.full_name,
                booking.provider.full_name,
                booking.title,
                f"{Decimal(booking.price):.2f}",
                booking.status,
                booking.payment.status if booking.payment else "unpaid",
                f"{Decimal(booking.payment.platform_fee):.2f}" if booking.payment else "0.00",
            ]
        )
    headers = [
        "Reference",
        "Created",
        "Scheduled",
        "Seeker",
        "Provider",
        "Service",
        "Amount (ZMW)",
        "Booking status",
        "Payment status",
        "Platform fee (ZMW)",
    ]
    return _csv_response(rows, headers, "campuslink-bookings.csv")


@bp.get("/reports/users.csv")
def export_users():
    users = User.query.order_by(User.created_at.desc()).all()
    rows = [
        [
            user.id,
            user.full_name,
            user.email,
            user.student_number,
            user.role,
            "yes" if user.is_verified else "no",
            "yes" if user.is_suspended else "no",
            f"{Decimal(user.wallet_balance or 0):.2f}",
            user.created_at.strftime("%Y-%m-%d"),
        ]
        for user in users
    ]
    headers = [
        "ID",
        "Name",
        "Email",
        "Student number",
        "Role",
        "Verified",
        "Suspended",
        "Wallet (ZMW)",
        "Joined",
    ]
    return _csv_response(rows, headers, "campuslink-users.csv")
