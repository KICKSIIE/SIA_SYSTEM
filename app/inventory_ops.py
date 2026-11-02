"""Inventory module: the queries and save workflows behind the screens.

Routes in blueprints/inventory.py stay thin: they read the form, call one function
here, then commit or roll back. All stock changes go through inventory_service.

`scope` arguments: None means every location (owner), otherwise one location id.
"""
import datetime as dt

from . import inventory_service as inv
from .inventory_service import InventoryError

PAGE_SIZE = 50
ADJ_REASONS = {"count difference": "count_difference", "damaged": "damaged", "lost": "lost",
               "delivery variance": "delivery_variance", "other": "other"}
MANAGER_ROLES = ("shop_manager", "warehouse_manager")


def _b():
    return inv.backend()


def _like(q):
    return "%" + q.strip().lower() + "%"


def _paged(sql_count, sql_rows, page, **params):
    total = _b().one(sql_count, **params)["n"]
    pages = max(1, -(-total // PAGE_SIZE))
    page = min(max(1, page), pages)
    rows = _b().all(sql_rows + " LIMIT %d OFFSET %d" % (PAGE_SIZE, (page - 1) * PAGE_SIZE), **params)
    return {"rows": rows, "total": total, "page": page, "pages": pages}


# ---------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------

def list_locations(scope=None):
    if scope is None:
        return _b().all("SELECT id, code, name, loc_type FROM locations WHERE is_active ORDER BY code")
    return _b().all("SELECT id, code, name, loc_type FROM locations WHERE id = :l", l=scope)


def get_location(location_id):
    return _b().one("SELECT id, code, name, loc_type FROM locations WHERE id = :l", l=location_id)


def items_for_select(location_id):
    """All active items with the stock at one location (for the item drop-downs)."""
    return _b().all(
        "SELECT i.id, i.item_code, i.item_name, COALESCE(b.on_hand, 0) AS on_hand, "
        "COALESCE(b.reserved, 0) AS reserved FROM items i "
        "LEFT JOIN stock_balances b ON b.item_id = i.id AND b.location_id = :l "
        "WHERE i.is_active ORDER BY i.item_name", l=location_id)


def get_item(item_id):
    return _b().one("SELECT * FROM items WHERE id = :i", i=item_id)


# ---------------------------------------------------------------------
# Stock list and stock card
# ---------------------------------------------------------------------

_STOCK_FROM = (
    "FROM items i CROSS JOIN locations l "
    "LEFT JOIN stock_balances b ON b.item_id = i.id AND b.location_id = l.id "
    "LEFT JOIN item_location_settings s ON s.item_id = i.id AND s.location_id = l.id "
    "WHERE i.is_active AND l.is_active AND (b.item_id IS NOT NULL OR s.item_id IS NOT NULL)")


def stock_rows(scope, q="", location_id=None, category="", status="", page=1):
    where, p = "", {}
    loc = scope if scope is not None else location_id
    if loc:
        where += " AND l.id = :loc"
        p["loc"] = loc
    if q.strip():
        where += " AND (LOWER(i.item_name) LIKE :q OR LOWER(i.item_code) LIKE :q)"
        p["q"] = _like(q)
    if category:
        where += " AND i.category = :cat"
        p["cat"] = category
    avail = "(COALESCE(b.on_hand, 0) - COALESCE(b.reserved, 0))"
    if status == "out":
        where += " AND COALESCE(b.on_hand, 0) = 0"
    elif status == "below":
        where += " AND COALESCE(s.rop, 0) > 0 AND COALESCE(b.on_hand, 0) > 0 AND %s <= s.rop" % avail
    elif status == "ok":
        where += " AND COALESCE(b.on_hand, 0) > 0 AND NOT (COALESCE(s.rop, 0) > 0 AND %s <= s.rop)" % avail
    cols = ("SELECT i.id AS item_id, i.item_code, i.item_name, i.category, s.rack AS rack, "
            "l.id AS location_id, l.code AS location, "
            "COALESCE(b.on_hand, 0) AS on_hand, COALESCE(b.reserved, 0) AS reserved, "
            "COALESCE(b.on_hand, 0) - COALESCE(b.reserved, 0) AS available, COALESCE(s.rop, 0) AS rop ")
    res = _paged("SELECT COUNT(*) AS n " + _STOCK_FROM + where,
                 cols + _STOCK_FROM + where + " ORDER BY i.item_name, l.code", page, **p)
    for r in res["rows"]:
        r["status"] = stock_status(r["on_hand"], r["available"], r["rop"])
    return res


def stock_status(on_hand, available, rop):
    if on_hand == 0:
        return "Out of stock"
    if rop > 0 and available <= rop:
        return "Below ROP"
    return "OK"


def stock_card(item_id, scope):
    item = get_item(item_id)
    if item is None:
        return None
    p = {"i": item_id}
    loc_sql = ""
    if scope is not None:
        loc_sql, p["loc"] = " AND l.id = :loc", scope
    balances = _b().all(
        "SELECT l.id AS location_id, l.code AS location, COALESCE(b.on_hand, 0) AS on_hand, "
        "COALESCE(b.reserved, 0) AS reserved, COALESCE(s.rop, 0) AS rop, COALESCE(s.max_level, 0) AS max_level, "
        "s.rack AS rack FROM locations l LEFT JOIN stock_balances b ON b.item_id = :i AND b.location_id = l.id "
        "LEFT JOIN item_location_settings s ON s.item_id = :i AND s.location_id = l.id "
        "WHERE l.is_active" + loc_sql + " ORDER BY l.code", **p)
    ledger = _b().all(
        "SELECT sl.created_at, l.code AS location, sl.movement_type, sl.qty_change, sl.balance_after, "
        "sl.ref_no, sl.remarks FROM stock_ledger sl JOIN locations l ON l.id = sl.location_id "
        "WHERE sl.item_id = :i" + loc_sql.replace("l.id", "sl.location_id") +
        " ORDER BY sl.created_at DESC, sl.id DESC LIMIT 100", **p)
    return {"item": item, "balances": balances, "ledger": ledger}


# ---------------------------------------------------------------------
# ROP settings (owner)
# ---------------------------------------------------------------------

def rop_rows(q="", location_id=None, only_missing=False, page=1):
    where, p = "", {}
    if location_id:
        where += " AND l.id = :loc"
        p["loc"] = location_id
    if q.strip():
        where += " AND (LOWER(i.item_name) LIKE :q OR LOWER(i.item_code) LIKE :q)"
        p["q"] = _like(q)
    if only_missing:
        where += " AND COALESCE(s.rop, 0) = 0"
    frm = ("FROM items i CROSS JOIN locations l "
           "LEFT JOIN stock_balances b ON b.item_id = i.id AND b.location_id = l.id "
           "LEFT JOIN item_location_settings s ON s.item_id = i.id AND s.location_id = l.id "
           "WHERE i.is_active AND l.is_active")
    cols = ("SELECT i.id AS item_id, i.item_name, l.code AS location, COALESCE(b.on_hand, 0) AS on_hand, "
            "COALESCE(s.rop, 0) AS rop, COALESCE(s.max_level, 0) AS max_level, "
            "COALESCE(s.lead_time_days, 0) AS lead_time_days, s.rack AS rack, s.updated_at AS updated_at ")
    return _paged("SELECT COUNT(*) AS n " + frm + where, cols + frm + where + " ORDER BY i.item_name, l.code", page, **p)


def rop_for_item(item_id):
    item = get_item(item_id)
    if item is None:
        return None
    rows = _b().all(
        "SELECT l.id AS location_id, l.code AS location, l.loc_type, COALESCE(b.on_hand, 0) AS on_hand, "
        "COALESCE(s.rop, 0) AS rop, COALESCE(s.max_level, 0) AS max_level, "
        "COALESCE(s.lead_time_days, 0) AS lead_time_days, s.rack AS rack "
        "FROM locations l LEFT JOIN stock_balances b ON b.item_id = :i AND b.location_id = l.id "
        "LEFT JOIN item_location_settings s ON s.item_id = :i AND s.location_id = l.id "
        "WHERE l.is_active ORDER BY l.code", i=item_id)
    return {"item": item, "rows": rows}


def _whole(v, label, minimum=0):
    try:
        n = int(str(v).strip())
    except (TypeError, ValueError):
        raise InventoryError("%s must be a whole number." % label)
    if n < minimum:
        raise InventoryError("%s cannot be below %d." % (label, minimum))
    return n


def save_rop(item_id, entries, user_id):
    """entries: list of dicts location_id, rop, max_level, lead_time (strings from the form)."""
    if get_item(item_id) is None:
        raise InventoryError("Item not found.")
    changed = []
    for e in entries:
        code = (get_location(e["location_id"]) or {}).get("code", "?")
        rop = _whole(e["rop"], "%s: ROP" % code)
        mx = _whole(e["max_level"], "%s: Max level" % code)
        lead = _whole(e["lead_time"], "%s: Lead time" % code)
        if mx < rop:
            raise InventoryError("%s: Max level must be equal to or higher than ROP." % code)
        rack = (e.get("rack") or "").strip()
        if len(rack) > 30:
            raise InventoryError("%s: Rack can be at most 30 characters." % code)
        old = _b().one("SELECT rop, max_level, lead_time_days, rack FROM item_location_settings "
                       "WHERE item_id = :i AND location_id = :l", i=item_id, l=e["location_id"])
        new = {"rop": rop, "max_level": mx, "lead_time_days": lead, "rack": rack or None}
        if old == new:
            continue
        _b().execute(
            "INSERT INTO item_location_settings (item_id, location_id, rop, max_level, lead_time_days, rack, updated_by) "
            "VALUES (:i, :l, :r, :m, :t, :k, :u) ON CONFLICT (item_id, location_id) DO UPDATE SET "
            "rop = :r, max_level = :m, lead_time_days = :t, rack = :k, updated_by = :u, updated_at = CURRENT_TIMESTAMP",
            i=item_id, l=e["location_id"], r=rop, m=mx, t=lead, k=rack or None, u=user_id)
        inv.write_audit(user_id, "update" if old else "create", "item_location_settings", item_id,
                        old=dict(old, location=code) if old else None, new=dict(new, location=code))
        changed.append(code)
    return changed


# ---------------------------------------------------------------------
# Sales / issues
# ---------------------------------------------------------------------

def _parse_date(v, label="Date"):
    try:
        d = dt.date.fromisoformat((v or "").strip())
    except ValueError:
        raise InventoryError("%s is required." % label)
    if d > dt.date.today():
        raise InventoryError("%s cannot be in the future." % label)
    return d


def _merge_lines(pairs, what):
    """pairs: (item_id_str, qty_str). Drops empty rows, merges repeated items."""
    merged = {}
    for item_id, qty in pairs:
        if not str(item_id).strip() and not str(qty).strip():
            continue
        if not str(item_id).strip():
            raise InventoryError("Select an item for every line.")
        i = _whole(item_id, "Item")
        merged[i] = merged.get(i, 0) + _whole(qty, what, 1)
    if not merged:
        raise InventoryError("Add at least one item.")
    return merged


def _item_name(item_id):
    return (get_item(item_id) or {}).get("item_name", "Item %s" % item_id)


def create_issue(user_id, location_id, issue_date, customer, document_ref, reason, remarks, pairs):
    """Save a sale / stock issue and deduct the stock. Returns (issue_id, issue_no, items_now_low)."""
    loc = get_location(location_id)
    if loc is None:
        raise InventoryError("Your account has no location. Ask the owner to set it.")
    d = _parse_date(issue_date)
    reason = (reason or "").strip().lower()
    if reason not in ("sale", "other"):
        raise InventoryError("Select a reason.")
    lines = _merge_lines(pairs, "Quantity")
    issue_no = inv.next_doc_no("ISS", d.year)
    row = _b().one(
        "INSERT INTO stock_issues (issue_no, location_id, customer_name, issue_date, document_ref, reason, remarks, recorded_by) "
        "VALUES (:n, :l, :c, :d, :ref, :r, :rem, :u) RETURNING id",
        n=issue_no, l=location_id, c=(customer or "").strip()[:120] or None, d=d.isoformat(),
        ref=(document_ref or "").strip()[:40] or None, r=reason, rem=(remarks or "").strip()[:200] or None, u=user_id)
    issue_id = row["id"]
    for item_id, qty in lines.items():
        _b().execute("INSERT INTO stock_issue_items (issue_id, item_id, qty) VALUES (:i, :it, :q)",
                     i=issue_id, it=item_id, q=qty)
        try:
            inv.change_stock(item_id, location_id, -qty, "issue", ref_type="ISS", ref_id=issue_id,
                             ref_no=issue_no, remarks=(customer or "").strip()[:200] or None, user_id=user_id)
        except InventoryError as e:
            raise InventoryError("%s: %s" % (_item_name(item_id), e))
    inv.write_audit(user_id, "create", "stock_issues", issue_id,
                    new={"issue_no": issue_no, "location": loc["code"], "items": lines})
    refresh_alerts(location_id, lines.keys())
    low = [r for r in inv.items_below_rop(location_id) if r["item_id"] in lines]
    for r in low:
        r["item_name"] = _item_name(r["item_id"])
    return issue_id, issue_no, low


def list_issues(scope, q="", period="", page=1):
    where, p = "", {}
    if scope is not None:
        where, p["loc"] = " AND si.location_id = :loc", scope
    if q.strip():
        where += " AND (LOWER(si.issue_no) LIKE :q OR LOWER(COALESCE(si.customer_name, '')) LIKE :q " \
                 "OR LOWER(COALESCE(si.document_ref, '')) LIKE :q)"
        p["q"] = _like(q)
    today = dt.date.today()
    since = {"today": today, "week": today - dt.timedelta(days=today.weekday()),
             "month": today.replace(day=1)}.get(period)
    if since:
        where += " AND si.issue_date >= :since"
        p["since"] = since.isoformat()
    frm = ("FROM stock_issues si JOIN locations l ON l.id = si.location_id JOIN users u ON u.id = si.recorded_by "
           "WHERE 1 = 1")
    cols = ("SELECT si.id, si.issue_no, si.issue_date, l.code AS location, si.customer_name, si.document_ref, "
            "si.status, u.full_name AS recorded_by, (SELECT COUNT(*) FROM stock_issue_items x WHERE x.issue_id = si.id) AS n_items ")
    return _paged("SELECT COUNT(*) AS n " + frm + where,
                  cols + frm + where + " ORDER BY si.issue_date DESC, si.id DESC", page, **p)


def get_issue(issue_id, scope):
    head = _b().one(
        "SELECT si.*, l.code AS location, u.full_name AS recorded_by_name, vr.full_name AS void_requested_by_name, "
        "vb.full_name AS voided_by_name FROM stock_issues si "
        "JOIN locations l ON l.id = si.location_id JOIN users u ON u.id = si.recorded_by "
        "LEFT JOIN users vr ON vr.id = si.void_requested_by LEFT JOIN users vb ON vb.id = si.voided_by WHERE si.id = :i", i=issue_id)
    if head is None or (scope is not None and head["location_id"] != scope):
        return None
    head["lines"] = _b().all(
        "SELECT i.item_name, x.qty FROM stock_issue_items x JOIN items i ON i.id = x.item_id "
        "WHERE x.issue_id = :i ORDER BY x.id", i=issue_id)
    return head


# ---------------------------------------------------------------------
# Stock adjustments
# ---------------------------------------------------------------------

def create_adjustment(user_id, location_id, reason, ar_no, remarks, triples):
    """Record a pending adjustment. triples: (item_id, qty_actual, item_remarks). No stock changes yet."""
    loc = get_location(location_id)
    if loc is None:
        raise InventoryError("Your account has no location. Ask the owner to set it.")
    reason_code = ADJ_REASONS.get((reason or "").strip().lower())
    if reason_code is None:
        raise InventoryError("Select a reason.")
    source_ar = None
    if (ar_no or "").strip():
        ar = _b().one("SELECT id FROM acknowledgment_receipts WHERE ar_no = :a", a=ar_no.strip())
        if ar is None:
            raise InventoryError("AR %s was not found." % ar_no.strip())
        source_ar = ar["id"]

    lines = {}
    for item_id, actual, note in triples:
        if not str(item_id).strip() and not str(actual).strip():
            continue
        if not str(item_id).strip():
            raise InventoryError("Select an item for every line.")
        i = _whole(item_id, "Item")
        if i in lines:
            raise InventoryError("%s is listed twice." % _item_name(i))
        lines[i] = (_whole(actual, "Actual qty"), (note or "").strip()[:200] or None)
    if not lines:
        raise InventoryError("Add at least one item.")

    rows = []
    for i, (actual, note) in lines.items():
        bal = inv.get_balance(i, location_id)
        if actual == bal["on_hand"]:
            raise InventoryError("%s: actual quantity equals the system quantity, so there is nothing to adjust." % _item_name(i))
        if actual < bal["reserved"]:
            raise InventoryError("%s: %d is reserved for requisitions, so the actual quantity cannot be below that."
                                 % (_item_name(i), bal["reserved"]))
        rows.append((i, bal["on_hand"], actual, note))

    adj_no = inv.next_doc_no("ADJ")
    head = _b().one(
        "INSERT INTO stock_adjustments (adj_no, location_id, reason, status, source_ar_id, remarks, requested_by) "
        "VALUES (:n, :l, :r, 'pending', :ar, :rem, :u) RETURNING id",
        n=adj_no, l=location_id, r=reason_code, ar=source_ar, rem=(remarks or "").strip() or None, u=user_id)
    for i, system, actual, note in rows:
        _b().execute("INSERT INTO stock_adjustment_items (adjustment_id, item_id, qty_system, qty_actual, item_remarks) "
                     "VALUES (:a, :i, :s, :q, :n)", a=head["id"], i=i, s=system, q=actual, n=note)
    inv.write_audit(user_id, "create", "stock_adjustments", head["id"],
                    new={"adj_no": adj_no, "location": loc["code"], "reason": reason_code,
                         "items": {i: [s, a] for i, s, a, _ in rows}})
    return head["id"], adj_no


def list_adjustments(scope, status="", q="", page=1):
    where, p = "", {}
    if scope is not None:
        where, p["loc"] = " AND a.location_id = :loc", scope
    if status in ("pending", "approved", "rejected"):
        where += " AND a.status = :st"
        p["st"] = status
    if q.strip():
        where += " AND LOWER(a.adj_no) LIKE :q"
        p["q"] = _like(q)
    frm = "FROM stock_adjustments a JOIN locations l ON l.id = a.location_id WHERE 1 = 1"
    cols = ("SELECT a.id, a.adj_no, a.created_at, l.code AS location, a.reason, a.status, "
            "(SELECT COUNT(*) FROM stock_adjustment_items x WHERE x.adjustment_id = a.id) AS n_items ")
    return _paged("SELECT COUNT(*) AS n " + frm + where, cols + frm + where + " ORDER BY a.id DESC", page, **p)


def get_adjustment(adj_id, scope):
    head = _b().one(
        "SELECT a.*, l.code AS location, l.loc_type, ru.full_name AS requested_by_name, rr.code AS requester_role, "
        "vu.full_name AS reviewed_by_name FROM stock_adjustments a JOIN locations l ON l.id = a.location_id "
        "JOIN users ru ON ru.id = a.requested_by JOIN roles rr ON rr.id = ru.role_id "
        "LEFT JOIN users vu ON vu.id = a.reviewed_by WHERE a.id = :i", i=adj_id)
    if head is None or (scope is not None and head["location_id"] != scope):
        return None
    head["lines"] = _b().all(
        "SELECT i.item_name, x.item_id, x.qty_system, x.qty_actual, x.qty_actual - x.qty_system AS qty_diff, x.item_remarks "
        "FROM stock_adjustment_items x JOIN items i ON i.id = x.item_id WHERE x.adjustment_id = :i ORDER BY x.id", i=adj_id)
    return head


def can_review(user, adj):
    """(allowed, reason). Rules: pending only; a manager reviews their OWN location;
    nobody reviews their own request; the owner reviews only requests raised by a manager."""
    if adj["status"] != "pending":
        return False, "This adjustment was already %s." % adj["status"]
    if adj["requested_by"] == user["id"]:
        return False, "You cannot approve your own adjustment."
    role = user["role"]
    if role in MANAGER_ROLES:
        if adj["location_id"] != user["location_id"]:
            return False, "You can only approve adjustments for your own location."
        return True, ""
    if role == "owner":
        if adj["requester_role"] in MANAGER_ROLES:
            return True, ""
        return False, "The manager of that location approves this one. You are only notified."
    return False, "Your role cannot approve adjustments."


def review_adjustment(user, adj_id, decision, remarks):
    adj = get_adjustment(adj_id, None)
    if adj is None:
        raise InventoryError("Adjustment not found.")
    ok, why = can_review(user, adj)
    if not ok:
        raise InventoryError(why)
    decision = (decision or "").strip().lower()
    if decision not in ("approve", "reject"):
        raise InventoryError("Select approve or reject.")
    if not (remarks or "").strip():
        raise InventoryError("Remarks are required.")
    if decision == "approve":
        for ln in adj["lines"]:
            try:
                inv.change_stock(ln["item_id"], adj["location_id"], ln["qty_diff"], "adjustment",
                                 ref_type="ADJ", ref_id=adj_id, ref_no=adj["adj_no"],
                                 remarks=(adj["reason"] or "")[:200], user_id=user["id"])
            except InventoryError as e:
                raise InventoryError("%s: %s" % (ln["item_name"], e))
    if decision == "approve":
        refresh_alerts(adj["location_id"], [ln["item_id"] for ln in adj["lines"]])
    status = "approved" if decision == "approve" else "rejected"
    _b().execute(
        "UPDATE stock_adjustments SET status = :s, reviewed_by = :u, review_remarks = :r, reviewed_at = CURRENT_TIMESTAMP "
        "WHERE id = :i", s=status, u=user["id"], r=remarks.strip(), i=adj_id)
    inv.write_audit(user["id"], decision, "stock_adjustments", adj_id,
                    old={"status": "pending"}, new={"status": status, "remarks": remarks.strip()})
    return adj["adj_no"], status


# ---------------------------------------------------------------------
# Dashboard numbers (Inventory tiles only)
# ---------------------------------------------------------------------

def dashboard_stats(scope):
    p, loc = {}, ""
    if scope is not None:
        loc, p["loc"] = " AND location_id = :loc", scope
    pending = _b().one("SELECT COUNT(*) AS n FROM stock_adjustments WHERE status = 'pending'" + loc, **p)["n"]
    recent = _b().one("SELECT COUNT(*) AS n FROM stock_adjustments WHERE status <> 'pending'" + loc +
                      " AND reviewed_at >= :d", d=(dt.date.today() - dt.timedelta(days=7)).isoformat(), **p)["n"]
    today = _b().one("SELECT COUNT(*) AS n FROM stock_issues WHERE issue_date = :d" + loc,
                     d=dt.date.today().isoformat(), **p)["n"]
    pending_voids = _b().one("SELECT COUNT(*) AS n FROM stock_issues WHERE status = 'void_requested'" + loc, **p)["n"]
    low = inv.items_below_rop(scope)
    no_rop = _b().one(
        "SELECT COUNT(*) AS n FROM items i CROSS JOIN locations l LEFT JOIN item_location_settings s "
        "ON s.item_id = i.id AND s.location_id = l.id WHERE i.is_active AND l.is_active AND COALESCE(s.rop, 0) = 0"
        + (" AND l.id = :loc" if scope is not None else ""), **p)["n"]
    by_loc = {}
    for r in low:
        by_loc[r["location_id"]] = by_loc.get(r["location_id"], 0) + 1
    return {"pending_voids": pending_voids, "pending_adjustments": pending, "recent_adjustments": recent, "issues_today": today,
            "below_rop": len(low), "below_rop_by_location": by_loc, "without_rop": no_rop}


# ---------------------------------------------------------------------
# Alerts (the rows Module 1 and Purchasing read from `notifications`)
# ---------------------------------------------------------------------
# Shop at or below ROP    -> 'low_stock' alert for the shop manager (Module 1 turns it into an RF).
# Warehouse at/below ROP  -> 'restock' alert for the warehouse manager (Purchasing turns it into a REF).
# An RF line the warehouse cannot fully reserve -> a 'shortage' row on the warehouse restock alert.
# One ACTIVE alert per type and location. Dismissed or completed alerts are never reopened: the next
# stock movement of an item that is still low creates a fresh one.

def _notif_type(location_id):
    loc = get_location(location_id)
    return None if loc is None else ("low_stock" if loc["loc_type"] == "shop" else "restock")


def _active_notification(location_id, create=False):
    ntype = _notif_type(location_id)
    if ntype is None:
        return None
    row = _b().one("SELECT id FROM notifications WHERE notif_type = :t AND location_id = :l AND status = 'active'",
                   t=ntype, l=location_id)
    if row:
        return row["id"]
    if not create:
        return None
    return _b().one("INSERT INTO notifications (notif_type, location_id, status) VALUES (:t, :l, 'active') RETURNING id",
                    t=ntype, l=location_id)["id"]


def _settings(item_id, location_id):
    return _b().one("SELECT rop, max_level FROM item_location_settings WHERE item_id = :i AND location_id = :l",
                    i=item_id, l=location_id) or {"rop": 0, "max_level": 0}


def _upsert_alert_item(nid, item_id, location_id, reason):
    bal = inv.get_balance(item_id, location_id)
    st = _settings(item_id, location_id)
    suggested = max(1, st["max_level"] - bal["available"])
    _b().execute(
        "INSERT INTO notification_items (notification_id, item_id, current_qty, rop, suggested_qty, reason) "
        "VALUES (:n, :i, :c, :r, :s, :why) ON CONFLICT (notification_id, item_id) DO UPDATE SET "
        "current_qty = :c, rop = :r, suggested_qty = :s, reason = :why",
        n=nid, i=item_id, c=bal["available"], r=st["rop"], s=suggested, why=reason)


def _close_if_empty(nid):
    left = _b().one("SELECT COUNT(*) AS n FROM notification_items WHERE notification_id = :n", n=nid)["n"]
    if left == 0:
        _b().execute("UPDATE notifications SET status = 'completed', closed_at = CURRENT_TIMESTAMP "
                     "WHERE id = :n AND status = 'active'", n=nid)


def refresh_alerts(location_id, item_ids):
    """Call after stock of these items changed at this location (sale, adjustment, receipt, reservation).
    Adds items that are now at or below ROP, removes the ones that recovered. Does not commit."""
    low = {r["item_id"] for r in inv.items_below_rop(location_id)}
    for item_id in set(item_ids):
        if item_id in low:
            nid = _active_notification(location_id, create=True)
            existing = _b().one("SELECT reason FROM notification_items WHERE notification_id = :n AND item_id = :i",
                                n=nid, i=item_id)
            _upsert_alert_item(nid, item_id, location_id, existing["reason"] if existing else "below_rop")
        else:
            nid = _active_notification(location_id)
            if nid:
                _b().execute("DELETE FROM notification_items WHERE notification_id = :n AND item_id = :i "
                             "AND reason = 'below_rop'", n=nid, i=item_id)
                _close_if_empty(nid)


def add_shortages(warehouse_id, item_ids):
    """RF lines the warehouse could not fully reserve become 'shortage' rows on its restock alert."""
    for item_id in set(item_ids):
        nid = _active_notification(warehouse_id, create=True)
        _upsert_alert_item(nid, item_id, warehouse_id, "shortage")


# ---------------------------------------------------------------------
# Voiding a mistaken sale: staff REQUEST, the shop manager (or the owner) CONFIRMS
# ---------------------------------------------------------------------
# While a void is requested the sale still counts. The stock goes back only when it is confirmed.

def can_request_void(user, issue):
    if issue["status"] == "void_requested":
        return False, "A void was already requested and is waiting for confirmation."
    if issue["status"] == "voided":
        return False, "This entry was already voided."
    if user["role"] in ("shop_staff", "shop_manager") and issue["location_id"] == user["location_id"]:
        return True, ""
    return False, "Only staff of this shop can request a void."


def can_confirm_void(user, issue):
    """Same rules as adjustments: own shop's manager, never your own request, the owner covers a manager's request."""
    if issue["status"] != "void_requested":
        return False, "There is no void request to confirm."
    if issue["void_requested_by"] == user["id"]:
        return False, "You cannot confirm your own void request."
    if user["role"] == "shop_manager":
        if issue["location_id"] != user["location_id"]:
            return False, "You can only confirm voids for your own shop."
        return True, ""
    if user["role"] == "owner":
        return True, ""
    return False, "Only the shop manager or the owner can confirm a void."


def request_void(user, issue_id, reason):
    issue = get_issue(issue_id, None)
    if issue is None:
        raise InventoryError("Entry not found.")
    ok, why = can_request_void(user, issue)
    if not ok:
        raise InventoryError(why)
    reason = (reason or "").strip()
    if not reason:
        raise InventoryError("A reason is required to request a void.")
    if len(reason) > 200:
        raise InventoryError("The reason can be at most 200 characters.")
    _b().execute("UPDATE stock_issues SET status = 'void_requested', void_reason = :r, void_requested_by = :u, "
                 "void_requested_at = CURRENT_TIMESTAMP WHERE id = :i", r=reason, u=user["id"], i=issue_id)
    inv.write_audit(user["id"], "void_request", "stock_issues", issue_id, old={"status": "posted"},
                    new={"status": "void_requested", "reason": reason})
    return issue["issue_no"]


def review_void(user, issue_id, decision, remarks):
    """decision: 'confirm' puts the stock back and voids the entry; 'reject' returns it to posted. Returns (issue_no, result)."""
    issue = get_issue(issue_id, None)
    if issue is None:
        raise InventoryError("Entry not found.")
    ok, why = can_confirm_void(user, issue)
    if not ok:
        raise InventoryError(why)
    decision = (decision or "").strip().lower()
    if decision not in ("confirm", "reject"):
        raise InventoryError("Select confirm or reject.")
    remarks = (remarks or "").strip()
    if decision == "reject":
        if not remarks:
            raise InventoryError("Remarks are required when rejecting a void request.")
        _b().execute("UPDATE stock_issues SET status = 'posted', void_reason = NULL, void_requested_by = NULL, "
                     "void_requested_at = NULL WHERE id = :i", i=issue_id)
        inv.write_audit(user["id"], "void_reject", "stock_issues", issue_id, old={"status": "void_requested", "reason": issue["void_reason"]},
                        new={"status": "posted", "remarks": remarks})
        return issue["issue_no"], "rejected"
    lines = _b().all("SELECT item_id, qty FROM stock_issue_items WHERE issue_id = :i ORDER BY id", i=issue_id)
    for ln in lines:
        inv.change_stock(ln["item_id"], issue["location_id"], ln["qty"], "adjustment", ref_type="ISS", ref_id=issue_id,
                         ref_no=issue["issue_no"], remarks=("Voided: " + issue["void_reason"])[:200], user_id=user["id"])
    _b().execute("UPDATE stock_issues SET status = 'voided', voided_by = :u, voided_at = CURRENT_TIMESTAMP WHERE id = :i",
                 u=user["id"], i=issue_id)
    inv.write_audit(user["id"], "void_confirm", "stock_issues", issue_id, old={"status": "void_requested"},
                    new={"status": "voided", "reason": issue["void_reason"], "remarks": remarks or None})
    refresh_alerts(issue["location_id"], [ln["item_id"] for ln in lines])
    return issue["issue_no"], "voided"


# ---------------------------------------------------------------------
# RF queue (warehouse manager): reserve stock for requisitions sent by shops
# ---------------------------------------------------------------------

def list_rf_queue(warehouse_id, q="", status="", page=1):
    where, p = "", {"w": warehouse_id}
    if status in ("open", "partially_delivered"):
        where += " AND r.status = :st"
        p["st"] = status
    if q.strip():
        where += " AND (LOWER(r.rf_no) LIKE :q OR LOWER(s.code) LIKE :q)"
        p["q"] = _like(q)
    frm = ("FROM requisitions r JOIN locations s ON s.id = r.shop_id "
           "WHERE r.warehouse_id = :w AND r.status IN ('open', 'partially_delivered')")
    cols = ("SELECT r.id, r.rf_no, COALESCE(r.submitted_at, r.created_at) AS rf_date, s.code AS shop, r.status, "
            "(SELECT COUNT(*) FROM requisition_items x WHERE x.rf_id = r.id) AS n_items, "
            "(SELECT COUNT(*) FROM requisition_items x WHERE x.rf_id = r.id "
            " AND x.qty_requested - x.qty_reserved > 0) AS n_waiting ")
    return _paged("SELECT COUNT(*) AS n " + frm + where, cols + frm + where + " ORDER BY r.id", page, **p)


def get_rf(rf_id, warehouse_id):
    head = _b().one(
        "SELECT r.*, s.code AS shop, u.full_name AS requested_by_name FROM requisitions r "
        "JOIN locations s ON s.id = r.shop_id JOIN users u ON u.id = r.requested_by WHERE r.id = :i", i=rf_id)
    if head is None or head["warehouse_id"] != warehouse_id:
        return None
    head["lines"] = _b().all(
        "SELECT x.id AS rf_item_id, x.item_id, i.item_name, x.qty_requested, x.qty_reserved, x.qty_delivered, "
        "COALESCE(b.on_hand, 0) AS on_hand, COALESCE(b.reserved, 0) AS reserved_all "
        "FROM requisition_items x JOIN items i ON i.id = x.item_id "
        "LEFT JOIN stock_balances b ON b.item_id = x.item_id AND b.location_id = :w "
        "WHERE x.rf_id = :i ORDER BY x.id", i=rf_id, w=warehouse_id)
    for ln in head["lines"]:
        ln["available"] = ln["on_hand"] - ln["reserved_all"]
        ln["remaining"] = ln["qty_requested"] - ln["qty_reserved"]      # qty_reserved counts everything reserved so far, even if already shipped
        ln["suggest"] = max(0, min(ln["remaining"], ln["available"]))
    return head


def reserve_rf(user, rf_id, pairs):
    """pairs: (rf_item_id, qty to reserve now). Returns (units_reserved, short_item_count)."""
    rf = get_rf(rf_id, user["location_id"])
    if rf is None:
        raise InventoryError("Requisition not found for your warehouse.")
    if rf["status"] not in ("open", "partially_delivered"):
        raise InventoryError("This requisition is %s, so nothing can be reserved." % rf["status"].replace("_", " "))
    by_id = {ln["rf_item_id"]: ln for ln in rf["lines"]}
    asked = {}
    for rf_item_id, qty in pairs:
        if not str(rf_item_id).strip():
            continue
        rid = _whole(rf_item_id, "Line")
        if rid not in by_id:
            raise InventoryError("A line does not belong to this requisition.")
        asked[rid] = _whole(qty or "0", "Quantity to reserve")
    reserved_now, touched = 0, []
    for rid, qty in asked.items():
        ln = by_id[rid]
        if qty == 0:
            continue
        if qty > ln["remaining"]:
            raise InventoryError("%s: only %d still needed." % (ln["item_name"], ln["remaining"]))
        try:
            inv.reserve(rid, ln["item_id"], rf["warehouse_id"], qty, user["id"])
        except InventoryError as e:
            raise InventoryError("%s: %s" % (ln["item_name"], e))
        _b().execute("UPDATE requisition_items SET qty_reserved = qty_reserved + :q WHERE id = :i", q=qty, i=rid)
        ln["qty_reserved"] += qty
        ln["remaining"] -= qty
        reserved_now += qty
        touched.append(ln["item_id"])
    short = [ln["item_id"] for ln in rf["lines"] if ln["remaining"] > 0]
    if touched:
        refresh_alerts(rf["warehouse_id"], touched)
    if short:
        add_shortages(rf["warehouse_id"], short)
    inv.write_audit(user["id"], "reserve", "requisitions", rf_id,
                    new={"rf_no": rf["rf_no"], "reserved": {by_id[r]["item_id"]: q for r, q in asked.items() if q}, "short_items": short})
    return reserved_now, len(short)
