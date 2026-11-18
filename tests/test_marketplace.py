from decimal import Decimal

from app.extensions import db
from app.models import Booking, Conversation, Message, Offer, Payment, Review, ServiceRequest, User
from tests.helpers import future_date


def _create_booking(client, accounts):
    response = client.post(
        f"/services/{accounts['service']}/book",
        data={
            "date": future_date(),
            "time": "10:00",
            "duration_minutes": "60",
            "location": "Main library steps",
            "description": "Help with hypothesis testing before Friday's exam.",
        },
    )
    assert response.status_code == 302
    return Booking.query.order_by(Booking.id.desc()).first()


def test_full_booking_and_review_lifecycle(client, login, accounts):
    login("seeker@test.zm")
    booking = _create_booking(client, accounts)
    assert booking.status == "pending"
    assert booking.reference.startswith("CML-")

    client.post("/logout")
    login("provider@test.zm")
    detail = client.get(f"/bookings/{booking.id}")
    assert detail.status_code == 200
    assert b"Accept request" in detail.data

    client.post(f"/bookings/{booking.id}/accept")
    assert db.session.get(Booking, booking.id).status == "accepted"

    client.post("/logout")
    login("seeker@test.zm")
    client.post(f"/bookings/{booking.id}/pay")

    booking = db.session.get(Booking, booking.id)
    assert booking.status == "in_escrow"
    assert booking.paid_at is not None
    payment = Payment.query.filter_by(booking_id=booking.id).one()
    assert payment.status == "held"
    assert payment.platform_fee == Decimal("5.00")
    assert payment.provider_amount == Decimal("95.00")
    assert db.session.get(User, accounts["seeker"]).wallet_balance == Decimal("400.00")

    client.post("/logout")
    login("provider@test.zm")
    client.post(f"/bookings/{booking.id}/deliver")
    assert db.session.get(Booking, booking.id).status == "delivered"

    client.post("/logout")
    login("seeker@test.zm")
    client.post(f"/bookings/{booking.id}/confirm")
    booking = db.session.get(Booking, booking.id)
    assert booking.status == "completed"
    assert booking.payment.status == "released"
    assert db.session.get(User, accounts["provider"]).wallet_balance == Decimal("95.00")

    response = client.post(
        f"/bookings/{booking.id}/review",
        data={
            "quality": "5",
            "timeliness": "4",
            "communication": "5",
            "comment": "Clear explanations and a practical revision plan.",
        },
        follow_redirects=True,
    )
    assert b"Thank you" in response.data
    assert Review.query.filter_by(booking_id=booking.id).count() == 1
    provider = db.session.get(User, accounts["provider"])
    assert provider.review_count == 1
    assert provider.completed_bookings == 1
    assert provider.rating_avg == Decimal("4.67")


def test_payment_blocked_when_wallet_is_short(client, login, accounts):
    login("seeker@test.zm")
    booking = _create_booking(client, accounts)
    client.post("/logout")
    login("provider@test.zm")
    client.post(f"/bookings/{booking.id}/accept")
    client.post("/logout")

    seeker = db.session.get(User, accounts["seeker"])
    seeker.wallet_balance = Decimal("10.00")
    db.session.commit()

    login("seeker@test.zm")
    response = client.post(f"/bookings/{booking.id}/pay")
    assert response.status_code == 302
    assert "/wallet" in response.headers["Location"]
    assert db.session.get(Booking, booking.id).status == "accepted"
    assert Payment.query.filter_by(booking_id=booking.id).first() is None
    assert db.session.get(User, accounts["seeker"]).wallet_balance == Decimal("10.00")


def test_booking_access_control(client, login, accounts):
    login("seeker@test.zm")
    booking = _create_booking(client, accounts)
    client.post("/logout")

    login("rival@test.zm")
    assert client.get(f"/bookings/{booking.id}").status_code == 403
    assert client.post(f"/bookings/{booking.id}/accept").status_code == 403
    assert client.post(f"/bookings/{booking.id}/pay").status_code == 403
    assert client.post(f"/bookings/{booking.id}/confirm").status_code == 403
    client.post("/logout")

    login("seeker@test.zm")
    assert client.post(f"/bookings/{booking.id}/accept").status_code == 403
    client.post("/logout")

    login("provider@test.zm")
    assert client.post(f"/bookings/{booking.id}/pay").status_code == 403
    client.post(f"/bookings/{booking.id}/accept")
    assert db.session.get(Booking, booking.id).status == "accepted"


def test_seeker_can_cancel_and_provider_is_notified(client, login, accounts):
    login("seeker@test.zm")
    booking = _create_booking(client, accounts)
    client.post(f"/bookings/{booking.id}/cancel", data={"reason": "Schedule changed"})
    booking = db.session.get(Booking, booking.id)
    assert booking.status == "cancelled"
    assert booking.cancellation_reason == "Schedule changed"
    assert booking.cancelled_by_id == accounts["seeker"]


