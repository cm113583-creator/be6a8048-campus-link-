from datetime import datetime
from decimal import Decimal
from io import BytesIO

from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload

from .constants import BOOKING_ACTIVE, DURATION_OPTIONS
from .extensions import db
from .marketplace import (
    InsufficientFunds,
    MarketplaceError,
    availability_problem,
    conflict_problem,
    hold_escrow,
    next_reference,
    refund_escrow,
    release_escrow,
)
from .models import Booking, Dispute, Review, Service
from .notifications import notify, notify_admins
from .reputation import refresh_provider_stats
from .utils import build_ics, parse_datetime, parse_int

bp = Blueprint("bookings", __name__)

HISTORY_STATUSES = ("completed", "declined", "cancelled", "refunded")


@bp.post("/services/<int:service_id>/book")
@login_required
def create(service_id):
    service = db.get_or_404(Service, service_id)
    if current_user.id == service.provider_id:
        flash("You cannot book your own service.", "danger")
        return redirect(url_for("listings.detail", service_id=service.id))
    if current_user.is_admin:
        flash("Admin accounts cannot place bookings.", "info")
        return redirect(url_for("listings.detail", service_id=service.id))
    if not service.is_live:
        flash("This service is not currently accepting bookings.", "danger")
        return redirect(url_for("listings.detail", service_id=service.id))

    date_raw = request.form.get("date", "").strip()
    time_raw = request.form.get("time", "").strip()
    scheduled_at = parse_datetime(date_raw, time_raw)
    duration = parse_int(request.form.get("duration_minutes"), minimum=30, maximum=480)
    if duration is None:
        duration = service.duration_minutes
    location = request.form.get("location", "").strip()
    description = request.form.get("description", "").strip()
    requirements = request.form.get("special_requirements", "").strip()

    problems = []
    if scheduled_at is None:
        problems.append("Choose a valid date and time.")
    if not location:
        problems.append("Add a meeting location.")
    if len(description) < 10:
        problems.append("Describe what you need in at least 10 characters.")
    if scheduled_at and not problems:
        problem = availability_problem(service, scheduled_at, duration)
        if problem:
            problems.append(problem)
    if scheduled_at and not problems:
        problem = conflict_problem(service.provider_id, scheduled_at, duration)
        if problem:
            problems.append(problem)
    if problems:
        for problem in problems:
            flash(problem, "danger")
        return redirect(url_for("listings.detail", service_id=service.id) + "#book")

    booking = Booking(
        seeker_id=current_user.id,
        provider_id=service.provider_id,
        service_id=service.id,
        category_id=service.category_id,
        title=service.title,
        description=description,
        price=service.quote(duration),
        scheduled_at=scheduled_at,
        duration_minutes=duration,
        location=location,
        special_requirements=requirements or None,
        status="pending",
    )
    db.session.add(booking)
    db.session.flush()
    next_reference(booking)
    notify(
        service.provider,
        "New booking request",
        f"{current_user.full_name} requested “{service.title}” on "
        f"{scheduled_at.strftime('%d %b at %H:%M')} for K{booking.price:,.2f}.",
        link=f"/bookings/{booking.id}",
        category="booking",
        email=True,
    )
    db.session.commit()
    flash("Request sent. You will be notified once the provider responds.", "success")
    return redirect(url_for("bookings.detail", booking_id=booking.id))


@bp.get("/bookings")
@login_required
def index():
    view = request.args.get("view", "seeking")
    state = request.args.get("state", "all")
    page = parse_int(request.args.get("page"), minimum=1, default=1)
    if current_user.is_admin:
        view = "all"
        base = Booking.query
    elif view == "providing":
        base = Booking.query.filter(Booking.provider_id == current_user.id)
    else:
        view = "seeking"
        base = Booking.query.filter(Booking.seeker_id == current_user.id)

    counts_base = db.session.query(Booking.status, db.func.count(Booking.id))
    if current_user.is_admin:
        counts_base = counts_base.group_by(Booking.status)
    elif view == "providing":
        counts_base = counts_base.filter(Booking.provider_id == current_user.id).group_by(Booking.status)
    else:
        counts_base = counts_base.filter(Booking.seeker_id == current_user.id).group_by(Booking.status)
    counts = {status: count for status, count in counts_base.all()}

    if state == "active":
        base = base.filter(Booking.status.in_(BOOKING_ACTIVE))
    elif state == "history":
        base = base.filter(Booking.status.in_(HISTORY_STATUSES))
    else:
        state = "all"

    pagination = (
        base.options(
            joinedload(Booking.seeker),
            joinedload(Booking.provider),
            joinedload(Booking.service),
        )
        .order_by(Booking.created_at.desc())
        .paginate(page=page, per_page=10, error_out=False)
    )
    seeking_total = (
        Booking.query.filter(Booking.seeker_id == current_user.id).count() if not current_user.is_admin else 0
    )
    providing_total = (
        Booking.query.filter(Booking.provider_id == current_user.id).count() if not current_user.is_admin else 0
    )
    return render_template(
        "bookings/index.html",
        pagination=pagination,
        view=view,
        state=state,
        counts=counts,
        seeking_total=seeking_total,
        providing_total=providing_total,
    )


