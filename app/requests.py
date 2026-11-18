from datetime import date, datetime
from decimal import Decimal

from flask import Blueprint, abort, flash, redirect, render_template, request as http_request, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload

from .constants import CAMPUS_AREAS, DURATION_OPTIONS
from .extensions import db
from .marketplace import conflict_problem, next_reference
from .models import Booking, Category, Offer, ServiceRequest
from .notifications import notify
from .utils import parse_date, parse_datetime, parse_decimal, parse_int

bp = Blueprint("requests", __name__)


@bp.get("/requests")
@login_required
def index():
    q = http_request.args.get("q", "").strip()
    category_slug = http_request.args.get("category", "").strip()
    mine = http_request.args.get("mine") == "1"
    page = parse_int(http_request.args.get("page"), minimum=1, default=1)

    query = ServiceRequest.query.options(
        joinedload(ServiceRequest.seeker), joinedload(ServiceRequest.category)
    )
    if mine:
        query = query.filter(ServiceRequest.seeker_id == current_user.id)
    else:
        query = query.filter(ServiceRequest.status == "open")
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(ServiceRequest.title.ilike(like), ServiceRequest.description.ilike(like)))
    active_category = None
    if category_slug:
        active_category = Category.query.filter_by(slug=category_slug).first()
        if active_category:
            query = query.filter(ServiceRequest.category_id == active_category.id)

    pagination = query.order_by(ServiceRequest.created_at.desc()).paginate(
        page=page, per_page=9, error_out=False
    )
    open_count = ServiceRequest.query.filter_by(status="open").count()
    mine_count = ServiceRequest.query.filter_by(seeker_id=current_user.id).count()
    return render_template(
        "requests/index.html",
        pagination=pagination,
        requests=pagination.items,
        categories=Category.query.order_by(Category.sort_order).all(),
        active_category=active_category,
        q=q,
        mine=mine,
        open_count=open_count,
        mine_count=mine_count,
    )


@bp.route("/requests/new", methods=["GET", "POST"])
@login_required
def create():
    if current_user.is_admin:
        abort(403)
    form = {"campus_area": current_user.campus_area or CAMPUS_AREAS[0]}
    errors = {}
    if http_request.method == "POST":
        form = {
            "title": http_request.form.get("title", "").strip(),
            "category_id": http_request.form.get("category_id", "").strip(),
            "description": http_request.form.get("description", "").strip(),
            "budget": http_request.form.get("budget", "").strip(),
            "campus_area": http_request.form.get("campus_area", "").strip(),
            "needed_by": http_request.form.get("needed_by", "").strip(),
        }
        category = db.session.get(Category, int(form["category_id"])) if form["category_id"].isdigit() else None
        budget = parse_decimal(form["budget"], minimum="1")
        needed_by = parse_date(form["needed_by"]) if form["needed_by"] else None
        if len(form["title"]) < 5 or len(form["title"]) > 140:
            errors["title"] = "Give your request a clear title (5–140 characters)."
        if category is None:
            errors["category_id"] = "Choose a category."
        if len(form["description"]) < 30:
            errors["description"] = "Describe what you need in at least 30 characters."
        if budget is None or budget > Decimal("100000"):
            errors["budget"] = "Enter a budget between K1 and K100,000."
        if form["campus_area"] not in CAMPUS_AREAS:
            errors["campus_area"] = "Choose a campus area."
        if form["needed_by"] and needed_by is None:
            errors["needed_by"] = "Enter a valid date."
        elif needed_by and needed_by < date.today():
            errors["needed_by"] = "The date needed by cannot be in the past."

        if not errors:
            service_request = ServiceRequest(
                seeker_id=current_user.id,
                category_id=category.id,
                title=form["title"],
                description=form["description"],
                budget=budget,
                campus_area=form["campus_area"],
                needed_by=needed_by,
                status="open",
            )
            db.session.add(service_request)
            db.session.commit()
            flash("Your request is live. Providers can now send offers.", "success")
            return redirect(url_for("requests.detail", request_id=service_request.id))
        flash("Please check the highlighted fields.", "danger")

    return render_template(
        "requests/form.html",
        form=form,
        errors=errors,
        categories=Category.query.order_by(Category.sort_order).all(),
        today=date.today().isoformat(),
    )


