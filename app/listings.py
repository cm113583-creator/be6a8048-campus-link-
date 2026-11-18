from datetime import date, timedelta
from decimal import Decimal

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from .constants import CAMPUS_AREAS, DURATION_OPTIONS, PRICE_UNITS, WEEKDAYS
from .extensions import db
from .models import Booking, Category, Review, Service, User
from .reputation import provider_breakdown
from .utils import parse_decimal, parse_int, parse_time

bp = Blueprint("listings", __name__)


def page_url(page):
    args = request.args.to_dict()
    args["page"] = page
    return url_for("listings.browse", **args)


@bp.get("/services")
def browse():
    q = request.args.get("q", "").strip()
    category_slug = request.args.get("category", "").strip()
    area = request.args.get("area", "").strip()
    min_price = parse_decimal(request.args.get("min_price"), minimum=0)
    max_price = parse_decimal(request.args.get("max_price"), minimum=0)
    rating = parse_int(request.args.get("rating"), minimum=1, maximum=5)
    sort = request.args.get("sort", "recommended")
    page = parse_int(request.args.get("page"), minimum=1, default=1)

    query = (
        Service.query.join(User, Service.provider_id == User.id)
        .join(Category, Service.category_id == Category.id)
        .options(joinedload(Service.provider), joinedload(Service.category))
        .filter(Service.status == "active", User.is_suspended.is_(False))
    )
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                Service.title.ilike(like),
                Service.description.ilike(like),
                User.full_name.ilike(like),
                Category.name.ilike(like),
            )
        )
    active_category = None
    if category_slug:
        active_category = Category.query.filter_by(slug=category_slug).first()
        if active_category:
            query = query.filter(Service.category_id == active_category.id)
    if area:
        query = query.filter(Service.campus_area == area)
    if min_price is not None:
        query = query.filter(Service.price >= min_price)
    if max_price is not None:
        query = query.filter(Service.price <= max_price)
    if rating:
        query = query.filter(User.rating_avg >= rating)

    if sort == "price_low":
        query = query.order_by(Service.price.asc(), Service.created_at.desc())
    elif sort == "price_high":
        query = query.order_by(Service.price.desc(), Service.created_at.desc())
    elif sort == "rating":
        query = query.order_by(User.rating_avg.desc(), User.review_count.desc())
    elif sort == "newest":
        query = query.order_by(Service.created_at.desc())
    else:
        sort = "recommended"
        query = query.order_by(
            User.is_verified.desc(),
            User.reputation_score.is_(None),
            User.reputation_score.desc(),
            Service.created_at.desc(),
        )

    pagination = query.paginate(page=page, per_page=9, error_out=False)
    return render_template(
        "services/browse.html",
        pagination=pagination,
        services=pagination.items,
        categories=Category.query.order_by(Category.sort_order).all(),
        active_category=active_category,
        q=q,
        area=area,
        min_price=request.args.get("min_price", ""),
        max_price=request.args.get("max_price", ""),
        rating=rating,
        sort=sort,
        page_url=page_url,
    )


@bp.get("/services/<int:service_id>")
def detail(service_id):
    service = db.get_or_404(Service, service_id)
    is_owner = current_user.is_authenticated and current_user.id == service.provider_id
    is_admin = current_user.is_authenticated and current_user.is_admin
    if not service.is_live and not (is_owner or is_admin):
        abort(404)

    reviews = (
        Review.query.filter_by(provider_id=service.provider_id)
        .order_by(Review.created_at.desc())
        .limit(6)
        .all()
    )
    other_services = (
        Service.query.filter(
            Service.provider_id == service.provider_id,
            Service.id != service.id,
            Service.status == "active",
        )
        .order_by(Service.created_at.desc())
        .limit(3)
        .all()
    )
    similar = (
        Service.query.filter(
            Service.category_id == service.category_id,
            Service.id != service.id,
            Service.status == "active",
        )
        .order_by(Service.created_at.desc())
        .limit(3)
        .all()
    )
    tomorrow = date.today() + timedelta(days=1)
    return render_template(
        "services/detail.html",
        service=service,
        reviews=reviews,
        breakdown=provider_breakdown(service.provider_id),
        other_services=other_services,
        similar=similar,
        is_owner=is_owner,
        can_book=current_user.is_authenticated
        and not is_owner
        and not is_admin
        and not current_user.is_suspended,
        min_date=tomorrow.isoformat(),
        durations=DURATION_OPTIONS,
    )


def _collect_service_form():
    form = {
        "title": request.form.get("title", "").strip(),
        "category_id": request.form.get("category_id", "").strip(),
        "description": request.form.get("description", "").strip(),
        "price": request.form.get("price", "").strip(),
        "price_unit": request.form.get("price_unit", "per task").strip(),
        "duration_minutes": request.form.get("duration_minutes", "60").strip(),
        "campus_area": request.form.get("campus_area", "").strip(),
        "available_from": request.form.get("available_from", "08:00").strip(),
        "available_to": request.form.get("available_to", "18:00").strip(),
    }
    form["available_days"] = request.form.getlist("available_days")
    return form


