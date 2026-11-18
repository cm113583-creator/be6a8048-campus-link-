from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from .extensions import db
from .marketplace import MarketplaceError, get_or_create_conversation
from .models import Conversation, Message, User
from .notifications import notify

bp = Blueprint("messages", __name__)


def _conversations_for(user_id):
    return (
        Conversation.query.filter(
            or_(Conversation.user_a_id == user_id, Conversation.user_b_id == user_id)
        )
        .order_by(Conversation.last_message_at.desc())
        .all()
    )


def _inbox_items(user_id):
    conversations = _conversations_for(user_id)
    return [
        {
            "conversation": conversation,
            "other": conversation.user_b if conversation.user_a_id == user_id else conversation.user_a,
            "unread": conversation.unread_for(user_id),
            "last": conversation.messages.order_by(Message.created_at.desc()).first(),
        }
        for conversation in conversations
    ]


@bp.get("/messages")
@login_required
def inbox():
    return render_template("messages/inbox.html", items=_inbox_items(current_user.id))


@bp.post("/messages/start/<int:user_id>")
@login_required
def start(user_id):
    target = db.get_or_404(User, user_id)
    try:
        conversation = get_or_create_conversation(current_user.id, target.id)
        db.session.commit()
    except MarketplaceError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(request.referrer or url_for("main.home"))
    return redirect(url_for("messages.thread", conversation_id=conversation.id))


@bp.route("/messages/<int:conversation_id>", methods=["GET", "POST"])
@login_required
def thread(conversation_id):
    conversation = db.get_or_404(Conversation, conversation_id)
    if current_user.id not in (conversation.user_a_id, conversation.user_b_id):
        abort(403)
    other = conversation.other_user(current_user)

    if request.method == "POST":
        body = request.form.get("body", "").strip()
        if not body:
            flash("Write a message first.", "danger")
        elif len(body) > 2000:
            flash("Keep messages under 2,000 characters.", "danger")
        else:
            message = Message(
                conversation_id=conversation.id,
                sender_id=current_user.id,
                body=body,
                is_read=False,
            )
            conversation.last_message_at = datetime.now()
            db.session.add(message)
            notify(
                other,
                "New message",
                f"{current_user.full_name}: {body[:90]}{'…' if len(body) > 90 else ''}",
                link=f"/messages/{conversation.id}",
                category="message",
                email=True,
            )
            db.session.commit()
            return redirect(url_for("messages.thread", conversation_id=conversation.id) + "#latest")

    conversation.messages.filter(
        Message.sender_id != current_user.id, Message.is_read.is_(False)
    ).update({"is_read": True}, synchronize_session=False)
    db.session.commit()
    messages = conversation.messages.order_by(Message.created_at.asc()).all()
    return render_template(
        "messages/thread.html",
        conversation=conversation,
        other=other,
        messages=messages,
        items=_inbox_items(current_user.id),
    )
