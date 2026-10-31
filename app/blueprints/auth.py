from flask import Blueprint, redirect, render_template, session, url_for, abort, flash
from ..roles import ROLE_LABELS

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    # TODO: real login (check username and password hash in the users table).
    return render_template("login.html")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/dev/role/<role>")
def dev_role(role):
    """TEMPORARY: pick a role to preview its screens. Remove when the real login is done."""
    if role not in ROLE_LABELS:
        abort(404)
    session["role"] = role
    return redirect(url_for("dashboard.index"))
