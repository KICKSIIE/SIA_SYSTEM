# Delivery: the shop receives the delivery (incoming deliveries, AR)
from flask import render_template, request, redirect, url_for, flash
from ...roles import roles_required
from . import bp


@bp.route("/deliveries")
@roles_required("shop_manager")
def delivery_list():
    # TODO: query the database
    return render_template("delivery/delivery_list.html")


@bp.route("/deliveries/<int:ts_id>/receive", methods=["GET", "POST"])
@roles_required("shop_manager")
def delivery_receive(ts_id):
    # TODO: load the record(s) from the database and pre-fill the form (see database/schema.sql)
    if request.method == "POST":
        # TODO: validate, save to the database, write the audit log
        flash("Saving is not implemented yet.", "info")
        return redirect(url_for("delivery.delivery_list"))
    return render_template("delivery/delivery_receive.html", ts_id=ts_id)