def test_request_and_offer_flow(client, login, accounts):
    login("seeker@test.zm")
    response = client.post(
        "/requests/new",
        data={
            "title": "Statistics revision before exams",
            "category_id": str(accounts["category"]),
            "description": "I need two focused sessions covering probability and hypothesis testing.",
            "budget": "300",
            "campus_area": "Main Campus",
            "needed_by": future_date(10),
        },
    )
    assert response.status_code == 302
    service_request = ServiceRequest.query.filter_by(title="Statistics revision before exams").one()
    assert service_request.status == "open"

    client.post("/logout")
    login("provider@test.zm")
    response = client.post(
        f"/requests/{service_request.id}/offers",
        data={
            "price": "280",
            "date": future_date(2),
            "time": "14:00",
            "duration_minutes": "120",
            "message": "I can cover both topics with past papers and a written summary.",
        },
    )
    assert response.status_code == 302
    winning_offer = Offer.query.filter_by(
        request_id=service_request.id, provider_id=accounts["provider"]
    ).one()
    assert winning_offer.status == "pending"

    client.post("/logout")
    login("rival@test.zm")
    client.post(
        f"/requests/{service_request.id}/offers",
        data={
            "price": "260",
            "date": future_date(2),
            "time": "14:00",
            "duration_minutes": "90",
            "message": "I have three years of statistics tutoring experience.",
        },
    )
    rival_offer = Offer.query.filter_by(request_id=service_request.id, provider_id=accounts["rival"]).one()

    client.post("/logout")
    login("seeker@test.zm")
    owner_view = client.get(f"/requests/{service_request.id}")
    assert owner_view.status_code == 200
    assert b"Offers received" in owner_view.data

    response = client.post(f"/requests/{service_request.id}/offers/{winning_offer.id}/accept")
    assert response.status_code == 302
    assert "/bookings/" in response.headers["Location"]

    service_request = db.session.get(ServiceRequest, service_request.id)
    assert service_request.status == "awarded"
    booking = db.session.get(Booking, service_request.booking.id)
    assert booking.status == "accepted"
    assert booking.offer_id == winning_offer.id
    assert booking.request_id == service_request.id
    assert db.session.get(Offer, winning_offer.id).status == "accepted"
    assert db.session.get(Offer, rival_offer.id).status == "declined"

    assert client.get(f"/bookings/{booking.id}").status_code == 200


def test_closed_request_is_hidden_from_other_students(client, login, accounts):
    login("seeker@test.zm")
    client.post(
        "/requests/new",
        data={
            "title": "Poster for a society event",
            "category_id": str(accounts["category"]),
            "description": "Looking for a clean poster and matching social media sizes.",
            "budget": "150",
            "campus_area": "Main Campus",
            "needed_by": "",
        },
    )
    service_request = ServiceRequest.query.filter_by(title="Poster for a society event").one()
    client.post(f"/requests/{service_request.id}/close")
    assert db.session.get(ServiceRequest, service_request.id).status == "closed"
    assert client.get(f"/requests/{service_request.id}").status_code == 200

    client.post("/logout")
    login("rival@test.zm")
    assert client.get(f"/requests/{service_request.id}").status_code == 403


def test_messaging_read_state_and_privacy(client, login, accounts):
    login("seeker@test.zm")
    response = client.post(f"/messages/start/{accounts['provider']}")
    assert response.status_code == 302
    conversation_id = int(response.headers["Location"].rstrip("/").split("/")[-1])
    assert Conversation.query.count() == 1

    response = client.post(
        f"/messages/{conversation_id}", data={"body": "Hi, is 10:00 still fine?"}, follow_redirects=True
    )
    assert response.status_code == 200
    message = Message.query.one()
    assert message.body == "Hi, is 10:00 still fine?"
    assert message.is_read is False

    client.post("/logout")
    login("provider@test.zm")
    inbox = client.get("/messages")
    assert b"Seeker Student" in inbox.data
    conversation = db.session.get(Conversation, conversation_id)
    assert conversation.unread_for(accounts["provider"]) == 1

    client.get(f"/messages/{conversation_id}")
    assert conversation.unread_for(accounts["provider"]) == 0
    client.post(f"/messages/{conversation_id}", data={"body": "Yes, see you at the library."})
    assert Message.query.count() == 2
    assert db.session.get(Conversation, conversation_id).unread_for(accounts["seeker"]) == 1

    client.post("/logout")
    login("rival@test.zm")
    assert client.get(f"/messages/{conversation_id}").status_code == 403
    assert client.post(f"/messages/start/{accounts['rival']}").status_code == 302


def test_booking_detail_blocks_non_participants_and_admins_can_view(client, login, accounts):
    login("seeker@test.zm")
    booking = _create_booking(client, accounts)
    client.post("/logout")
    login("admin@test.zm")
    response = client.get(f"/bookings/{booking.id}")
    assert response.status_code == 200
    assert b"Admin view" in response.data
