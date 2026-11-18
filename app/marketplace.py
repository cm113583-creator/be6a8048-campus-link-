from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from flask import current_app

from .constants import BOOKING_BLOCKING
from .extensions import db
from .models import Booking, Conversation, Payment, User, WalletTransaction
from .notifications import notify
from .reputation import refresh_provider_stats


class MarketplaceError(Exception):
    pass


class InsufficientFunds(MarketplaceError):
    pass


def fee_for(amount):
    rate = Decimal(str(current_app.config.get("PLATFORM_FEE_RATE", "0.05")))
    return (Decimal(amount) * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def availability_problem(service, scheduled_at, duration_minutes):
    if scheduled_at <= datetime.now() + timedelta(minutes=30):
        return "Choose a start time at least 30 minutes from now."
    if scheduled_at.date() > (datetime.now() + timedelta(days=120)).date():
        return "Bookings can be made up to 120 days in advance."
    if scheduled_at.weekday() not in service.day_numbers:
        return f"This provider is not available on {scheduled_at.strftime('%A')}."
    try:
        start_time = scheduled_at.time()
        end_dt = scheduled_at + timedelta(minutes=int(duration_minutes))
        from_time = datetime.strptime(service.available_from, "%H:%M").time()
        to_time = datetime.strptime(service.available_to, "%H:%M").time()
    except ValueError:
        return "The provider's availability is not configured correctly."
    if end_dt.date() != scheduled_at.date():
        return "The service must end on the same day it starts."
    if start_time < from_time or end_dt.time() > to_time:
        return (
            f"Choose a time within the provider's availability "
            f"({service.available_from}–{service.available_to})."
        )
    return None


def conflict_problem(provider_id, scheduled_at, duration_minutes, exclude_booking_id=None):
    start = scheduled_at
    end = scheduled_at + timedelta(minutes=int(duration_minutes))
    window_start = start - timedelta(hours=8)
    window_end = end + timedelta(hours=8)
    query = Booking.query.filter(
        Booking.provider_id == provider_id,
        Booking.status.in_(BOOKING_BLOCKING),
        Booking.scheduled_at >= window_start,
        Booking.scheduled_at <= window_end,
    )
    if exclude_booking_id:
        query = query.filter(Booking.id != exclude_booking_id)
    for other in query.all():
        if start < other.ends_at and end > other.scheduled_at:
            return (
                f"That time overlaps with another booking "
                f"({other.scheduled_at.strftime('%d %b %Y, %H:%M')})."
            )
    return None


def next_reference(booking):
    if not booking.reference:
        booking.reference = f"CML-{datetime.now().year}-{booking.id:05d}"
    return booking.reference


def _wallet_entry(user, amount, kind, description, booking_id=None):
    user.wallet_balance = Decimal(user.wallet_balance or 0) + Decimal(amount)
    user.wallet_balance = Decimal(user.wallet_balance).quantize(Decimal("0.01"))
    entry = WalletTransaction(
        user_id=user.id,
        amount=Decimal(amount),
        balance_after=user.wallet_balance,
        kind=kind,
        description=description,
        booking_id=booking_id,
    )
    db.session.add(entry)
    return entry


def top_up(user, amount, reference="Demo top-up"):
    if amount <= 0:
        raise MarketplaceError("Enter an amount greater than zero.")
    if amount > Decimal("20000"):
        raise MarketplaceError("Demo top-ups are limited to K20,000 per transaction.")
    return _wallet_entry(user, amount, "top_up", reference)


def debit(user, amount, kind, description, booking_id=None):
    amount = Decimal(amount)
    if amount <= 0:
        raise MarketplaceError("Invalid amount.")
    if Decimal(user.wallet_balance or 0) < amount:
        raise InsufficientFunds(
            f"Your wallet balance is K{Decimal(user.wallet_balance or 0):,.2f}. "
            f"Top up at least K{(amount - Decimal(user.wallet_balance or 0)):,.2f} to continue."
        )
    return _wallet_entry(user, -amount, kind, description, booking_id)


def hold_escrow(booking):
    if booking.status != "accepted":
        raise MarketplaceError("This booking is not awaiting payment.")
    if booking.payment and booking.payment.status == "held":
        raise MarketplaceError("Payment is already held in escrow.")
    amount = Decimal(booking.price)
    seeker = booking.seeker
    debit(
        seeker,
        amount,
        "escrow_hold",
        f"Escrow hold for {booking.reference} · {booking.title}",
        booking.id,
    )
    payment = Payment(
        booking_id=booking.id,
        amount=amount,
        platform_fee=fee_for(amount),
        provider_amount=amount - fee_for(amount),
        status="held",
    )
    db.session.add(payment)
    booking.status = "in_escrow"
    booking.paid_at = datetime.now()
    notify(
        booking.provider,
        "Payment secured in escrow",
        f"{seeker.full_name} paid K{amount:,.2f} for “{booking.title}”. "
        "Funds are held until completion is confirmed.",
        link=f"/bookings/{booking.id}",
        category="payment",
        email=True,
    )
    notify(
        seeker,
        "Payment held in escrow",
        f"K{amount:,.2f} is held safely for {booking.reference}. "
        "It will only be released after you confirm completion.",
        link=f"/bookings/{booking.id}",
        category="payment",
    )
    return payment


def release_escrow(booking, note=None):
    payment = booking.payment
    if not payment or payment.status != "held":
        raise MarketplaceError("There are no escrowed funds to release.")
    provider = booking.provider
    seeker = booking.seeker
    fee = fee_for(payment.amount)
    provider_amount = Decimal(payment.amount) - fee
    payment.platform_fee = fee
    payment.provider_amount = provider_amount
    payment.status = "released"
    payment.released_at = datetime.now()
    _wallet_entry(
        provider,
        provider_amount,
        "escrow_release",
        f"Earnings for {booking.reference} · {booking.title}",
        booking.id,
    )
    booking.status = "completed"
    booking.completed_at = datetime.now()
    refresh_provider_stats(provider)
    notify(
        provider,
        "Payment released",
        f"K{provider_amount:,.2f} was added to your wallet for “{booking.title}” "
        f"(platform fee K{fee:,.2f}).",
        link=f"/bookings/{booking.id}",
        category="payment",
        email=True,
    )
    notify(
        seeker,
        "Booking completed",
        f"Your booking {booking.reference} is complete. Leave a review to help other students.",
        link=f"/bookings/{booking.id}",
        category="booking",
    )
    if note:
        booking.cancellation_reason = note
    return payment


def refund_escrow(booking, reason=None):
    payment = booking.payment
    if not payment or payment.status != "held":
        raise MarketplaceError("There are no escrowed funds to refund.")
    seeker = booking.seeker
    amount = Decimal(payment.amount)
    payment.status = "refunded"
    payment.refunded_at = datetime.now()
    _wallet_entry(
        seeker,
        amount,
        "refund",
        f"Escrow refund for {booking.reference} · {booking.title}",
        booking.id,
    )
    booking.status = "refunded"
    booking.cancelled_at = datetime.now()
    if reason:
        booking.cancellation_reason = reason
    refresh_provider_stats(booking.provider)
    notify(
        seeker,
        "Refund processed",
        f"K{amount:,.2f} was returned to your CampusLink wallet for {booking.reference}.",
        link=f"/bookings/{booking.id}",
        category="payment",
        email=True,
    )
    notify(
        booking.provider,
        "Booking refunded",
        f"Booking {booking.reference} was refunded to the seeker. Reason: {reason or 'not provided'}.",
        link=f"/bookings/{booking.id}",
        category="payment",
    )
    return payment


def get_or_create_conversation(user_a_id, user_b_id):
    if user_a_id == user_b_id:
        raise MarketplaceError("You cannot message yourself.")
    a, b = Conversation.pair_ids(user_a_id, user_b_id)
    conversation = Conversation.query.filter_by(user_a_id=a, user_b_id=b).first()
    if conversation:
        return conversation
    other = db.session.get(User, user_b_id)
    if not other or other.is_suspended:
        raise MarketplaceError("That account is not available for messaging.")
    conversation = Conversation(user_a_id=a, user_b_id=b, last_message_at=datetime.now())
    db.session.add(conversation)
    db.session.flush()
    return conversation
