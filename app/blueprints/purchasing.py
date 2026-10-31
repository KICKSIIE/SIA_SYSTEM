from flask import Blueprint, render_template, request, redirect, url_for, flash
from ..roles import roles_required

bp = Blueprint("purchasing", __name__, url_prefix="/purchasing")


@bp.route("/alerts")
@roles_required("warehouse_manager")
def alert_list():
    # TODO: query the database
    return render_template("purchasing/alert_list.html")


@bp.route("/alerts/<int:alert_id>")
@roles_required("warehouse_manager")
def alert_detail(alert_id):
    # TODO: query the database
    return render_template("purchasing/alert_detail.html", alert_id=alert_id)


@bp.route("/alerts/<int:alert_id>/dismiss", methods=["GET", "POST"])
@roles_required("warehouse_manager")
def alert_dismiss(alert_id):
    # TODO: load the record(s) from the database and pre-fill the form (see database/schema.sql)
    if request.method == "POST":
        # TODO: validate, save to the database, write the audit log
        flash("Saving is not implemented yet.", "info")
        return redirect(url_for("purchasing.alert_detail", alert_id=alert_id))
    return render_template("purchasing/alert_dismiss.html", alert_id=alert_id)


@bp.route("/ref")
@roles_required("warehouse_manager", "owner")
def ref_list():
    # TODO: query the database
    return render_template("purchasing/ref_list.html")


@bp.route("/ref/new", methods=["GET", "POST"])
@roles_required("warehouse_manager")
def ref_new():
    # TODO: load the record(s) from the database and pre-fill the form (see database/schema.sql)
    if request.method == "POST":
        # TODO: validate, save to the database, write the audit log
        flash("Saving is not implemented yet.", "info")
        return redirect(url_for("purchasing.ref_list"))
    return render_template("purchasing/ref_new.html")


@bp.route("/ref/<int:ref_id>")
@roles_required("warehouse_manager", "owner")
def ref_detail(ref_id):
    # TODO: query the database
    return render_template("purchasing/ref_detail.html", ref_id=ref_id)


@bp.route("/ref/<int:ref_id>/cancel", methods=["GET", "POST"])
@roles_required("warehouse_manager")
def ref_cancel(ref_id):
    # TODO: load the record(s) from the database and pre-fill the form (see database/schema.sql)
    if request.method == "POST":
        # TODO: validate, save to the database, write the audit log
        flash("Saving is not implemented yet.", "info")
        return redirect(url_for("purchasing.ref_detail", ref_id=ref_id))
    return render_template("purchasing/ref_cancel.html", ref_id=ref_id)


@bp.route("/ref/<int:ref_id>/rfq/new", methods=["GET", "POST"])
@roles_required("warehouse_manager")
def rfq_new(ref_id):
    # TODO: load the record(s) from the database and pre-fill the form (see database/schema.sql)
    if request.method == "POST":
        # TODO: validate, save to the database, write the audit log
        flash("Saving is not implemented yet.", "info")
        return redirect(url_for("purchasing.ref_detail", ref_id=ref_id))
    return render_template("purchasing/rfq_new.html", ref_id=ref_id)


@bp.route("/ref/<int:ref_id>/quotation/new", methods=["GET", "POST"])
@roles_required("warehouse_manager")
def quotation_new(ref_id):
    # TODO: load the record(s) from the database and pre-fill the form (see database/schema.sql)
    if request.method == "POST":
        # TODO: validate, save to the database, write the audit log
        flash("Saving is not implemented yet.", "info")
        return redirect(url_for("purchasing.ref_detail", ref_id=ref_id))
    return render_template("purchasing/quotation_new.html", ref_id=ref_id)


@bp.route("/ref/<int:ref_id>/compare", methods=["GET", "POST"])
@roles_required("warehouse_manager")
def ref_compare(ref_id):
    # TODO: load the record(s) from the database and pre-fill the form (see database/schema.sql)
    if request.method == "POST":
        # TODO: validate, save to the database, write the audit log
        flash("Saving is not implemented yet.", "info")
        return redirect(url_for("purchasing.ref_detail", ref_id=ref_id))
    return render_template("purchasing/ref_compare.html", ref_id=ref_id)


@bp.route("/approvals")
@roles_required("owner", "warehouse_manager")
def approval_list():
    # TODO: query the database
    return render_template("purchasing/approval_list.html")


@bp.route("/approvals/<int:approval_id>", methods=["GET", "POST"])
@roles_required("owner")
def approval_detail(approval_id):
    # TODO: load the record(s) from the database and pre-fill the form (see database/schema.sql)
    if request.method == "POST":
        # TODO: validate, save to the database, write the audit log
        flash("Saving is not implemented yet.", "info")
        return redirect(url_for("purchasing.approval_list"))
    return render_template("purchasing/approval_detail.html", approval_id=approval_id)


@bp.route("/po")
@roles_required("warehouse_manager", "owner", "warehouse_staff")
def po_list():
    # TODO: query the database
    return render_template("purchasing/po_list.html")


@bp.route("/po/<int:po_id>")
@roles_required("warehouse_manager", "owner", "warehouse_staff")
def po_detail(po_id):
    # TODO: query the database
    return render_template("purchasing/po_detail.html", po_id=po_id)


@bp.route("/suppliers")
@roles_required("warehouse_manager", "owner")
def supplier_list():
    # TODO: query the database
    return render_template("purchasing/supplier_list.html")


@bp.route("/suppliers/new", methods=["GET", "POST"])
@roles_required("warehouse_manager")
def supplier_new():
    # TODO: load the record(s) from the database and pre-fill the form (see database/schema.sql)
    if request.method == "POST":
        # TODO: validate, save to the database, write the audit log
        flash("Saving is not implemented yet.", "info")
        return redirect(url_for("purchasing.supplier_list"))
    return render_template("purchasing/supplier_new.html")


@bp.route("/suppliers/<int:supplier_id>/edit", methods=["GET", "POST"])
@roles_required("warehouse_manager")
def supplier_edit(supplier_id):
    # TODO: load the record(s) from the database and pre-fill the form (see database/schema.sql)
    if request.method == "POST":
        # TODO: validate, save to the database, write the audit log
        flash("Saving is not implemented yet.", "info")
        return redirect(url_for("purchasing.supplier_list"))
    return render_template("purchasing/supplier_edit.html", supplier_id=supplier_id)
