from itertools import zip_longest

from flask import Blueprint, render_template, request, redirect, url_for, flash
from ..roles import roles_required
from .. import inventory_service as inv
from .. import inventory_ops as ops
from ..inventory_service import InventoryError
from ..session_user import current_user, scope_location

bp = Blueprint("inventory", __name__, url_prefix="/inventory")


def _page():
    try:
        return max(1, int(request.args.get("page", 1)))
    except ValueError:
        return 1


def _own_location(user):
    """The location a shop / warehouse user works in, or None (with a message) if the account has none."""
    if not user["location_id"]:
        flash("Your account has no location. Ask the owner to set it.", "error")
        return None
    return user["location_id"]


def _lines(*names):
    """Table rows from the form, one tuple per row. A missing column becomes ''."""
    return list(zip_longest(*[request.form.getlist(n) for n in names], fillvalue=""))


# ---------------------------------------------------------------------
# Stock
# ---------------------------------------------------------------------

@bp.route("/stock")
@roles_required("owner", "shop_manager", "shop_staff", "warehouse_manager", "warehouse_staff")
def stock_list():
    user = current_user()
    scope = scope_location(user)
    if user["role"] != "owner" and scope is None:
        _own_location(user)
    loc_arg = request.args.get("location", type=int)
    res = ops.stock_rows(scope, request.args.get("q", ""), loc_arg,
                         request.args.get("category", ""), request.args.get("status", ""), _page())
    return render_template("inventory/stock_list.html", res=res, locations=ops.list_locations(scope),
                           f=request.args)


@bp.route("/stock/<int:item_id>")
@roles_required("owner", "shop_manager", "shop_staff", "warehouse_manager", "warehouse_staff")
def stock_detail(item_id):
    card = ops.stock_card(item_id, scope_location(current_user()))
    if card is None:
        return render_template("404.html"), 404
    return render_template("inventory/stock_detail.html", item_id=item_id, card=card)


# ---------------------------------------------------------------------
# Sales / issues
# ---------------------------------------------------------------------

@bp.route("/issues")
@roles_required("shop_staff", "shop_manager", "owner")
def issue_list():
    res = ops.list_issues(scope_location(current_user()), request.args.get("q", ""),
                          request.args.get("period", ""), _page())
    return render_template("inventory/issue_list.html", res=res, f=request.args)


@bp.route("/issues/new", methods=["GET", "POST"])
@roles_required("shop_staff", "shop_manager")
def issue_new():
    user = current_user()
    loc_id = _own_location(user)
    if loc_id is None:
        return redirect(url_for("inventory.issue_list"))
    if request.method == "POST":
        try:
            _id, issue_no, low = ops.create_issue(
                user["id"], loc_id, request.form.get("issue_date"), request.form.get("customer_name"),
                request.form.get("document_ref"), request.form.get("reason"), request.form.get("remarks"),
                _lines("item_id[]", "qty[]"))
            inv.commit()
        except InventoryError as e:
            inv.rollback()
            flash(str(e), "error")
        else:
            flash("Saved %s. Stock was deducted." % issue_no, "success")
            if low:
                # TODO (Module 1): create / refresh the low-stock alert for the shop manager here.
                flash("Now at or below ROP: " + ", ".join(r["item_name"] for r in low), "info")
            return redirect(url_for("inventory.issue_detail", issue_id=_id))
    return render_template("inventory/issue_new.html", items=ops.items_for_select(loc_id),
                           location=ops.get_location(loc_id), f=request.form)


@bp.route("/issues/<int:issue_id>")
@roles_required("shop_staff", "shop_manager", "owner")
def issue_detail(issue_id):
    user = current_user()
    issue = ops.get_issue(issue_id, scope_location(user))
    if issue is None:
        return render_template("404.html"), 404
    can_request, _w1 = ops.can_request_void(user, issue)
    can_confirm, _w2 = ops.can_confirm_void(user, issue)
    return render_template("inventory/issue_detail.html", issue=issue, can_request=can_request, can_confirm=can_confirm)


@bp.route("/issues/<int:issue_id>/void-request", methods=["POST"])
@roles_required("shop_staff", "shop_manager")
def issue_void_request(issue_id):
    try:
        issue_no = ops.request_void(current_user(), issue_id, request.form.get("void_reason"))
        inv.commit()
    except InventoryError as e:
        inv.rollback()
        flash(str(e), "error")
    else:
        flash("Void requested for %s. The stock goes back when your manager confirms it." % issue_no, "success")
    return redirect(url_for("inventory.issue_detail", issue_id=issue_id))


# Staff request, the manager of the same shop (or the owner) confirms. Rules live in ops.can_confirm_void().
@bp.route("/issues/<int:issue_id>/void-review", methods=["POST"])
@roles_required("shop_manager", "owner")
def issue_void_review(issue_id):
    try:
        issue_no, result = ops.review_void(current_user(), issue_id, request.form.get("decision"), request.form.get("remarks"))
        inv.commit()
    except InventoryError as e:
        inv.rollback()
        flash(str(e), "error")
    else:
        flash("%s was voided and the stock was put back." % issue_no if result == "voided"
              else "Void request for %s was rejected. The sale stays." % issue_no, "success")
    return redirect(url_for("inventory.issue_detail", issue_id=issue_id))


# ---------------------------------------------------------------------
# ROP settings (owner)
# ---------------------------------------------------------------------

@bp.route("/rop")
@roles_required("owner")
def rop_list():
    res = ops.rop_rows(request.args.get("q", ""), request.args.get("location", type=int),
                       request.args.get("show") == "missing", _page())
    return render_template("inventory/rop_list.html", res=res, locations=ops.list_locations(), f=request.args)


