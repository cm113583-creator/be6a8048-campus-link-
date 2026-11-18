from datetime import date, datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload

from .constants import CAMPUS_AREAS, PROGRAMS, YEAR_OPTIONS
from .extensions import db
from .marketplace import MarketplaceError, top_up
from .models import (
    Booking,
    Category,
    Notification,
    Review,
    Service,
    ServiceRequest,
    User,
    WalletTransaction,
)
from .notifications import notify
from .reputation import provider_breakdown
from .utils import parse_decimal, parse_int, safe_next_url

bp = Blueprint("main", __name__)


@bp.get("/")
def home():
    featured = (
        Service.query.join(User, Service.provider_id == User.id)
        .options(joinedload(Service.provider), joinedload(Service.category))
        .filter(Service.status == "active", User.is_suspended.is_(False))
        .order_by(
            User.is_verified.desc(),
            User.reputation_score.is_(None),
            User.reputation_score.desc(),
            Service.created_at.desc(),
        )
        .limit(6)
        .all()
    )
    categories = Category.query.order_by(Category.sort_order).all()
    category_counts = dict(
        db.session.query(Service.category_id, func.count(Service.id))
        .join(User, Service.provider_id == User.id)
        .filter(Service.status == "active", User.is_suspended.is_(False))
        .group_by(Service.category_id)
        .all()
    )
    live_listings = Service.query.filter_by(status="active").count()
    verified_providers = (
        db.session.query(func.count(func.distinct(Service.provider_id)))
        .join(User, Service.provider_id == User.id)
        .filter(Service.status == "active", User.is_verified.is_(True), User.is_suspended.is_(False))
        .scalar()
        or 0
    )
    completed = Booking.query.filter_by(status="completed").count()
    recent_requests = (
        ServiceRequest.query.filter_by(status="open")
        .options(joinedload(ServiceRequest.seeker), joinedload(ServiceRequest.category))
        .order_by(ServiceRequest.created_at.desc())
        .limit(3)
        .all()
    )
    testimonials = (
        Review.query.filter(Review.comment.isnot(None), Review.comment != "")
        .options(joinedload(Review.author), joinedload(Review.provider))
        .order_by(Review.created_at.desc())
        .limit(3)
        .all()
    )
    return render_template(
        "main/home.html",
        featured=featured,
        categories=categories,
        category_counts=category_counts,
        live_listings=live_listings,
        verified_providers=verified_providers,
        completed=completed,
        recent_requests=recent_requests,
        testimonials=testimonials,
    )


@bp.get("/dashboard")
@login_required
def dashboard():
    if current_user.is_admin:
        return redirect(url_for("admin.dashboard"))
    now = db.func.now()
    active_partner_filter = or_(
        Booking.seeker_id == current_user.id,
        Booking.provider_id == current_user.id,
    )
    active_bookings = (
        Booking.query.filter(
            active_partner_filter,
            Booking.status.in_(("pending", "accepted", "in_escrow", "delivered", "disputed")),
        )
        .options(joinedload(Booking.seeker), joinedload(Booking.provider))
        .order_by(Booking.scheduled_at.asc())
        .limit(6)
        .all()
    )
    action_counts = {
        "to_accept": Booking.query.filter_by(provider_id=current_user.id, status="pending").count(),
        "to_pay": Booking.query.filter_by(seeker_id=current_user.id, status="accepted").count(),
        "to_deliver": Booking.query.filter_by(provider_id=current_user.id, status="in_escrow").count(),
        "to_confirm": Booking.query.filter_by(seeker_id=current_user.id, status="delivered").count(),
    }
    listings = (
        Service.query.filter_by(provider_id=current_user.id)
        .options(joinedload(Service.category))
        .order_by(Service.created_at.desc())
        .limit(4)
        .all()
    )
    listing_count = Service.query.filter_by(provider_id=current_user.id).count()
    suggested = (
        Service.query.join(User, Service.provider_id == User.id)
        .options(joinedload(Service.provider), joinedload(Service.category))
        .filter(
            Service.status == "active",
            Service.provider_id != current_user.id,
            User.is_suspended.is_(False),
        )
        .order_by(
            (Service.campus_area == current_user.campus_area).desc(),
            User.is_verified.desc(),
            User.reputation_score.is_(None),
            User.reputation_score.desc(),
        )
        .limit(3)
        .all()
    )
    notifications = (
        Notification.query.filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(5)
        .all()
    )
    open_requests = (
        ServiceRequest.query.filter(
            ServiceRequest.status == "open", ServiceRequest.seeker_id != current_user.id
        )
        .options(joinedload(ServiceRequest.category), joinedload(ServiceRequest.seeker))
        .order_by(ServiceRequest.created_at.desc())
        .limit(3)
        .all()
    )
    escrow_total = (
        db.session.query(func.coalesce(func.sum(Booking.price), 0))
        .filter(
            Booking.seeker_id == current_user.id,
            Booking.status.in_(("in_escrow", "delivered", "disputed")),
        )
        .scalar()
        or 0
    )
    return render_template(
        "main/dashboard.html",
        active_bookings=active_bookings,
        action_counts=action_counts,
        listings=listings,
        listing_count=listing_count,
        suggested=suggested,
        notifications=notifications,
        open_requests=open_requests,
        escrow_total=escrow_total,
        today=date.today(),
        now=datetime.now(),
    )


