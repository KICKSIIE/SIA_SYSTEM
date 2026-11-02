# Admin: item master data (owner adds and edits, the warehouse manager can view)
from flask import render_template, request, redirect, url_for, flash
from ...roles import roles_required
from ... import inventory_service as inv
from ... import item_ops as ops
from ...inventory_service import InventoryError
from ...session_user import current_user
from . import bp


@bp.route("/items")
@roles_required("owner", "warehouse_manager")
def item_list():
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    res = ops.list_items(request.args.get("q", ""), request.args.get("category", ""), request.args.get("brand", ""),
                         request.args.get("status", "active"), page)
    return render_template("admin/item_list.html", res=res, brands=ops.brands(), categories=ops.CATEGORIES, f=request.args)


def _form_context(**extra):
    return dict(brands=ops.brands(), patterns=ops.patterns(), categories=ops.CATEGORIES, **extra)


@bp.route("/items/new", methods=["GET", "POST"])
@roles_required("owner")
def item_new():
    if request.method == "POST":
        try:
            item_id, code, notes = ops.create_item(request.form, current_user()["id"])
            inv.commit()
        except InventoryError as e:
            inv.rollback()
            flash(str(e), "error")
        else:
            flash("Item %s saved." % code, "success")
            for n in notes:
                flash(n, "info")
            return redirect(url_for("admin.item_list"))
        return render_template("admin/item_new.html", f=request.form, **_form_context())
    return render_template("admin/item_new.html", f={"category": "tire"}, **_form_context())


@bp.route("/items/<int:item_id>/edit", methods=["GET", "POST"])
@roles_required("owner")
def item_edit(item_id):
    item = ops.get_item(item_id)
    if item is None:
        return render_template("404.html"), 404
    if request.method == "POST":
        try:
            changed, notes = ops.update_item(item_id, request.form, current_user()["id"])
            inv.commit()
        except InventoryError as e:
            inv.rollback()
            flash(str(e), "error")
            return render_template("admin/item_edit.html", item=item, f=request.form, on_hand=ops.total_on_hand(item_id),
                                   **_form_context())
        flash("Item saved." if changed else "Nothing changed.", "success")
        for n in notes:
            flash(n, "info")
        return redirect(url_for("admin.item_list"))
    form = dict(item, is_active="1" if item["is_active"] else "")
    return render_template("admin/item_edit.html", item=item, f=form, on_hand=ops.total_on_hand(item_id), **_form_context())


@bp.route("/classification", methods=["GET", "POST"])
@roles_required("owner")
def classification():
    """Brands and patterns: see them, rename one, or merge two (rename to a name that already exists)."""
    if request.method == "POST":
        try:
            msg = ops.rename_value(request.form.get("kind"), request.form.get("old"), request.form.get("new"),
                                   current_user()["id"])
            inv.commit()
        except InventoryError as e:
            inv.rollback()
            flash(str(e), "error")
        else:
            flash(msg, "success")
        return redirect(url_for("admin.classification"))
    return render_template("admin/classification.html", data=ops.classification())
