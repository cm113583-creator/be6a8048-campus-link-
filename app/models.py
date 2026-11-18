from datetime import datetime
from decimal import Decimal

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .constants import BOOKING_STATUSES, OFFER_STATUSES, REQUEST_STATUSES, SERVICE_STATUSES
from .extensions import db


def now():
    return datetime.now()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    student_number = db.Column(db.String(40), unique=True, nullable=False)
    phone = db.Column(db.String(30))
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="student")
    program = db.Column(db.String(120))
    year_of_study = db.Column(db.String(30))
    campus_area = db.Column(db.String(60))
    bio = db.Column(db.Text)
    skills = db.Column(db.String(255))
    is_verified = db.Column(db.Boolean, nullable=False, default=False)
    is_suspended = db.Column(db.Boolean, nullable=False, default=False)
    wallet_balance = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))

    rating_avg = db.Column(db.Numeric(3, 2))
    review_count = db.Column(db.Integer, nullable=False, default=0)
    completed_bookings = db.Column(db.Integer, nullable=False, default=0)
    completion_rate = db.Column(db.Numeric(5, 2))
    reputation_score = db.Column(db.Numeric(3, 2))

    created_at = db.Column(db.DateTime, nullable=False, default=now)

    listings = db.relationship("Service", back_populates="provider", lazy="dynamic")
    reviews_received = db.relationship(
        "Review", back_populates="provider", foreign_keys="Review.provider_id", lazy="dynamic"
    )
    notifications = db.relationship("Notification", back_populates="user", lazy="dynamic")
    wallet_transactions = db.relationship(
        "WalletTransaction", back_populates="user", lazy="dynamic", order_by="WalletTransaction.created_at.desc()"
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == "admin"

    @property
    def first_name(self):
        return self.full_name.split()[0] if self.full_name else "Student"

    @property
    def initials(self):
        parts = [p for p in (self.full_name or "").split() if p]
        return "".join(p[0] for p in parts[:2]).upper() or "?"

    @property
    def avatar_tone(self):
        return (self.id or 0) % 6

    @property
    def skills_list(self):
        return [s.strip() for s in (self.skills or "").split(",") if s.strip()]

    @property
    def rating_stars(self):
        return float(self.rating_avg or 0)

    @property
    def rating_display(self):
        return f"{float(self.rating_avg):.1f}" if self.rating_avg is not None else "New"

    @property
    def completion_display(self):
        return f"{float(self.completion_rate):.0f}%" if self.completion_rate is not None else "—"

    @property
    def active_listings(self):
        return self.listings.filter_by(status="active").count()

    def __repr__(self):
        return f"<User {self.full_name}>"


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    slug = db.Column(db.String(80), unique=True, nullable=False, index=True)
    description = db.Column(db.String(255))
    icon = db.Column(db.String(60), nullable=False, default="bi-grid")
    color = db.Column(db.String(20), nullable=False, default="#0F6B4F")
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    services = db.relationship("Service", back_populates="category", lazy="dynamic")
    requests = db.relationship("ServiceRequest", back_populates="category", lazy="dynamic")

    def __repr__(self):
        return f"<Category {self.name}>"


class Service(db.Model):
    __tablename__ = "services"

    id = db.Column(db.Integer, primary_key=True)
    provider_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False, index=True)
    title = db.Column(db.String(140), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    price_unit = db.Column(db.String(20), nullable=False, default="per task")
    duration_minutes = db.Column(db.Integer, nullable=False, default=60)
    campus_area = db.Column(db.String(60), nullable=False)
    available_days = db.Column(db.String(20), nullable=False, default="0,1,2,3,4")
    available_from = db.Column(db.String(5), nullable=False, default="08:00")
    available_to = db.Column(db.String(5), nullable=False, default="18:00")
    status = db.Column(db.String(20), nullable=False, default="active", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=now)
    updated_at = db.Column(db.DateTime, nullable=False, default=now, onupdate=now)

    provider = db.relationship("User", back_populates="listings")
    category = db.relationship("Category", back_populates="services")
    bookings = db.relationship("Booking", back_populates="service", lazy="dynamic")

    @property
    def day_numbers(self):
        return [int(d) for d in (self.available_days or "").split(",") if d.strip().isdigit()]

    @property
    def availability_summary(self):
        days = sorted(self.day_numbers)
        if not days:
            return "By arrangement"
        if days == list(range(5)):
            day_text = "Mon–Fri"
        elif days == [5, 6]:
            day_text = "Weekends"
        elif days == list(range(7)):
            day_text = "Every day"
        else:
            short = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}
            day_text = ", ".join(short[d] for d in days)
        return f"{day_text} · {self.available_from}–{self.available_to}"

    @property
    def status_meta(self):
        return SERVICE_STATUSES.get(self.status, {"label": self.status, "color": "secondary"})

    @property
    def is_live(self):
        return self.status == "active" and not self.provider.is_suspended

    def quote(self, minutes):
        minutes = int(minutes)
        if self.price_unit == "per hour":
            amount = Decimal(self.price) * Decimal(minutes) / Decimal(60)
            return amount.quantize(Decimal("0.01"))
        return Decimal(self.price).quantize(Decimal("0.01"))

    def __repr__(self):
        return f"<Service {self.title}>"


