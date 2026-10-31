# Admin: users and locations
from flask import render_template, request, redirect, url_for, flash
from ...roles import roles_required
from . import bp


@bp.route("/users")
@roles_required("owner")
def user_list():
    # TODO: query the database
    return render_template("admin/user_list.html")


@bp.route("/users/new", methods=["GET", "POST"])
@roles_required("owner")
def user_new():
    # TODO: load the record(s) from the database and pre-fill the form (see database/schema.sql)
    if request.method == "POST":
        # TODO: validate, save to the database, write the audit log
        flash("Saving is not implemented yet.", "info")
        return redirect(url_for("admin.user_list"))
    return render_template("admin/user_new.html")


@bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@roles_required("owner")
def user_edit(user_id):
    # TODO: load the record(s) from the database and pre-fill the form (see database/schema.sql)
    if request.method == "POST":
        # TODO: validate, save to the database, write the audit log
        flash("Saving is not implemented yet.", "info")
        return redirect(url_for("admin.user_list"))
    return render_template("admin/user_edit.html", user_id=user_id)


@bp.route("/locations")
@roles_required("owner")
def location_list():
    # TODO: query the database
    return render_template("admin/location_list.html")


@bp.route("/locations/new", methods=["GET", "POST"])
@roles_required("owner")
def location_new():
    # TODO: load the record(s) from the database and pre-fill the form (see database/schema.sql)
    if request.method == "POST":
        # TODO: validate, save to the database, write the audit log
        flash("Saving is not implemented yet.", "info")
        return redirect(url_for("admin.location_list"))
    return render_template("admin/location_new.html")


@bp.route("/locations/<int:location_id>/edit", methods=["GET", "POST"])
@roles_required("owner")
def location_edit(location_id):
    # TODO: load the record(s) from the database and pre-fill the form (see database/schema.sql)
    if request.method == "POST":
        # TODO: validate, save to the database, write the audit log
        flash("Saving is not implemented yet.", "info")
        return redirect(url_for("admin.location_list"))
    return render_template("admin/location_edit.html", location_id=location_id)
