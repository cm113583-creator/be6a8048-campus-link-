from app.extensions import db
from app.models import Service, User
from tests.helpers import future_date


def test_public_pages_render(client):
    for path in ("/", "/services", "/login", "/register"):
        response = client.get(path)
        assert response.status_code == 200, path


def test_protected_pages_redirect_to_login(client):
    for path in ("/dashboard", "/bookings", "/requests", "/messages", "/wallet", "/admin/"):
        response = client.get(path)
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


def test_register_login_logout(client, app):
    response = client.post(
        "/register",
        data={
            "full_name": "New Student",
            "email": "new@student.test.zm",
            "student_number": "999-001",
            "phone": "+260 97 0000000",
            "program": "Bachelor of Law",
            "year_of_study": "Year 1",
            "campus_area": "Ridgeway",
            "password": "Password1",
            "confirm_password": "Password1",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Welcome to CampusLink" in response.data
    user = User.query.filter_by(email="new@student.test.zm").one()
    assert user.is_verified is False

    response = client.post("/logout", follow_redirects=True)
    assert b"You have been logged out" in response.data

    response = client.post(
        "/login", data={"email": "new@student.test.zm", "password": "Password1"}, follow_redirects=True
    )
    assert b"Welcome back" in response.data


def test_registration_rejects_weak_password_and_duplicate_email(client, accounts):
    response = client.post(
        "/register",
        data={
            "full_name": "Weak Password",
            "email": "weak@student.test.zm",
            "student_number": "999-002",
            "program": "Bachelor of Law",
            "year_of_study": "Year 1",
            "campus_area": "Ridgeway",
            "password": "short",
            "confirm_password": "short",
        },
    )
    assert response.status_code == 200
    assert b"Use at least 8 characters" in response.data
    assert User.query.filter_by(email="weak@student.test.zm").first() is None

    response = client.post(
        "/register",
        data={
            "full_name": "Duplicate Email",
            "email": "seeker@test.zm",
            "student_number": "999-003",
            "program": "Bachelor of Law",
            "year_of_study": "Year 1",
            "campus_area": "Ridgeway",
            "password": "Password1",
            "confirm_password": "Password1",
        },
    )
    assert b"already exists" in response.data


def test_suspended_user_cannot_log_in(client, app, accounts):
    rival = db.session.get(User, accounts["rival"])
    rival.is_suspended = True
    db.session.commit()

    response = client.post(
        "/login", data={"email": "rival@test.zm", "password": "Password1"}, follow_redirects=True
    )
    assert b"suspended" in response.data
    assert client.get("/dashboard").status_code == 302


def test_wallet_top_up_and_limits(login, client, accounts):
    login("rival@test.zm")
    response = client.post("/wallet", data={"amount": "250.50"}, follow_redirects=True)
    assert response.status_code == 200
    rival = db.session.get(User, accounts["rival"])
    assert rival.wallet_balance == 250.50

    client.post("/wallet", data={"amount": "0"}, follow_redirects=True)
    assert db.session.get(User, accounts["rival"]).wallet_balance == 250.50

    response = client.post("/wallet", data={"amount": "20001"}, follow_redirects=True)
    assert b"limited to K20,000" in response.data
    assert db.session.get(User, accounts["rival"]).wallet_balance == 250.50


def test_provider_creates_and_pauses_listing(login, client, accounts):
    login("provider@test.zm")
    response = client.post(
        "/services/new",
        data={
            "title": "Exam revision coaching",
            "category_id": str(accounts["category"]),
            "description": "A focused revision sprint covering past papers and exam technique.",
            "price": "150",
            "price_unit": "per hour",
            "duration_minutes": "90",
            "campus_area": "Main Campus",
            "available_days": ["0", "1", "2", "3", "4"],
            "available_from": "09:00",
            "available_to": "17:00",
        },
    )
    assert response.status_code == 302
    service = Service.query.filter_by(title="Exam revision coaching").one()
    assert service.status == "active"
    assert client.get(f"/services/{service.id}").status_code == 200

    client.post(f"/services/{service.id}/toggle")
    assert db.session.get(Service, service.id).status == "paused"
    browse = client.get("/services", query_string={"q": "Exam revision coaching"})
    assert b"0 results" in browse.data

    client.post(f"/services/{service.id}/toggle")
    assert db.session.get(Service, service.id).status == "active"


def test_non_owner_cannot_edit_listing(login, client, accounts):
    login("rival@test.zm")
    assert client.get(f"/services/{accounts['service']}/edit").status_code == 403


def test_booking_and_offer_pages_require_authentication(client, accounts):
    assert client.get(f"/services/{accounts['service']}").status_code == 200
    response = client.post(
        f"/services/{accounts['service']}/book",
        data={"date": future_date(), "time": "10:00", "location": "Library", "description": "Tutoring help"},
    )
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
