import os
from decimal import Decimal, InvalidOperation

import click
from flask import Flask, flash, g, redirect, render_template, request, url_for
from flask_login import current_user, logout_user
from sqlalchemy import func, or_

from .config import Config
from .constants import APP_NAME, APP_TAGLINE, BOOKING_STATUSES, CAMPUS_AREAS, OFFER_STATUSES, REQUEST_STATUSES, SERVICE_STATUSES
from .extensions import csrf, db, login_manager


def create_app(config_object=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if config_object:
        app.config.update(config_object)

    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to continue."
    login_manager.login_message_category = "info"
    login_manager.session_protection = "basic"

    from . import admin, auth, bookings, listings, main, messages, requests
    from .models import Category, Conversation, Dispute, Message, Notification, User

    app.register_blueprint(main.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(listings.bp)
    app.register_blueprint(requests.bp)
    app.register_blueprint(bookings.bp)
    app.register_blueprint(messages.bp)
    app.register_blueprint(admin.bp)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.before_request
    def block_suspended_users():
        if current_user.is_authenticated and current_user.is_suspended:
            logout_user()
            flash("This account has been suspended. Contact the platform administrator.", "danger")
            return redirect(url_for("auth.login"))

    @app.context_processor
    def inject_globals():
        if "nav_categories" not in g:
            g.nav_categories = Category.query.order_by(Category.sort_order, Category.name).all()
        unread_messages = 0
        unread_notifications = 0
        open_disputes = 0
        if current_user.is_authenticated:
            unread_messages = (
                db.session.query(func.count(Message.id))
                .join(Conversation, Message.conversation_id == Conversation.id)
                .filter(
                    or_(
                        Conversation.user_a_id == current_user.id,
                        Conversation.user_b_id == current_user.id,
                    ),
                    Message.sender_id != current_user.id,
                    Message.is_read.is_(False),
                )
                .scalar()
                or 0
            )
            unread_notifications = Notification.query.filter_by(
                user_id=current_user.id, is_read=False
            ).count()
            if current_user.is_admin:
                open_disputes = Dispute.query.filter_by(status="open").count()
        return {
            "APP_NAME": APP_NAME,
            "APP_TAGLINE": APP_TAGLINE,
            "nav_categories": g.nav_categories,
            "CAMPUS_AREAS": CAMPUS_AREAS,
            "BOOKING_STATUSES": BOOKING_STATUSES,
            "REQUEST_STATUSES": REQUEST_STATUSES,
            "OFFER_STATUSES": OFFER_STATUSES,
            "SERVICE_STATUSES": SERVICE_STATUSES,
            "unread_messages": unread_messages,
            "unread_notifications": unread_notifications,
            "open_disputes": open_disputes,
        }

    @app.template_filter("money")
    def money_filter(value):
        if value is None or value == "":
            return "K0.00"
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return "K0.00"
        return f"K{amount:,.2f}"

    @app.template_filter("datetime")
    def datetime_filter(value, fmt="%d %b %Y, %H:%M"):
        return value.strftime(fmt) if value else ""

    @app.template_filter("date")
    def date_filter(value, fmt="%d %b %Y"):
        return value.strftime(fmt) if value else ""

    @app.template_filter("time")
    def time_filter(value, fmt="%H:%M"):
        return value.strftime(fmt) if value else ""

    @app.template_filter("nl2br")
    def nl2br_filter(value):
        from markupsafe import Markup, escape

        return Markup("<br>".join(escape(value or "").split("\n")))

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        return response

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("errors/error.html", code=403, title="Not allowed",
                               message="You do not have permission to view this page."), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/error.html", code=404, title="Page not found",
                               message="The page you are looking for may have been moved or removed."), 404

    @app.errorhandler(500)
    def server_error(_error):
        db.session.rollback()
        return render_template("errors/error.html", code=500, title="Something went wrong",
                               message="An unexpected error occurred. Please try again."), 500

    @app.cli.command("seed")
    @click.option("--reset", is_flag=True, help="Drop all tables before seeding.")
    def seed_command(reset):
        from .seed_data import seed_database

        seed_database(reset=reset)
        click.echo("CampusLink database seeded.")

    return app
