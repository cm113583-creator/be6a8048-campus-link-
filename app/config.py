import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "campuslink-dev-secret-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///campuslink.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PLATFORM_FEE_RATE = "0.05"
    CURRENCY = "ZMW"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True
    WTF_CSRF_TIME_LIMIT = None
    MAIL_OUTBOX = os.environ.get("MAIL_OUTBOX", "mail_outbox.log")