@bp.get("/bookings/<int:booking_id>")
@login_required
def detail(booking_id):
    booking = db.get_or_404(Booking, booking_id)
    is_seeker = booking.seeker_id == current_user.id
    is_provider = booking.provider_id == current_user.id
    if not (is_seeker or is_provider or current_user.is_admin):
        abort(403)

    can_accept = is_provider and booking.status == "pending"
    can_decline = is_provider and booking.status == "pending"
    can_pay = is_seeker and booking.status == "accepted" and not booking.provider.is_suspended
    can_deliver = is_provider and booking.status == "in_escrow"
    can_confirm = is_seeker and booking.status == "delivered"
    can_review = is_seeker and booking.status == "completed" and booking.review is None
    can_dispute = (
        (is_seeker or is_provider)
        and booking.status in ("in_escrow", "delivered")
        and booking.dispute is None
    )
    can_cancel = (
        (is_seeker and booking.status in ("pending", "accepted"))
        or (is_provider and booking.status in ("pending", "accepted", "in_escrow"))
    )
    return render_template(
        "bookings/detail.html",
        booking=booking,
        is_seeker=is_seeker,
        is_provider=is_provider,
        is_admin=current_user.is_admin,
        can_accept=can_accept,
        can_decline=can_decline,
        can_pay=can_pay,
        can_deliver=can_deliver,
        can_confirm=can_confirm,
        can_review=can_review,
        can_dispute=can_dispute,
        can_cancel=can_cancel,
        durations=DURATION_OPTIONS,
    )


@bp.post("/bookings/<int:booking_id>/accept")
@login_required
def accept(booking_id):
    booking = db.get_or_404(Booking, booking_id)
    if booking.provider_id != current_user.id:
        abort(403)
    if booking.status != "pending":
        flash("This request can no longer be accepted.", "danger")
        return redirect(url_for("bookings.detail", booking_id=booking.id))
    problem = conflict_problem(
        booking.provider_id,
        booking.scheduled_at,
        booking.duration_minutes,
        exclude_booking_id=booking.id,
    )
    if problem:
        flash(problem, "danger")
        return redirect(url_for("bookings.detail", booking_id=booking.id))
    booking.status = "accepted"
    booking.accepted_at = datetime.now()
    notify(
        booking.seeker,
        "Booking request accepted",
        f"{booking.provider.full_name} accepted “{booking.title}”. Pay into escrow to confirm the booking.",
        link=f"/bookings/{booking.id}",
        category="booking",
        email=True,
    )
    db.session.commit()
    flash("Booking accepted. The seeker has been asked to pay into escrow.", "success")
    return redirect(url_for("bookings.detail", booking_id=booking.id))


@bp.post("/bookings/<int:booking_id>/decline")
@login_required
def decline(booking_id):
    booking = db.get_or_404(Booking, booking_id)
    if booking.provider_id != current_user.id:
        abort(403)
    if booking.status != "pending":
        flash("This request can no longer be declined.", "danger")
        return redirect(url_for("bookings.detail", booking_id=booking.id))
    reason = request.form.get("reason", "").strip()
    booking.status = "declined"
    booking.cancelled_at = datetime.now()
    booking.cancelled_by_id = current_user.id
    booking.cancellation_reason = reason or "Declined by provider"
    notify(
        booking.seeker,
        "Booking request declined",
        f"{booking.provider.full_name} declined “{booking.title}”. Reason: "
        f"{booking.cancellation_reason}.",
        link=f"/bookings/{booking.id}",
        category="booking",
        email=True,
    )
    db.session.commit()
    flash("Request declined and the seeker has been notified.", "info")
    return redirect(url_for("bookings.detail", booking_id=booking.id))


