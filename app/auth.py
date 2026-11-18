import re
import time

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_user, logout_user

from .constants import CAMPUS_AREAS, PROGRAMS, YEAR_OPTIONS
from .extensions import db
from .models import User
from .notifications import notify
from .utils import safe_next_url

bp = Blueprint("auth", __name__)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    form = {}
    errors = {}
    if request.method == "POST":
        form = {
            "full_name": request.form.get("full_name", "").strip(),
            "email": request.form.get("email", "").strip().lower(),
            "student_number": request.form.get("student_number", "").strip().upper(),
            "phone": request.form.get("phone", "").strip(),
            "program": request.form.get("program", "").strip(),
            "year_of_study": request.form.get("year_of_study", "").strip(),
            "campus_area": request.form.get("campus_area", "").strip(),
        }
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if len(form["full_name"]) < 3:
            errors["full_name"] = "Enter your full name."
        if not EMAIL_RE.match(form["email"]) or len(form["email"]) > 255:
            errors["email"] = "Enter a valid email address."
        elif User.query.filter_by(email=form["email"]).first():
            errors["email"] = "An account with this email already exists."
        if not re.fullmatch(r"[A-Za-z0-9\-/]{3,40}", form["student_number"]):
            errors["student_number"] = "Enter a valid student number (letters, numbers, - or /)."
        elif User.query.filter_by(student_number=form["student_number"]).first():
            errors["student_number"] = "This student number is already registered."
        if form["phone"] and not re.fullmatch(r"[0-9+\s\-]{7,20}", form["phone"]):
            errors["phone"] = "Enter a valid phone number."
        if form["program"] not in PROGRAMS:
            errors["program"] = "Select your programme."
        if form["year_of_study"] not in YEAR_OPTIONS:
            errors["year_of_study"] = "Select your year of study."
        if form["campus_area"] not in CAMPUS_AREAS:
            errors["campus_area"] = "Select your campus area."
        if len(password) < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
            errors["password"] = "Use at least 8 characters, including a letter and a number."
        if password != confirm:
            errors["confirm_password"] = "Passwords do not match."

        if not errors:
            user = User(
                full_name=form["full_name"],
                email=form["email"],
                student_number=form["student_number"],
                phone=form["phone"] or None,
                program=form["program"],
                year_of_study=form["year_of_study"],
                campus_area=form["campus_area"],
                role="student",
            )
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            notify(
                user,
                "Welcome to CampusLink",
                "Your account is ready. Browse services, post a request, or create your first listing.",
                link="/dashboard",
                category="account",
                email=True,
            )
            db.session.commit()
            login_user(user)
            flash("Welcome to CampusLink! Your account has been created.", "success")
            return redirect(url_for("main.dashboard"))

        flash("Please check the highlighted fields.", "danger")

    return render_template("auth/register.html", form=form, errors=errors, programs=PROGRAMS, years=YEAR_OPTIONS)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = {}
    error = None
    if request.method == "POST":
        form["email"] = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        attempts = [t for t in session.get("login_attempts", []) if time.time() - t < 300]
        if len(attempts) >= 5:
            error = "Too many failed attempts. Try again in a few minutes."
        else:
            user = User.query.filter_by(email=form["email"]).first()
            if user is None or not user.check_password(password):
                attempts.append(time.time())
                session["login_attempts"] = attempts
                error = "Email or password is incorrect."
            elif user.is_suspended:
                error = "This account has been suspended. Contact the platform administrator."
            else:
                session.pop("login_attempts", None)
                login_user(user, remember=bool(request.form.get("remember")))
                flash(f"Welcome back, {user.first_name}.", "success")
                target = safe_next_url(request.args.get("next")) or safe_next_url(request.form.get("next"))
                return redirect(target or url_for("main.dashboard"))
        flash(error, "danger")

    return render_template("auth/login.html", form=form, error=error)


@bp.post("/logout")
def logout():
    if current_user.is_authenticated:
        logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.home"))
