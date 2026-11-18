from decimal import Decimal

from app.extensions import db
from app.models import Booking, Dispute, Payment, Service, User
from tests.helpers import future_date


def test_non_admin_cannot_access_admin(client, login):
    login("seeker@test.zm")
    for path in ("/admin/", "/admin/users", "/admin/listings", "/admin/disputes", "/admin/reports"):
        assert client.get(path).status_code == 403


def test_admin_pages_and_csv_exports(client, login):
    login("admin@test.zm")
    for path in (
        "/admin/",
        "/admin/users",
        "/admin/users?state=verified",
        "/admin/listings",
        "/admin/listings?status=active",
        "/admin/disputes",
        "/admin/disputes?state=all",
        "/admin/reports",
        "/admin/reports?days=90",
    ):
        assert client.get(path).status_code == 200, path

    bookings_csv = client.get("/admin/reports/bookings.csv")
    assert bookings_csv.status_code == 200
    assert bookings_csv.headers["Content-Type"].startswith("text/csv")
    assert bookings_csv.data.startswith(b"\xef\xbb\xbf")
    assert b"Reference" in bookings_csv.data

    users_csv = client.get("/admin/reports/users.csv")
    assert users_csv.status_code == 200
    assert users_csv.data.startswith(b"\xef\xbb\xbf")
    assert b"Student number" in users_csv.data


def test_admin_verify_suspend_and_restore_user(client, login, accounts):
    rival = db.session.get(User, accounts["rival"])
    listing = Service(
        provider_id=rival.id,
        category_id=accounts["category"],
        title="Rival tutoring",
        description="A listing used to verify admin moderation behaviour.",
        price=Decimal("80.00"),
        price_unit="per task",
        duration_minutes=60,
        campus_area="Main Campus",
        available_days="0,1,2,3,4",
        available_from="08:00",
        available_to="18:00",
        status="active",
    )
    db.session.add(listing)
    db.session.commit()

    login("admin@test.zm")
    client.post(f"/admin/users/{accounts['rival']}/verify")
    rival = db.session.get(User, accounts["rival"])
    assert rival.is_verified is False

    client.post(f"/admin/users/{accounts['rival']}/verify")
    assert db.session.get(User, accounts["rival"]).is_verified is True

    client.post(f"/admin/users/{accounts['rival']}/suspend", data={"reason": "Repeated no-shows"})
    rival = db.session.get(User, accounts["rival"])
    assert rival.is_suspended is True
    assert db.session.get(Service, listing.id).status == "suspended"

    client.post("/logout")
    response = client.post(
        "/login", data={"email": "rival@test.zm", "password": "Password1"}, follow_redirects=True
    )
    assert b"suspended" in response.data

    login("admin@test.zm")
    client.post(f"/admin/users/{accounts['rival']}/unsuspend")
    assert db.session.get(User, accounts["rival"]).is_suspended is False
    client.post(f"/admin/listings/{listing.id}/restore")
    assert db.session.get(Service, listing.id).status == "active"


def test_admin_suspend_and_restore_listing(client, login, accounts):
    login("admin@test.zm")
    client.post(f"/admin/listings/{accounts['service']}/suspend")
    assert db.session.get(Service, accounts["service"]).status == "suspended"
    browse = client.get("/services", query_string={"q": "Statistics tutoring"})
    assert b"0 results" in browse.data

    client.post(f"/admin/listings/{accounts['service']}/restore")
    assert db.session.get(Service, accounts["service"]).status == "active"
    assert client.get(f"/services/{accounts['service']}").status_code == 200


def test_admin_refunds_dispute_to_seeker(client, login, accounts, make_booking):
    booking = make_booking()
    login("seeker@test.zm")
    response = client.post(
        f"/bookings/{booking.id}/dispute",
        data={
            "reason": "Service not completed as described",
            "details": "The session ended early and the agreed topics were not covered.",
        },
    )
    assert response.status_code == 302
    booking = db.session.get(Booking, booking.id)
    assert booking.status == "disputed"
    dispute = Dispute.query.filter_by(booking_id=booking.id).one()

    client.post("/logout")
    login("admin@test.zm")
    assert client.get("/admin/disputes").status_code == 200
    assert client.get(f"/admin/disputes/{dispute.id}").status_code == 200

    response = client.post(
        f"/admin/disputes/{dispute.id}/resolve",
        data={"action": "refund", "resolution_note": "Refund approved after reviewing the timeline."},
    )
    assert response.status_code == 302

    booking = db.session.get(Booking, booking.id)
    dispute = db.session.get(Dispute, dispute.id)
    assert booking.status == "refunded"
    assert booking.payment.status == "refunded"
    assert dispute.status == "resolved_refund"
    assert dispute.resolved_by_id == accounts["admin"]
    assert db.session.get(User, accounts["seeker"]).wallet_balance == Decimal("500.00")

    client.post(
        f"/admin/disputes/{dispute.id}/resolve",
        data={"action": "refund", "resolution_note": "Trying to resolve twice."},
    )
    assert db.session.get(Dispute, dispute.id).status == "resolved_refund"


def test_admin_releases_dispute_to_provider(client, login, accounts, make_booking):
    booking = make_booking()
    login("provider@test.zm")
    client.post(
        f"/bookings/{booking.id}/dispute",
        data={
            "reason": "Seeker unavailable for handover",
            "details": "I delivered the work but the seeker has not confirmed completion.",
        },
    )
    dispute = Dispute.query.filter_by(booking_id=booking.id).one()

    client.post("/logout")
    login("admin@test.zm")
    client.post(
        f"/admin/disputes/{dispute.id}/resolve",
        data={"action": "release", "resolution_note": "Delivery evidence verified; release approved."},
    )

    booking = db.session.get(Booking, booking.id)
    assert booking.status == "completed"
    assert booking.payment.status == "released"
    assert booking.payment.platform_fee == Decimal("5.00")
    assert db.session.get(Dispute, dispute.id).status == "resolved_release"
    assert db.session.get(User, accounts["provider"]).wallet_balance == Decimal("95.00")


def test_admin_resolution_requires_note(client, login, accounts, make_booking):
    booking = make_booking()
    login("seeker@test.zm")
    client.post(
        f"/bookings/{booking.id}/dispute",
        data={
            "reason": "Work not delivered",
            "details": "The provider stopped responding after payment was secured.",
        },
    )
    dispute = Dispute.query.filter_by(booking_id=booking.id).one()

    client.post("/logout")
    login("admin@test.zm")
    response = client.post(
        f"/admin/disputes/{dispute.id}/resolve",
        data={"action": "refund", "resolution_note": "no"},
        follow_redirects=True,
    )
    assert b"short resolution note" in response.data
    assert db.session.get(Dispute, dispute.id).status == "open"
    assert db.session.get(Payment, booking.payment.id).status == "held"


def test_admin_cannot_use_student_marketplace(client, login, accounts):
    login("admin@test.zm")
    assert client.get("/requests/new").status_code == 403
    assert client.get("/services/new").status_code == 403
    response = client.post(
        f"/services/{accounts['service']}/book",
        data={
            "date": future_date(),
            "time": "10:00",
            "duration_minutes": "60",
            "location": "Library",
            "description": "Admin should not be able to book a service.",
        },
        follow_redirects=True,
    )
    assert b"Admin accounts cannot place bookings" in response.data
    assert Booking.query.count() == 0
