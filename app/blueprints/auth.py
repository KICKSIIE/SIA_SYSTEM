from flask import Blueprint, redirect, render_template, session, url_for, abort, flash
from ..roles import ROLE_LABELS
from .. import inventory_service as inv

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    # TODO: real login (check username and password hash in the users table).
    return render_template("login.html")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


def _set_session(role, user):
    session.clear()
    session["role"] = role
    session["user_id"] = user["id"] if user else None
    session["user_name"] = user["full_name"] if user else None
    session["location_id"] = user["location_id"] if user else None


@bp.route("/dev/role/<role>")
def dev_role(role):
    """TEMPORARY: preview a role. Logs in as the first active user with that role (if any)."""
    if role not in ROLE_LABELS:
        abort(404)
    try:
        user = inv.backend().one(
            "SELECT u.id, u.full_name, u.location_id FROM users u JOIN roles r ON r.id = u.role_id "
            "WHERE r.code = :c AND u.is_active ORDER BY u.id LIMIT 1", c=role)
    except Exception:          # no database yet: still let the screens be previewed
        user = None
    _set_session(role, user)
    if user is None:
        flash("No user with this role in the database yet (run database/seed_users.sql). "
              "Screens that save data will not work.", "info")
    return redirect(url_for("dashboard.index"))


@bp.route("/dev/user/<int:user_id>")
def dev_user(user_id):
    """TEMPORARY: log in as one specific user."""
    user = inv.backend().one(
        "SELECT u.id, u.full_name, u.location_id, r.code AS role FROM users u JOIN roles r ON r.id = u.role_id "
        "WHERE u.id = :i AND u.is_active", i=user_id)
    if user is None:
        abort(404)
    _set_session(user["role"], user)
    return redirect(url_for("dashboard.index"))