@bp.get("/requests/<int:request_id>")
@login_required
def detail(request_id):
    service_request = db.get_or_404(ServiceRequest, request_id)
    is_owner = service_request.seeker_id == current_user.id
    if not (is_owner or current_user.is_admin) and service_request.status not in ("open", "awarded"):
        abort(403)
    offers = []
    my_offer = None
    if is_owner:
        offers = (
            Offer.query.filter_by(request_id=service_request.id)
            .options(joinedload(Offer.provider))
            .order_by(Offer.created_at.desc())
            .all()
        )
    elif current_user.is_admin:
        offers = Offer.query.filter_by(request_id=service_request.id).all()
    else:
        my_offer = Offer.query.filter_by(
            request_id=service_request.id, provider_id=current_user.id
        ).first()
    can_offer = (
        service_request.status == "open"
        and not is_owner
        and not current_user.is_admin
        and current_user.id != service_request.seeker_id
    )
    return render_template(
        "requests/detail.html",
        request_item=service_request,
        offers=offers,
        my_offer=my_offer,
        is_owner=is_owner,
        can_offer=can_offer,
        durations=DURATION_OPTIONS,
        min_date=(date.today().isoformat()),
    )


@bp.post("/requests/<int:request_id>/offers")
@login_required
def make_offer(request_id):
    service_request = db.get_or_404(ServiceRequest, request_id)
    if service_request.status != "open":
        flash("This request is no longer open for offers.", "danger")
        return redirect(url_for("requests.detail", request_id=service_request.id))
    if service_request.seeker_id == current_user.id or current_user.is_admin:
        abort(403)

    price = parse_decimal(http_request.form.get("price"), minimum="1")
    proposed_at = parse_datetime(http_request.form.get("date"), http_request.form.get("time"))
    duration = parse_int(http_request.form.get("duration_minutes"), minimum=30, maximum=480)
    message = http_request.form.get("message", "").strip()
    problems = []
    if price is None or price > Decimal("100000"):
        problems.append("Enter an offer between K1 and K100,000.")
    if proposed_at is None or proposed_at <= datetime.now():
        problems.append("Choose a future date and time for the work.")
    if duration is None:
        problems.append("Choose how long the work will take.")
    if len(message) < 20:
        problems.append("Explain your approach in at least 20 characters.")
    if proposed_at and duration:
        conflict = conflict_problem(current_user.id, proposed_at, duration)
        if conflict:
            problems.append(conflict)
    if problems:
        for problem in problems:
            flash(problem, "danger")
        return redirect(url_for("requests.detail", request_id=service_request.id))

    existing = Offer.query.filter_by(request_id=service_request.id, provider_id=current_user.id).first()
    if existing and existing.status == "pending":
        flash("You already have a pending offer on this request.", "info")
        return redirect(url_for("requests.detail", request_id=service_request.id))
    if existing:
        existing.price = price
        existing.proposed_at = proposed_at
        existing.duration_minutes = duration
        existing.message = message
        existing.status = "pending"
        existing.created_at = datetime.now()
        offer = existing
    else:
        offer = Offer(
            request_id=service_request.id,
            provider_id=current_user.id,
            price=price,
            proposed_at=proposed_at,
            duration_minutes=duration,
            message=message,
            status="pending",
        )
        db.session.add(offer)
    notify(
        service_request.seeker,
        "New offer received",
        f"{current_user.full_name} offered K{price:,.2f} for “{service_request.title}”.",
        link=f"/requests/{service_request.id}",
        category="request",
        email=True,
    )
    db.session.commit()
    flash("Offer sent. The seeker will be notified if it is accepted.", "success")
    return redirect(url_for("requests.detail", request_id=service_request.id))


