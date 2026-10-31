# Admin: item master data
from flask import render_template, request, redirect, url_for, flash
from ...roles import roles_required
from . import bp


@bp.route("/items")
@roles_required("owner", "warehouse_manager")
def item_list():
    # TODO: query the database
    return render_template("admin/item_list.html")


@bp.route("/items/new", methods=["GET", "POST"])
@roles_required("owner")
def item_new():
    # TODO: load the record(s) from the database and pre-fill the form (see database/schema.sql)
    if request.method == "POST":
        # TODO: validate, save to the database, write the audit log
        flash("Saving is not implemented yet.", "info")
        return redirect(url_for("admin.item_list"))
    return render_template("admin/item_new.html")


@bp.route("/items/<int:item_id>/edit", methods=["GET", "POST"])
@roles_required("owner")
def item_edit(item_id):
    # TODO: load the record(s) from the database and pre-fill the form (see database/schema.sql)
    if request.method == "POST":
        # TODO: validate, save to the database, write the audit log
        flash("Saving is not implemented yet.", "info")
        return redirect(url_for("admin.item_list"))
    return render_template("admin/item_edit.html", item_id=item_id)