def _service_errors(form):
    errors = {}
    if len(form["title"]) < 5 or len(form["title"]) > 140:
        errors["title"] = "Give your service a clear title (5–140 characters)."
    category = db.session.get(Category, int(form["category_id"])) if form["category_id"].isdigit() else None
    if category is None:
        errors["category_id"] = "Choose a category."
    if len(form["description"]) < 30:
        errors["description"] = "Describe the service in at least 30 characters."
    price = parse_decimal(form["price"], minimum="1")
    if price is None or price > Decimal("100000"):
        errors["price"] = "Enter a price between K1 and K100,000."
    if form["price_unit"] not in PRICE_UNITS:
        errors["price_unit"] = "Choose a pricing unit."
    duration = parse_int(form["duration_minutes"], minimum=30, maximum=480)
    if duration is None:
        errors["duration_minutes"] = "Choose a valid duration."
    if form["campus_area"] not in CAMPUS_AREAS:
        errors["campus_area"] = "Choose a campus area."
    days = []
    for raw in form["available_days"]:
        if raw.isdigit() and 0 <= int(raw) <= 6:
            days.append(int(raw))
    if not days:
        errors["available_days"] = "Select at least one available day."
    start = parse_time(form["available_from"])
    end = parse_time(form["available_to"])
    if not start or not end:
        errors["available_from"] = "Enter valid times in HH:MM format."
    elif start >= end:
        errors["available_to"] = "End time must be after start time."
    return errors, category, price, duration, days


@bp.route("/services/new", methods=["GET", "POST"])
@login_required
def create():
    if current_user.is_admin:
        abort(403)
    form = {
        "price_unit": "per hour",
        "duration_minutes": "60",
        "available_from": "08:00",
        "available_to": "18:00",
        "available_days": ["0", "1", "2", "3", "4"],
        "campus_area": current_user.campus_area or CAMPUS_AREAS[0],
    }
    errors = {}
    if request.method == "POST":
        form = _collect_service_form()
        errors, category, price, duration, days = _service_errors(form)
        if not errors:
            service = Service(
                provider_id=current_user.id,
                category_id=category.id,
                title=form["title"],
                description=form["description"],
                price=price,
                price_unit=form["price_unit"],
                duration_minutes=duration,
                campus_area=form["campus_area"],
                available_days=",".join(str(d) for d in sorted(set(days))),
                available_from=form["available_from"],
                available_to=form["available_to"],
                status="active",
            )
            db.session.add(service)
            db.session.commit()
            flash("Your service is live. Students can now find and book it.", "success")
            return redirect(url_for("listings.detail", service_id=service.id))
        flash("Please check the highlighted fields.", "danger")

    return render_template(
        "services/form.html",
        form=form,
        errors=errors,
        service=None,
        categories=Category.query.order_by(Category.sort_order).all(),
        weekdays=WEEKDAYS,
        price_units=PRICE_UNITS,
        durations=DURATION_OPTIONS,
    )


@bp.route("/services/<int:service_id>/edit", methods=["GET", "POST"])
@login_required
def edit(service_id):
    service = db.get_or_404(Service, service_id)
    if service.provider_id != current_user.id:
        abort(403)
    errors = {}
    if request.method == "POST":
        form = _collect_service_form()
        errors, category, price, duration, days = _service_errors(form)
        if not errors:
            service.category_id = category.id
            service.title = form["title"]
            service.description = form["description"]
            service.price = price
            service.price_unit = form["price_unit"]
            service.duration_minutes = duration
            service.campus_area = form["campus_area"]
            service.available_days = ",".join(str(d) for d in sorted(set(days)))
            service.available_from = form["available_from"]
            service.available_to = form["available_to"]
            db.session.commit()
            flash("Listing updated.", "success")
            return redirect(url_for("listings.detail", service_id=service.id))
        flash("Please check the highlighted fields.", "danger")
    else:
        form = {
            "title": service.title,
            "category_id": str(service.category_id),
            "description": service.description,
            "price": f"{Decimal(service.price):.2f}",
            "price_unit": service.price_unit,
            "duration_minutes": str(service.duration_minutes),
            "campus_area": service.campus_area,
            "available_from": service.available_from,
            "available_to": service.available_to,
            "available_days": [str(d) for d in service.day_numbers],
        }
    return render_template(
        "services/form.html",
        form=form,
        errors=errors,
        service=service,
        categories=Category.query.order_by(Category.sort_order).all(),
        weekdays=WEEKDAYS,
        price_units=PRICE_UNITS,
        durations=DURATION_OPTIONS,
    )


@bp.post("/services/<int:service_id>/toggle")
@login_required
def toggle(service_id):
    service = db.get_or_404(Service, service_id)
    if service.provider_id != current_user.id:
        abort(403)
    if service.status == "suspended":
        flash("This listing is suspended by an administrator and cannot be enabled.", "danger")
    elif service.status == "active":
        service.status = "paused"
        flash("Listing paused. It is hidden from search.", "info")
    else:
        service.status = "active"
        flash("Listing is live again.", "success")
    db.session.commit()
    return redirect(request.referrer or url_for("listings.my_services"))


@bp.get("/my-services")
@login_required
def my_services():
    if current_user.is_admin:
        return redirect(url_for("admin.dashboard"))
    services = (
        Service.query.filter_by(provider_id=current_user.id)
        .options(joinedload(Service.category))
        .order_by(Service.created_at.desc())
        .all()
    )
    bookings = {}
    for service in services:
        bookings[service.id] = service.bookings.filter(
            Booking.status.in_(("pending", "accepted", "in_escrow", "delivered"))
        ).count()
    return render_template("services/my_services.html", services=services, booking_counts=bookings)
