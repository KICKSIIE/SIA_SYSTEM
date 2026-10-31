from flask import Blueprint, render_template, request, redirect, url_for, flash
from ..roles import roles_required

bp = Blueprint("requisition", __name__, url_prefix="/requisition")


@bp.route("/alerts")
@roles_required("shop_manager")
def alert_list():
    # TODO: query the database
    return render_template("requisition/alert_list.html")


@bp.route("/alerts/<int:alert_id>")
@roles_required("shop_manager")
def alert_detail(alert_id):
    # TODO: query the database
    return render_template("requisition/alert_detail.html", alert_id=alert_id)


@bp.route("/alerts/<int:alert_id>/dismiss", methods=["GET", "POST"])
@roles_required("shop_manager")
def alert_dismiss(alert_id):
    # TODO: load the record(s) from the database and pre-fill the form (see database/schema.sql)
    if request.method == "POST":
        # TODO: validate, save to the database, write the audit log
        flash("Saving is not implemented yet.", "info")
        return redirect(url_for("requisition.alert_detail", alert_id=alert_id))
    return render_template("requisition/alert_dismiss.html", alert_id=alert_id)


@bp.route("/rf")
@roles_required("shop_manager", "warehouse_manager", "owner")
def rf_list():
    # TODO: query the database
    return render_template("requisition/rf_list.html")


@bp.route("/rf/new", methods=["GET", "POST"])
@roles_required("shop_manager")
def rf_new():
    # TODO: load the record(s) from the database and pre-fill the form (see database/schema.sql)
    if request.method == "POST":
        # TODO: validate, save to the database, write the audit log
        flash("Saving is not implemented yet.", "info")
        return redirect(url_for("requisition.rf_list"))
    return render_template("requisition/rf_new.html")


@bp.route("/rf/<int:rf_id>")
@roles_required("shop_manager", "warehouse_manager", "owner")
def rf_detail(rf_id):
    # TODO: query the database
    return render_template("requisition/rf_detail.html", rf_id=rf_id)


@bp.route("/rf/<int:rf_id>/cancel", methods=["GET", "POST"])
@roles_required("shop_manager")
def rf_cancel(rf_id):
    # TODO: load the record(s) from the database and pre-fill the form (see database/schema.sql)
    if request.method == "POST":
        # TODO: validate, save to the database, write the audit log
        flash("Saving is not implemented yet.", "info")
        return redirect(url_for("requisition.rf_detail", rf_id=rf_id))
    return render_template("requisition/rf_cancel.html", rf_id=rf_id)
