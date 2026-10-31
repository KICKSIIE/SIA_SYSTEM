from flask import Blueprint, render_template, request, redirect, url_for, flash
from ..roles import roles_required

bp = Blueprint("inventory", __name__, url_prefix="/inventory")


@bp.route("/stock")
@roles_required("owner", "shop_manager", "shop_staff", "inventory_manager", "warehouse_manager", "warehouse_staff")
def stock_list():
    # TODO: query the database
    return render_template("inventory/stock_list.html")


@bp.route("/stock/<int:item_id>")
@roles_required("owner", "shop_manager", "shop_staff", "inventory_manager", "warehouse_manager", "warehouse_staff")
def stock_detail(item_id):
    # TODO: query the database
    return render_template("inventory/stock_detail.html", item_id=item_id)


@bp.route("/issues")
@roles_required("shop_staff", "shop_manager", "owner")
def issue_list():
    # TODO: query the database
    return render_template("inventory/issue_list.html")


@bp.route("/issues/new", methods=["GET", "POST"])
@roles_required("shop_staff", "shop_manager")
def issue_new():
    # TODO: load the record(s) from the database and pre-fill the form (see database/schema.sql)
    if request.method == "POST":
        # TODO: validate, save to the database, write the audit log
        flash("Saving is not implemented yet.", "info")
        return redirect(url_for("inventory.issue_list"))
    return render_template("inventory/issue_new.html")


@bp.route("/issues/<int:issue_id>")
@roles_required("shop_staff", "shop_manager", "owner")
def issue_detail(issue_id):
    # TODO: query the database
    return render_template("inventory/issue_detail.html", issue_id=issue_id)


@bp.route("/rop")
@roles_required("inventory_manager", "owner")
def rop_list():
    # TODO: query the database
    return render_template("inventory/rop_list.html")


@bp.route("/rop/<int:item_id>/edit", methods=["GET", "POST"])
@roles_required("inventory_manager")
def rop_edit(item_id):
    # TODO: load the record(s) from the database and pre-fill the form (see database/schema.sql)
    if request.method == "POST":
        # TODO: validate, save to the database, write the audit log
        flash("Saving is not implemented yet.", "info")
        return redirect(url_for("inventory.rop_list"))
    return render_template("inventory/rop_edit.html", item_id=item_id)


@bp.route("/rf-queue")
@roles_required("warehouse_manager")
def rfqueue_list():
    # TODO: query the database
    return render_template("inventory/rfqueue_list.html")


@bp.route("/rf-queue/<int:rf_id>", methods=["GET", "POST"])
@roles_required("warehouse_manager")
def rfqueue_review(rf_id):
    # TODO: load the record(s) from the database and pre-fill the form (see database/schema.sql)
    if request.method == "POST":
        # TODO: validate, save to the database, write the audit log
        flash("Saving is not implemented yet.", "info")
        return redirect(url_for("inventory.rfqueue_list"))
    return render_template("inventory/rfqueue_review.html", rf_id=rf_id)


@bp.route("/adjustments")
@roles_required("inventory_manager", "warehouse_manager", "warehouse_staff", "owner")
def adjustment_list():
    # TODO: query the database
    return render_template("inventory/adjustment_list.html")


@bp.route("/adjustments/new", methods=["GET", "POST"])
@roles_required("warehouse_staff", "warehouse_manager")
def adjustment_new():
    # TODO: load the record(s) from the database and pre-fill the form (see database/schema.sql)
    if request.method == "POST":
        # TODO: validate, save to the database, write the audit log
        flash("Saving is not implemented yet.", "info")
        return redirect(url_for("inventory.adjustment_list"))
    return render_template("inventory/adjustment_new.html")


@bp.route("/adjustments/<int:adj_id>")
@roles_required("inventory_manager", "warehouse_manager", "warehouse_staff", "owner")
def adjustment_detail(adj_id):
    # TODO: query the database
    return render_template("inventory/adjustment_detail.html", adj_id=adj_id)


@bp.route("/adjustments/<int:adj_id>/review", methods=["GET", "POST"])
@roles_required("inventory_manager")
def adjustment_review(adj_id):
    # TODO: load the record(s) from the database and pre-fill the form (see database/schema.sql)
    if request.method == "POST":
        # TODO: validate, save to the database, write the audit log
        flash("Saving is not implemented yet.", "info")
        return redirect(url_for("inventory.adjustment_detail", adj_id=adj_id))
    return render_template("inventory/adjustment_review.html", adj_id=adj_id)