class Booking(db.Model):
    __tablename__ = "bookings"

    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(24), unique=True, index=True)
    seeker_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    provider_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    service_id = db.Column(db.Integer, db.ForeignKey("services.id"), nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True, index=True)
    request_id = db.Column(db.Integer, db.ForeignKey("service_requests.id"), nullable=True)
    offer_id = db.Column(db.Integer, db.ForeignKey("offers.id"), nullable=True)

    title = db.Column(db.String(140), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    scheduled_at = db.Column(db.DateTime, nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=False, default=60)
    location = db.Column(db.String(120), nullable=False)
    special_requirements = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    cancellation_reason = db.Column(db.Text)
    cancelled_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, nullable=False, default=now)
    accepted_at = db.Column(db.DateTime)
    paid_at = db.Column(db.DateTime)
    delivered_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    cancelled_at = db.Column(db.DateTime)

    seeker = db.relationship("User", foreign_keys=[seeker_id])
    provider = db.relationship("User", foreign_keys=[provider_id])
    cancelled_by = db.relationship("User", foreign_keys=[cancelled_by_id])
    service = db.relationship("Service", back_populates="bookings")
    category = db.relationship("Category")
    request = db.relationship("ServiceRequest", back_populates="booking")
    offer = db.relationship("Offer", back_populates="booking")
    payment = db.relationship("Payment", back_populates="booking", uselist=False)
    review = db.relationship("Review", back_populates="booking", uselist=False)
    dispute = db.relationship("Dispute", back_populates="booking", uselist=False)

    @property
    def status_meta(self):
        return BOOKING_STATUSES.get(self.status, {"label": self.status, "color": "secondary"})

    @property
    def ends_at(self):
        from datetime import timedelta

        return self.scheduled_at + timedelta(minutes=self.duration_minutes or 60)

    @property
    def is_participant(self):
        from flask_login import current_user

        return current_user.is_authenticated and current_user.id in (self.seeker_id, self.provider_id)

    def other_party(self, user):
        return self.provider if user.id == self.seeker_id else self.seeker

    def quantity_label(self):
        minutes = self.duration_minutes or 60
        if minutes % 60 == 0:
            return f"{minutes // 60} hour{'s' if minutes > 60 else ''}"
        return f"{minutes} minutes"

    def __repr__(self):
        return f"<Booking {self.reference}>"


class ServiceRequest(db.Model):
    __tablename__ = "service_requests"

    id = db.Column(db.Integer, primary_key=True)
    seeker_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False)
    title = db.Column(db.String(140), nullable=False)
    description = db.Column(db.Text, nullable=False)
    budget = db.Column(db.Numeric(10, 2), nullable=False)
    campus_area = db.Column(db.String(60), nullable=False)
    needed_by = db.Column(db.Date)
    status = db.Column(db.String(20), nullable=False, default="open", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=now)

    seeker = db.relationship("User", foreign_keys=[seeker_id])
    category = db.relationship("Category", back_populates="requests")
    offers = db.relationship("Offer", back_populates="request", lazy="dynamic", cascade="all, delete-orphan")
    booking = db.relationship("Booking", back_populates="request", uselist=False)

    @property
    def status_meta(self):
        return REQUEST_STATUSES.get(self.status, {"label": self.status, "color": "secondary"})

    @property
    def offer_count(self):
        return self.offers.count()

    def has_offer_from(self, user_id):
        return self.offers.filter_by(provider_id=user_id).first() is not None

    def __repr__(self):
        return f"<ServiceRequest {self.title}>"


