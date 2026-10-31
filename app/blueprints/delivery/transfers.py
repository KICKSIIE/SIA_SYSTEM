# Delivery: transfer slips (assign driver and vehicle, loading check, release), drivers, vehicles
from flask import render_template, request, redirect, url_for, flash
from ...roles import roles_required
from . import bp


@bp.route("/transfers")
@roles_required("warehouse_manager", "warehouse_staff", "owner")
def transfer_list():
    # TODO: query the database
    return render_template("delivery/transfer_list.html")


@bp.route("/transfers/<int:ts_id>")
@roles_required("warehouse_manager", "warehouse_staff", "shop_manager", "owner")
def transfer_detail(ts_id):
    # TODO: query the database
    return render_template("delivery/transfer_detail.html", ts_id=ts_id)


@bp.route("/transfers/<int:ts_id>/assign", methods=["GET", "POST"])
@roles_required("warehouse_manager")
def transfer_assign(ts_id):
    # TODO: load the record(s) from the database and pre-fill the form (see database/schema.sql)
    if request.method == "POST":
        # TODO: validate, save to the database, write the audit log
        flash("Saving is not implemented yet.", "info")
        return redirect(url_for("delivery.transfer_detail", ts_id=ts_id))
    return render_template("delivery/transfer_assign.html", ts_id=ts_id)


@bp.route("/transfers/<int:ts_id>/load", methods=["GET", "POST"])
@roles_required("warehouse_staff")
def transfer_load(ts_id):
    # TODO: load the record(s) from the database and pre-fill the form (see database/schema.sql)
    if request.method == "POST":
        # TODO: validate, save to the database, write the audit log
        flash("Saving is not implemented yet.", "info")
        return redirect(url_for("delivery.transfer_detail", ts_id=ts_id))
    return render_template("delivery/transfer_load.html", ts_id=ts_id)


@bp.route("/transfers/<int:ts_id>/release", methods=["GET", "POST"])
@roles_required("warehouse_manager")
def transfer_release(ts_id):
    # TODO: load the record(s) from the database and pre-fill the form (see database/schema.sql)
    if request.method == "POST":
        # TODO: validate, save to the database, write the audit log
        flash("Saving is not implemented yet.", "info")
        return redirect(url_for("delivery.transfer_detail", ts_id=ts_id))
    return render_template("delivery/transfer_release.html", ts_id=ts_id)


@bp.route("/drivers")
@roles_required("warehouse_manager")
def driver_list():
    # TODO: query the database
    return render_template("delivery/driver_list.html")


@bp.route("/drivers/new", methods=["GET", "POST"])
@roles_required("warehouse_manager")
def driver_new():
    # TODO: load the record(s) from the database and pre-fill the form (see database/schema.sql)
    if request.method == "POST":
        # TODO: validate, save to the database, write the audit log
        flash("Saving is not implemented yet.", "info")
        return redirect(url_for("delivery.driver_list"))
    return render_template("delivery/driver_new.html")


@bp.route("/drivers/<int:driver_id>/edit", methods=["GET", "POST"])
@roles_required("warehouse_manager")
def driver_edit(driver_id):
    # TODO: load the record(s) from the database and pre-fill the form (see database/schema.sql)
    if request.method == "POST":
        # TODO: validate, save to the database, write the audit log
        flash("Saving is not implemented yet.", "info")
        return redirect(url_for("delivery.driver_list"))
    return render_template("delivery/driver_edit.html", driver_id=driver_id)


@bp.route("/vehicles")
@roles_required("warehouse_manager")
def vehicle_list():
    # TODO: query the database
    return render_template("delivery/vehicle_list.html")


@bp.route("/vehicles/new", methods=["GET", "POST"])
@roles_required("warehouse_manager")
def vehicle_new():
    # TODO: load the record(s) from the database and pre-fill the form (see database/schema.sql)
    if request.method == "POST":
        # TODO: validate, save to the database, write the audit log
        flash("Saving is not implemented yet.", "info")
        return redirect(url_for("delivery.vehicle_list"))
    return render_template("delivery/vehicle_new.html")


@bp.route("/vehicles/<int:vehicle_id>/edit", methods=["GET", "POST"])
@roles_required("warehouse_manager")
def vehicle_edit(vehicle_id):
    # TODO: load the record(s) from the database and pre-fill the form (see database/schema.sql)
    if request.method == "POST":
        # TODO: validate, save to the database, write the audit log
        flash("Saving is not implemented yet.", "info")
        return redirect(url_for("delivery.vehicle_list"))
    return render_template("delivery/vehicle_edit.html", vehicle_id=vehicle_id)
