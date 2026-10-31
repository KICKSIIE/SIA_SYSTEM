from flask import Blueprint, redirect, render_template, session, url_for
from ..roles import roles_required

bp = Blueprint("dashboard", __name__)


@bp.route("/")
def index():
    role = session.get("role")
    if role is None:
        return redirect(url_for("auth.login"))
    # TODO: replace the placeholder numbers with real counts from the database
    return render_template("dashboard/%s.html" % role)


@bp.route("/reports")
@roles_required("owner")
def reports():
    return render_template("dashboard/reports.html")