@bp.post("/bookings/<int:booking_id>/pay")
@login_required
def pay(booking_id):
    booking = db.get_or_404(Booking, booking_id)
    if booking.seeker_id != current_user.id:
        abort(403)
    if booking.status != "accepted":
        flash("This booking is not awaiting payment.", "danger")
        return redirect(url_for("bookings.detail", booking_id=booking.id))
    if booking.provider.is_suspended:
        flash("This provider's account is suspended. Payment cannot be accepted.", "danger")
        return redirect(url_for("bookings.detail", booking_id=booking.id))
    try:
        hold_escrow(booking)
        db.session.commit()
    except InsufficientFunds as exc:
        db.session.rollback()
        flash(str(exc), "warning")
        return redirect(url_for("main.wallet", next=url_for("bookings.detail", booking_id=booking.id)))
    except MarketplaceError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("bookings.detail", booking_id=booking.id))
    flash("Payment secured in escrow. The provider can now start your job.", "success")
    return redirect(url_for("bookings.detail", booking_id=booking.id))


@bp.post("/bookings/<int:booking_id>/deliver")
@login_required
def deliver(booking_id):
    booking = db.get_or_404(Booking, booking_id)
    if booking.provider_id != current_user.id:
        abort(403)
    if booking.status != "in_escrow":
        flash("This booking cannot be marked as delivered yet.", "danger")
        return redirect(url_for("bookings.detail", booking_id=booking.id))
    booking.status = "delivered"
    booking.delivered_at = datetime.now()
    notify(
        booking.seeker,
        "Service delivered — please confirm",
        f"{booking.provider.full_name} marked “{booking.title}” as delivered. "
        "Confirm completion to release the escrowed payment.",
        link=f"/bookings/{booking.id}",
        category="booking",
        email=True,
    )
    db.session.commit()
    flash("Marked as delivered. The seeker will confirm completion.", "success")
    return redirect(url_for("bookings.detail", booking_id=booking.id))


@bp.post("/bookings/<int:booking_id>/confirm")
@login_required
def confirm(booking_id):
    booking = db.get_or_404(Booking, booking_id)
    if booking.seeker_id != current_user.id:
        abort(403)
    if booking.status != "delivered":
        flash("Only delivered bookings can be confirmed.", "danger")
        return redirect(url_for("bookings.detail", booking_id=booking.id))
    try:
        release_escrow(booking)
        db.session.commit()
    except MarketplaceError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("bookings.detail", booking_id=booking.id))
    flash("Booking completed. Payment was released and you can now leave a review.", "success")
    return redirect(url_for("bookings.detail", booking_id=booking.id))


@bp.post("/bookings/<int:booking_id>/cancel")
@login_required
def cancel(booking_id):
    booking = db.get_or_404(Booking, booking_id)
    if current_user.id not in (booking.seeker_id, booking.provider_id):
        abort(403)
    reason = request.form.get("reason", "").strip()
    is_seeker = current_user.id == booking.seeker_id
    is_provider = current_user.id == booking.provider_id

    if is_seeker and booking.status not in ("pending", "accepted"):
        flash("This booking can no longer be cancelled directly. Open a dispute for help.", "danger")
        return redirect(url_for("bookings.detail", booking_id=booking.id))
    if is_provider and booking.status not in ("pending", "accepted", "in_escrow"):
        flash("This booking can no longer be cancelled.", "danger")
        return redirect(url_for("bookings.detail", booking_id=booking.id))

    booking.cancelled_by_id = current_user.id
    booking.cancellation_reason = reason or f"Cancelled by {'seeker' if is_seeker else 'provider'}"
    booking.cancelled_at = datetime.now()
    if booking.status == "in_escrow" and booking.payment and booking.payment.status == "held":
        try:
            refund_escrow(booking, reason=booking.cancellation_reason)
        except MarketplaceError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
            return redirect(url_for("bookings.detail", booking_id=booking.id))
        flash("Booking cancelled and the escrowed payment was returned to the seeker.", "success")
    else:
        booking.status = "cancelled"
        refresh_provider_stats(booking.provider)
        flash("Booking cancelled.", "info")
    notify(
        booking.other_party(current_user),
        "Booking cancelled",
        f"{current_user.full_name} cancelled “{booking.title}”. Reason: {booking.cancellation_reason}.",
        link=f"/bookings/{booking.id}",
        category="booking",
        email=True,
    )
    db.session.commit()
    return redirect(url_for("bookings.detail", booking_id=booking.id))


