from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import Category, Service, User

PASSWORD_HASH = generate_password_hash("Password1")


def _make_user(name, email, role="student", balance="0.00", verified=True):
    user = User(
        full_name=name,
        email=email,
        student_number=email.split("@")[0].upper(),
        program="Bachelor of Science in Computing",
        year_of_study="Year 3",
        campus_area="Main Campus",
        is_verified=verified,
        role=role,
        wallet_balance=Decimal(balance),
    )
    user.password_hash = PASSWORD_HASH
    db.session.add(user)
    return user


@pytest.fixture()
def app(tmp_path):
    application = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
            "WTF_CSRF_ENABLED": False,
            "SECRET_KEY": "test-secret",
            "MAIL_OUTBOX": "test-mail.log",
        }
    )
    with application.app_context():
        db.create_all()
        admin = _make_user("Admin User", "admin@test.zm", role="admin")
        seeker = _make_user("Seeker Student", "seeker@test.zm", balance="500.00")
        provider = _make_user("Provider Student", "provider@test.zm")
        rival = _make_user("Rival Student", "rival@test.zm")
        category = Category(
            name="Tutoring",
            slug="tutoring",
            description="One-to-one academic support",
            icon="bi-mortarboard",
            color="#2563EB",
            sort_order=0,
        )
        db.session.add(category)
        db.session.flush()
        service = Service(
            provider_id=provider.id,
            category_id=category.id,
            title="Statistics tutoring",
            description="Patient one-to-one statistics tutoring using past papers and worked examples.",
            price=Decimal("100.00"),
            price_unit="per task",
            duration_minutes=60,
            campus_area="Main Campus",
            available_days="0,1,2,3,4,5,6",
            available_from="08:00",
            available_to="18:00",
            status="active",
        )
        db.session.add(service)
        db.session.commit()
        application.config["TEST_IDS"] = {
            "admin": admin.id,
            "seeker": seeker.id,
            "provider": provider.id,
            "rival": rival.id,
            "category": category.id,
            "service": service.id,
        }
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def login(client):
    def _login(email, password="Password1"):
        return client.post("/login", data={"email": email, "password": password}, follow_redirects=True)

    return _login


@pytest.fixture()
def accounts(app):
    return app.config["TEST_IDS"]


def future_date(days=1):
    return (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")


@pytest.fixture()
def make_booking(client, login, accounts, app):
    from app.marketplace import hold_escrow, next_reference
    from app.models import Booking

    def _make(status="accepted", escrow=True, price="100.00"):
        booking = Booking(
            seeker_id=accounts["seeker"],
            provider_id=accounts["provider"],
            service_id=accounts["service"],
            category_id=accounts["category"],
            title="Statistics tutoring",
            description="Help with hypothesis testing before the exam.",
            price=Decimal(price),
            scheduled_at=datetime.now() + timedelta(days=2),
            duration_minutes=60,
            location="Main Campus",
            status="accepted",
        )
        db.session.add(booking)
        db.session.flush()
        next_reference(booking)
        if escrow:
            hold_escrow(booking)
        if status != "accepted" and status != "in_escrow":
            booking.status = status
        db.session.commit()
        return booking

    return _make
