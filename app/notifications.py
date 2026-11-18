from .extensions import db
from .models import Notification, User
from .utils import log_email


def notify(user, title, body=None, link=None, category="system", email=False):
    notification = Notification(
        user_id=user.id,
        title=title,
        body=body,
        link=link,
        category=category,
    )
    db.session.add(notification)
    if email and user.email:
        log_email(user.email, title, body or title)
    return notification


def notify_admins(title, body=None, link=None, category="system"):
    admins = User.query.filter_by(role="admin", is_suspended=False).all()
    for admin in admins:
        notify(admin, title, body, link, category=category)
    return len(admins)