@bp.route("/rop/<int:item_id>/edit", methods=["GET", "POST"])
@roles_required("owner")
def rop_edit(item_id):
    data = ops.rop_for_item(item_id)
    if data is None:
        return render_template("404.html"), 404
    if request.method == "POST":
        entries = [{"location_id": int(l), "rop": r, "max_level": m, "lead_time": t, "rack": k}
                   for l, r, m, t, k in _lines("location_id[]", "rop[]", "max_level[]", "lead_time_days[]", "rack[]")]
        try:
            changed = ops.save_rop(item_id, entries, current_user()["id"])
            inv.commit()
        except InventoryError as e:
            inv.rollback()
            flash(str(e), "error")
            # show what the owner typed, not the old values
            for row, (_l, r, m, t, k) in zip(data["rows"], _lines("location_id[]", "rop[]", "max_level[]", "lead_time_days[]", "rack[]")):
                row["rop"], row["max_level"], row["lead_time_days"], row["rack"] = r, m, t, k
        else:
            flash("ROP settings saved for: %s." % ", ".join(changed) if changed else "Nothing changed.", "success")
            return redirect(url_for("inventory.rop_list"))
    return render_template("inventory/rop_edit.html", item_id=item_id, data=data)


@bp.route("/rf-queue")
@roles_required("warehouse_manager")
def rfqueue_list():
    user = current_user()
    loc = _own_location(user)
    res = ops.list_rf_queue(loc or 0, request.args.get("q", ""), request.args.get("status", ""), _page())
    return render_template("inventory/rfqueue_list.html", res=res, f=request.args)


@bp.route("/rf-queue/<int:rf_id>", methods=["GET", "POST"])
@roles_required("warehouse_manager")
def rfqueue_review(rf_id):
    user = current_user()
    rf = ops.get_rf(rf_id, user["location_id"] or 0)
    if rf is None:
        return render_template("404.html"), 404
    if request.method == "POST":
        try:
            units, short = ops.reserve_rf(user, rf_id, _lines("rf_item_id[]", "qty_reserve[]"))
            inv.commit()
        except InventoryError as e:
            inv.rollback()
            flash(str(e), "error")
        else:
            msg = "Reserved %d unit(s) for %s." % (units, rf["rf_no"])
            if short:
                msg += " %d item(s) are still short and were added to the restock alert." % short
            flash(msg, "success")
            # Creating the transfer slip (TS) belongs to the Delivery module.
            return redirect(url_for("inventory.rfqueue_list"))
        rf = ops.get_rf(rf_id, user["location_id"])
    return render_template("inventory/rfqueue_review.html", rf=rf, f=request.form)


# ---------------------------------------------------------------------
# Stock adjustments
# ---------------------------------------------------------------------

@bp.route("/adjustments")
@roles_required("warehouse_manager", "warehouse_staff", "shop_manager", "shop_staff", "owner")
def adjustment_list():
    res = ops.list_adjustments(scope_location(current_user()), request.args.get("status", ""),
                               request.args.get("q", ""), _page())
    return render_template("inventory/adjustment_list.html", res=res, f=request.args)


@bp.route("/adjustments/new", methods=["GET", "POST"])
@roles_required("warehouse_staff", "warehouse_manager", "shop_staff", "shop_manager")
def adjustment_new():
    user = current_user()
    loc_id = _own_location(user)
    if loc_id is None:
        return redirect(url_for("inventory.adjustment_list"))
    if request.method == "POST":
        try:
            adj_id, adj_no = ops.create_adjustment(
                user["id"], loc_id, request.form.get("reason"), request.form.get("ar_no"),
                request.form.get("remarks"), _lines("item_id[]", "qty_actual[]", "item_remarks[]"))
            inv.commit()
        except InventoryError as e:
            inv.rollback()
            flash(str(e), "error")
        else:
            flash("Saved %s. It waits for your manager's approval before the stock changes." % adj_no, "success")
            return redirect(url_for("inventory.adjustment_detail", adj_id=adj_id))
    return render_template("inventory/adjustment_new.html", items=ops.items_for_select(loc_id),
                           location=ops.get_location(loc_id), f=request.form)


@bp.route("/adjustments/<int:adj_id>")
@roles_required("warehouse_manager", "warehouse_staff", "shop_manager", "shop_staff", "owner")
def adjustment_detail(adj_id):
    user = current_user()
    adj = ops.get_adjustment(adj_id, scope_location(user))
    if adj is None:
        return render_template("404.html"), 404
    can, _why = ops.can_review(user, adj)
    return render_template("inventory/adjustment_detail.html", adj=adj, can_review=can)


# Each manager approves the adjustments of their OWN location only:
#   warehouse_manager -> warehouse, shop_manager -> own shop. The owner is notified and can view them.
# Only if a manager raised the request (no one else at that location can approve), the owner reviews it.
# The rules live in ops.can_review().
@bp.route("/adjustments/<int:adj_id>/review", methods=["GET", "POST"])
@roles_required("warehouse_manager", "shop_manager", "owner")
def adjustment_review(adj_id):
    user = current_user()
    adj = ops.get_adjustment(adj_id, None)
    if adj is None:
        return render_template("404.html"), 404
    ok, why = ops.can_review(user, adj)
    if not ok:
        flash(why, "error")
        return redirect(url_for("inventory.adjustment_detail", adj_id=adj_id))
    if request.method == "POST":
        try:
            adj_no, status = ops.review_adjustment(user, adj_id, request.form.get("decision"),
                                                   request.form.get("review_remarks"))
            inv.commit()
        except InventoryError as e:
            inv.rollback()
            flash(str(e), "error")
        else:
            flash("%s %s." % (adj_no, status), "success")
            return redirect(url_for("inventory.adjustment_detail", adj_id=adj_id))
    return render_template("inventory/adjustment_review.html", adj=adj, f=request.form)
