from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func

from .extensions import db
from .models import Booking, Review, User


def _round(value, places="0.01"):
    return Decimal(value).quantize(Decimal(places), rounding=ROUND_HALF_UP)


def refresh_provider_stats(provider):
    if isinstance(provider, int):
        provider = db.session.get(User, provider)
    if provider is None:
        return None

    totals = (
        db.session.query(
            func.count(Review.id),
            func.avg(Review.quality),
            func.avg(Review.timeliness),
            func.avg(Review.communication),
        )
        .filter(Review.provider_id == provider.id)
        .one()
    )
    review_count = int(totals[0] or 0)
    avg_quality = Decimal(str(totals[1])) if totals[1] is not None else None
    avg_timeliness = Decimal(str(totals[2])) if totals[2] is not None else None
    avg_communication = Decimal(str(totals[3])) if totals[3] is not None else None

    completed = Booking.query.filter_by(provider_id=provider.id, status="completed").count()
    provider_cancelled = Booking.query.filter(
        Booking.provider_id == provider.id,
        Booking.status == "cancelled",
        Booking.cancelled_by_id == provider.id,
    ).count()
    refunded = Booking.query.filter_by(provider_id=provider.id, status="refunded").count()
    decided = completed + provider_cancelled + refunded
    completion_rate = (Decimal(completed) / Decimal(decided) * 100) if decided else None

    rating_avg = None
    reputation = None
    if review_count:
        rating_avg = (avg_quality + avg_timeliness + avg_communication) / 3
        weighted = avg_quality * Decimal("0.5") + avg_timeliness * Decimal("0.3") + avg_communication * Decimal("0.2")
        completion_component = (completion_rate / 100 * 5) if completion_rate is not None else weighted
        reputation = weighted * Decimal("0.7") + completion_component * Decimal("0.3")

    provider.review_count = review_count
    provider.completed_bookings = completed
    provider.rating_avg = _round(rating_avg) if rating_avg is not None else None
    provider.completion_rate = _round(completion_rate) if completion_rate is not None else None
    provider.reputation_score = _round(reputation) if reputation is not None else None

    return {
        "review_count": review_count,
        "rating_avg": provider.rating_avg,
        "completed": completed,
        "completion_rate": provider.completion_rate,
        "reputation": provider.reputation_score,
        "avg_quality": _round(avg_quality) if avg_quality is not None else None,
        "avg_timeliness": _round(avg_timeliness) if avg_timeliness is not None else None,
        "avg_communication": _round(avg_communication) if avg_communication is not None else None,
    }


def provider_breakdown(provider_id):
    row = (
        db.session.query(
            func.avg(Review.quality),
            func.avg(Review.timeliness),
            func.avg(Review.communication),
        )
        .filter(Review.provider_id == provider_id)
        .one()
    )
    return {
        "quality": float(row[0]) if row[0] is not None else None,
        "timeliness": float(row[1]) if row[1] is not None else None,
        "communication": float(row[2]) if row[2] is not None else None,
    }