@bp.get("/profile/<int:user_id>")
def profile(user_id):
    user = db.get_or_404(User, user_id)
    if user.is_admin:
        abort(404)
    services = (
        Service.query.filter_by(provider_id=user.id)
        .options(joinedload(Service.category))
        .order_by(Service.status.asc(), Service.created_at.desc())
        .all()
    )
    if not (current_user.is_authenticated and (current_user.id == user.id or current_user.is_admin)):
        services = [s for s in services if s.status == "active"]
    reviews = (
        Review.query.filter_by(provider_id=user.id)
        .options(joinedload(Review.author), joinedload(Review.booking))
        .order_by(Review.created_at.desc())
        .all()
    )
    is_provider = bool(services) or user.review_count > 0 or user.completed_bookings > 0
    return render_template(
        "main/profile.html",
        profile_user=user,
        services=services,
        reviews=reviews,
        breakdown=provider_breakdown(user.id),
        is_provider=is_provider,
        is_self=current_user.is_authenticated and current_user.id == user.id,
    )


@bp.route("/settings/profile", methods=["GET", "POST"])
@login_required
def edit_profile():
    form = {
        "full_name": current_user.full_name,
        "phone": current_user.phone or "",
        "program": current_user.program or "",
        "year_of_study": current_user.year_of_study or "",
        "campus_area": current_user.campus_area or "",
        "bio": current_user.bio or "",
        "skills": current_user.skills or "",
    }
    errors = {}
    if request.method == "POST":
        form = {
            "full_name": request.form.get("full_name", "").strip(),
            "phone": request.form.get("phone", "").strip(),
            "program": request.form.get("program", "").strip(),
            "year_of_study": request.form.get("year_of_study", "").strip(),
            "campus_area": request.form.get("campus_area", "").strip(),
            "bio": request.form.get("bio", "").strip(),
            "skills": request.form.get("skills", "").strip(),
        }
        if len(form["full_name"]) < 3 or len(form["full_name"]) > 120:
            errors["full_name"] = "Enter your full name."
        if form["phone"] and not all(c.isdigit() or c in "+- " for c in form["phone"]):
            errors["phone"] = "Enter a valid phone number."
        if form["program"] and form["program"] not in PROGRAMS:
            errors["program"] = "Select a valid programme."
        if form["year_of_study"] and form["year_of_study"] not in YEAR_OPTIONS:
            errors["year_of_study"] = "Select a valid year."
        if form["campus_area"] and form["campus_area"] not in CAMPUS_AREAS:
            errors["campus_area"] = "Select a valid campus area."
        if len(form["bio"]) > 600:
            errors["bio"] = "Keep your bio under 600 characters."
        if len(form["skills"]) > 255:
            errors["skills"] = "Keep skills under 255 characters."
        if not errors:
            current_user.full_name = form["full_name"]
            current_user.phone = form["phone"] or None
            current_user.program = form["program"] or None
            current_user.year_of_study = form["year_of_study"] or None
            current_user.campus_area = form["campus_area"] or None
            current_user.bio = form["bio"] or None
            current_user.skills = form["skills"] or None
            db.session.commit()
            flash("Profile updated.", "success")
            return redirect(url_for("main.profile", user_id=current_user.id))
        flash("Please check the highlighted fields.", "danger")
    return render_template(
        "main/settings.html",
        form=form,
        errors=errors,
        programs=PROGRAMS,
        years=YEAR_OPTIONS,
        campus_areas=CAMPUS_AREAS,
    )


@bp.route("/wallet", methods=["GET", "POST"])
@login_required
def wallet():
    next_url = safe_next_url(request.values.get("next"))
    if request.method == "POST":
        amount = parse_decimal(request.form.get("amount"), minimum="1")
        if amount is None:
            flash("Enter a valid amount.", "danger")
        else:
            try:
                top_up(current_user, amount)
                db.session.commit()
                flash(f"K{amount:,.2f} was added to your demo wallet.", "success")
                if next_url:
                    return redirect(next_url)
                return redirect(url_for("main.wallet"))
            except MarketplaceError as exc:
                db.session.rollback()
                flash(str(exc), "danger")
    page = parse_int(request.args.get("page"), minimum=1, default=1)
    pagination = (
        WalletTransaction.query.filter_by(user_id=current_user.id)
        .order_by(WalletTransaction.created_at.desc())
        .paginate(page=page, per_page=15, error_out=False)
    )
    return render_template(
        "main/wallet.html",
        pagination=pagination,
        transactions=pagination.items,
        next_url=next_url,
    )


@bp.get("/notifications")
@login_required
def notifications():
    page = parse_int(request.args.get("page"), minimum=1, default=1)
    pagination = (
        Notification.query.filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .paginate(page=page, per_page=20, error_out=False)
    )
    return render_template("main/notifications.html", pagination=pagination, items=pagination.items)


@bp.post("/notifications/read-all")
@login_required
def read_all_notifications():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update(
        {"is_read": True}, synchronize_session=False
    )
    db.session.commit()
    flash("All notifications marked as read.", "info")
    return redirect(url_for("main.notifications"))


@bp.get("/notifications/<int:notification_id>/open")
@login_required
def open_notification(notification_id):
    notification = db.get_or_404(Notification, notification_id)
    if notification.user_id != current_user.id:
        abort(403)
    notification.is_read = True
    db.session.commit()
    target = safe_next_url(notification.link) or url_for("main.notifications")
    return redirect(target)