class Offer(db.Model):
    __tablename__ = "offers"
    __table_args__ = (db.UniqueConstraint("request_id", "provider_id", name="uq_offer_provider_request"),)

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey("service_requests.id"), nullable=False, index=True)
    provider_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    proposed_at = db.Column(db.DateTime, nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=False, default=60)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    created_at = db.Column(db.DateTime, nullable=False, default=now)

    request = db.relationship("ServiceRequest", back_populates="offers")
    provider = db.relationship("User", foreign_keys=[provider_id])
    booking = db.relationship("Booking", back_populates="offer", uselist=False)

    @property
    def status_meta(self):
        return OFFER_STATUSES.get(self.status, {"label": self.status, "color": "secondary"})

    def __repr__(self):
        return f"<Offer {self.id} K{self.price}>"


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("bookings.id"), unique=True, nullable=False, index=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    platform_fee = db.Column(db.Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    provider_amount = db.Column(db.Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    status = db.Column(db.String(20), nullable=False, default="held")
    created_at = db.Column(db.DateTime, nullable=False, default=now)
    released_at = db.Column(db.DateTime)
    refunded_at = db.Column(db.DateTime)

    booking = db.relationship("Booking", back_populates="payment")

    @property
    def status_label(self):
        return {"held": "Held in escrow", "released": "Released to provider", "refunded": "Refunded to seeker"}.get(
            self.status, self.status
        )

    def __repr__(self):
        return f"<Payment booking={self.booking_id} {self.status}>"


class Review(db.Model):
    __tablename__ = "reviews"
    __table_args__ = (
        db.CheckConstraint("quality BETWEEN 1 AND 5", name="ck_review_quality"),
        db.CheckConstraint("timeliness BETWEEN 1 AND 5", name="ck_review_timeliness"),
        db.CheckConstraint("communication BETWEEN 1 AND 5", name="ck_review_communication"),
    )

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("bookings.id"), unique=True, nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    provider_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    quality = db.Column(db.Integer, nullable=False)
    timeliness = db.Column(db.Integer, nullable=False)
    communication = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=now)

    booking = db.relationship("Booking", back_populates="review")
    author = db.relationship("User", foreign_keys=[author_id])
    provider = db.relationship("User", foreign_keys=[provider_id], back_populates="reviews_received")

    @property
    def overall(self):
        return round((self.quality + self.timeliness + self.communication) / 3, 1)

    def __repr__(self):
        return f"<Review booking={self.booking_id} {self.overall}>"


class Dispute(db.Model):
    __tablename__ = "disputes"

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("bookings.id"), unique=True, nullable=False, index=True)
    opened_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    reason = db.Column(db.String(120), nullable=False)
    details = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(24), nullable=False, default="open", index=True)
    resolution_note = db.Column(db.Text)
    resolved_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, nullable=False, default=now)
    resolved_at = db.Column(db.DateTime)

    booking = db.relationship("Booking", back_populates="dispute")
    opened_by = db.relationship("User", foreign_keys=[opened_by_id])
    resolved_by = db.relationship("User", foreign_keys=[resolved_by_id])

    @property
    def status_meta(self):
        if self.status == "open":
            return {"label": "Open", "color": "danger"}
        if self.status == "resolved_refund":
            return {"label": "Resolved · refunded", "color": "success"}
        return {"label": "Resolved · released", "color": "success"}

    def __repr__(self):
        return f"<Dispute booking={self.booking_id} {self.status}>"


class Conversation(db.Model):
    __tablename__ = "conversations"
    __table_args__ = (db.UniqueConstraint("user_a_id", "user_b_id", name="uq_conversation_pair"),)

    id = db.Column(db.Integer, primary_key=True)
    user_a_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    user_b_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=now)
    last_message_at = db.Column(db.DateTime, nullable=False, default=now)

    user_a = db.relationship("User", foreign_keys=[user_a_id])
    user_b = db.relationship("User", foreign_keys=[user_b_id])
    messages = db.relationship(
        "Message", back_populates="conversation", lazy="dynamic", cascade="all, delete-orphan"
    )

    @staticmethod
    def pair_ids(user_a_id, user_b_id):
        return (min(user_a_id, user_b_id), max(user_a_id, user_b_id))

    def other_user(self, user):
        return self.user_b if user.id == self.user_a_id else self.user_a

    def unread_for(self, user_id):
        return self.messages.filter_by(is_read=False).filter(Message.sender_id != user_id).count()

    def __repr__(self):
        return f"<Conversation {self.user_a_id}-{self.user_b_id}>"


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id"), nullable=False, index=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    body = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=now)

    conversation = db.relationship("Conversation", back_populates="messages")
    sender = db.relationship("User", foreign_keys=[sender_id])

    def __repr__(self):
        return f"<Message {self.id}>"


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    category = db.Column(db.String(30), nullable=False, default="system")
    title = db.Column(db.String(140), nullable=False)
    body = db.Column(db.String(300))
    link = db.Column(db.String(255))
    is_read = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=now)

    user = db.relationship("User", back_populates="notifications")

    def __repr__(self):
        return f"<Notification {self.title}>"


class WalletTransaction(db.Model):
    __tablename__ = "wallet_transactions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    balance_after = db.Column(db.Numeric(12, 2), nullable=False)
    kind = db.Column(db.String(24), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    booking_id = db.Column(db.Integer, db.ForeignKey("bookings.id"))
    created_at = db.Column(db.DateTime, nullable=False, default=now)

    user = db.relationship("User", back_populates="wallet_transactions")
    booking = db.relationship("Booking")

    @property
    def is_credit(self):
        return Decimal(self.amount) > 0

    def __repr__(self):
        return f"<WalletTransaction {self.kind} {self.amount}>"