@bp.post("/bookings/<int:booking_id>/dispute")
@login_required
def dispute(booking_id):
    booking = db.get_or_404(Booking, booking_id)
    if current_user.id not in (booking.seeker_id, booking.provider_id):
        abort(403)
    if booking.status not in ("in_escrow", "delivered"):
        flash("A dispute can only be opened for an active, paid booking.", "danger")
        return redirect(url_for("bookings.detail", booking_id=booking.id))
    if booking.dispute is not None:
        flash("A dispute is already open for this booking.", "info")
        return redirect(url_for("bookings.detail", booking_id=booking.id))
    reason = request.form.get("reason", "").strip()
    details = request.form.get("details", "").strip()
    if not reason or len(details) < 20:
        flash("Choose a reason and describe the issue in at least 20 characters.", "danger")
        return redirect(url_for("bookings.detail", booking_id=booking.id))
    dispute = Dispute(
        booking_id=booking.id,
        opened_by_id=current_user.id,
        reason=reason,
        details=details,
        status="open",
    )
    db.session.add(dispute)
    booking.status = "disputed"
    booking.cancelled_at = None
    notify(
        booking.other_party(current_user),
        "A dispute was opened",
        f"{current_user.full_name} opened a dispute for “{booking.title}”. An administrator will review it.",
        link=f"/bookings/{booking.id}",
        category="dispute",
        email=True,
    )
    notify_admins(
        "New dispute needs review",
        f"{current_user.full_name} opened a dispute on {booking.reference} — {reason}.",
        link=f"/admin/disputes/{dispute.id}",
        category="dispute",
    )
    db.session.commit()
    flash("Dispute submitted. Escrowed funds stay on hold while an administrator reviews it.", "warning")
    return redirect(url_for("bookings.detail", booking_id=booking.id))


@bp.post("/bookings/<int:booking_id>/review")
@login_required
def review(booking_id):
    booking = db.get_or_404(Booking, booking_id)
    if booking.seeker_id != current_user.id:
        abort(403)
    if booking.status != "completed":
        flash("You can review a provider only after a completed booking.", "danger")
        return redirect(url_for("bookings.detail", booking_id=booking.id))
    if booking.review is not None:
        flash("You have already reviewed this booking.", "info")
        return redirect(url_for("bookings.detail", booking_id=booking.id))
    quality = parse_int(request.form.get("quality"), minimum=1, maximum=5)
    timeliness = parse_int(request.form.get("timeliness"), minimum=1, maximum=5)
    communication = parse_int(request.form.get("communication"), minimum=1, maximum=5)
    comment = request.form.get("comment", "").strip()
    if not all((quality, timeliness, communication)):
        flash("Choose a rating for quality, timeliness, and communication.", "danger")
        return redirect(url_for("bookings.detail", booking_id=booking.id) + "#review")
    if len(comment) > 1000:
        flash("Keep your review under 1,000 characters.", "danger")
        return redirect(url_for("bookings.detail", booking_id=booking.id) + "#review")

    review = Review(
        booking_id=booking.id,
        author_id=current_user.id,
        provider_id=booking.provider_id,
        quality=quality,
        timeliness=timeliness,
        communication=communication,
        comment=comment or None,
    )
    db.session.add(review)
    db.session.flush()
    refresh_provider_stats(booking.provider)
    notify(
        booking.provider,
        "New review received",
        f"{current_user.full_name} rated “{booking.title}” {review.overall}/5.",
        link=f"/profile/{booking.provider_id}",
        category="review",
        email=True,
    )
    db.session.commit()
    flash("Thank you — your review helps the whole campus community.", "success")
    return redirect(url_for("bookings.detail", booking_id=booking.id))


@bp.get("/bookings/<int:booking_id>/calendar.ics")
@login_required
def calendar(booking_id):
    booking = db.get_or_404(Booking, booking_id)
    if current_user.id not in (booking.seeker_id, booking.provider_id) and not current_user.is_admin:
        abort(403)
    payload = build_ics(booking).encode("utf-8")
    return send_file(
        BytesIO(payload),
        mimetype="text/calendar",
        as_attachment=True,
        download_name=f"{booking.reference}.ics",
    )
