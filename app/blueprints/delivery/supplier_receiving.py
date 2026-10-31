# Delivery: receiving goods from the supplier (RM) and discrepancy reports
from flask import render_template, request, redirect, url_for, flash
from ...roles import roles_required
from . import bp


@bp.route("/receiving")
@roles_required("warehouse_staff", "warehouse_manager")
def receiving_list():
    # TODO: query the database
    return render_template("delivery/receiving_list.html")


@bp.route("/receiving/<int:po_id>/check", methods=["GET", "POST"])
@roles_required("warehouse_staff", "warehouse_manager")
def receiving_check(po_id):
    # TODO: load the record(s) from the database and pre-fill the form (see database/schema.sql)
    if request.method == "POST":
        # TODO: validate, save to the database, write the audit log
        flash("Saving is not implemented yet.", "info")
        return redirect(url_for("purchasing.po_detail", po_id=po_id))
    return render_template("delivery/receiving_check.html", po_id=po_id)


@bp.route("/receiving/rm/<int:rm_id>")
@roles_required("warehouse_staff", "warehouse_manager", "owner")
def receiving_detail(rm_id):
    # TODO: query the database
    return render_template("delivery/receiving_detail.html", rm_id=rm_id)


@bp.route("/discrepancies")
@roles_required("warehouse_manager", "owner")
def discrepancy_list():
    # TODO: query the database
    return render_template("delivery/discrepancy_list.html")


@bp.route("/discrepancies/<int:report_id>", methods=["GET", "POST"])
@roles_required("warehouse_manager")
def discrepancy_detail(report_id):
    # TODO: load the record(s) from the database and pre-fill the form (see database/schema.sql)
    if request.method == "POST":
        # TODO: validate, save to the database, write the audit log
        flash("Saving is not implemented yet.", "info")
        return redirect(url_for("delivery.discrepancy_list"))
    return render_template("delivery/discrepancy_detail.html", report_id=report_id)
