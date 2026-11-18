import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "campuslink-dev-secret-change-me")
    database_url = os.environ.get("DATABASE_URL")
    if database_url and database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = database_url or "sqlite:///campuslink.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PLATFORM_FEE_RATE = "0.05"
    CURRENCY = "ZMW"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True
    WTF_CSRF_TIME_LIMIT = None
    MAIL_OUTBOX = os.environ.get("MAIL_OUTBOX", "mail_outbox.log")