@bp.post("/requests/<int:request_id>/offers/<int:offer_id>/accept")
@login_required
def accept_offer(request_id, offer_id):
    service_request = db.get_or_404(ServiceRequest, request_id)
    offer = db.get_or_404(Offer, offer_id)
    if offer.request_id != service_request.id:
        abort(404)
    if service_request.seeker_id != current_user.id:
        abort(403)
    if service_request.status != "open" or offer.status != "pending":
        flash("This offer cannot be accepted.", "danger")
        return redirect(url_for("requests.detail", request_id=service_request.id))
    if offer.provider.is_suspended:
        flash("This provider's account is suspended. Choose another offer.", "danger")
        return redirect(url_for("requests.detail", request_id=service_request.id))
    if offer.proposed_at <= datetime.now():
        flash("This proposed time has passed. Ask the provider for a new offer.", "danger")
        return redirect(url_for("requests.detail", request_id=service_request.id))
    conflict = conflict_problem(offer.provider_id, offer.proposed_at, offer.duration_minutes)
    if conflict:
        flash(f"The provider is no longer available then: {conflict}", "danger")
        return redirect(url_for("requests.detail", request_id=service_request.id))

    booking = Booking(
        seeker_id=service_request.seeker_id,
        provider_id=offer.provider_id,
        request_id=service_request.id,
        offer_id=offer.id,
        category_id=service_request.category_id,
        title=service_request.title,
        description=service_request.description,
        price=offer.price,
        scheduled_at=offer.proposed_at,
        duration_minutes=offer.duration_minutes,
        location=service_request.campus_area,
        special_requirements=f"Offer message: {offer.message}",
        status="accepted",
        accepted_at=datetime.now(),
    )
    db.session.add(booking)
    db.session.flush()
    next_reference(booking)
    offer.status = "accepted"
    service_request.status = "awarded"
    for other in offer.request.offers.filter(Offer.id != offer.id, Offer.status == "pending").all():
        other.status = "declined"
        notify(
            other.provider,
            "Offer not selected",
            f"Your offer on “{service_request.title}” was not selected.",
            link=f"/requests/{service_request.id}",
            category="request",
        )
    notify(
        offer.provider,
        "Your offer was accepted",
        f"{current_user.full_name} accepted your K{offer.price:,.2f} offer for “{service_request.title}”. "
        "Payment will be held in escrow.",
        link=f"/bookings/{booking.id}",
        category="request",
        email=True,
    )
    db.session.commit()
    flash("Offer accepted. Pay into escrow to confirm the booking.", "success")
    return redirect(url_for("bookings.detail", booking_id=booking.id))


@bp.post("/requests/<int:request_id>/offers/<int:offer_id>/withdraw")
@login_required
def withdraw_offer(request_id, offer_id):
    service_request = db.get_or_404(ServiceRequest, request_id)
    offer = db.get_or_404(Offer, offer_id)
    if offer.request_id != service_request.id:
        abort(404)
    if offer.provider_id != current_user.id:
        abort(403)
    if offer.status != "pending":
        flash("Only a pending offer can be withdrawn.", "danger")
        return redirect(url_for("requests.detail", request_id=service_request.id))
    offer.status = "withdrawn"
    notify(
        service_request.seeker,
        "Offer withdrawn",
        f"{current_user.full_name} withdrew their offer on “{service_request.title}”.",
        link=f"/requests/{service_request.id}",
        category="request",
    )
    db.session.commit()
    flash("Offer withdrawn.", "info")
    return redirect(url_for("requests.detail", request_id=service_request.id))


@bp.post("/requests/<int:request_id>/close")
@login_required
def close(request_id):
    service_request = db.get_or_404(ServiceRequest, request_id)
    if service_request.seeker_id != current_user.id:
        abort(403)
    if service_request.status != "open":
        flash("Only open requests can be closed.", "danger")
        return redirect(url_for("requests.detail", request_id=service_request.id))
    service_request.status = "closed"
    for offer in service_request.offers.filter_by(status="pending").all():
        offer.status = "declined"
        notify(
            offer.provider,
            "Request closed",
            f"“{service_request.title}” was closed by the seeker.",
            link=f"/requests/{service_request.id}",
            category="request",
        )
    db.session.commit()
    flash("Request closed.", "info")
    return redirect(url_for("requests.detail", request_id=service_request.id))
