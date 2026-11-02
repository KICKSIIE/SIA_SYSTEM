"""Inventory reports for the owner. Each report returns (columns, rows) so the page and the CSV download share one query."""
import datetime as dt

from . import inventory_service as inv

HTML_LIMIT = 500          # rows shown on screen. The CSV download has every row.

REPORTS = {
    "stock": ("Stock on hand", "On hand, reserved and available for every item and location, with rack and ROP"),
    "reorder": ("Items at or below ROP", "What needs restocking, with the suggested quantity and lead time"),
    "movements": ("Stock movements", "Every IN and OUT from the stock ledger for a date range"),
    "sales": ("Sales and issues", "What was sold or issued in a date range, including voided entries"),
    "adjustments": ("Stock adjustments", "Counts, damage and losses with who asked and who approved"),
}


def _b():
    return inv.backend()


def _like(q):
    return "%" + q.strip().lower() + "%"


def _dates(args):
    today = dt.date.today()
    d_from = (args.get("date_from") or (today - dt.timedelta(days=30)).isoformat()).strip()
    d_to = (args.get("date_to") or today.isoformat()).strip()
    return d_from, d_to


def run(name, args):
    """Returns (columns, rows, filters_used). `args` is request.args."""
    q = (args.get("q") or "")
    loc = args.get("location", type=int)
    if name == "stock":
        where, p = "", {}
        if loc:
            where += " AND l.id = :loc"; p["loc"] = loc
        if args.get("category"):
            where += " AND i.category = :cat"; p["cat"] = args["category"]
        if q.strip():
            where += " AND (LOWER(i.item_name) LIKE :q OR LOWER(i.item_code) LIKE :q)"; p["q"] = _like(q)
        rows = _b().all(
            "SELECT i.item_code, i.item_name, i.category, i.brand, i.model, i.size, i.ply_rating, i.pattern, l.code AS location, "
            "s.rack, COALESCE(b.on_hand, 0) AS on_hand, COALESCE(b.reserved, 0) AS reserved, "
            "COALESCE(b.on_hand, 0) - COALESCE(b.reserved, 0) AS available, COALESCE(s.rop, 0) AS rop, COALESCE(s.max_level, 0) AS max_level "
            "FROM items i CROSS JOIN locations l LEFT JOIN stock_balances b ON b.item_id = i.id AND b.location_id = l.id "
            "LEFT JOIN item_location_settings s ON s.item_id = i.id AND s.location_id = l.id "
            "WHERE i.is_active AND l.is_active AND (b.item_id IS NOT NULL OR s.item_id IS NOT NULL)" + where +
            " ORDER BY i.item_name, l.code", **p)
        for r in rows:
            r["status"] = "Out of stock" if r["on_hand"] == 0 else ("Below ROP" if r["rop"] > 0 and r["available"] <= r["rop"] else "OK")
        cols = ["item_code", "item_name", "category", "brand", "model", "size", "ply_rating", "pattern", "location", "rack",
                "on_hand", "reserved", "available", "rop", "max_level", "status"]
    elif name == "reorder":
        rows = inv.items_below_rop(loc)
        names = {r["id"]: r for r in _b().all("SELECT id, item_code, item_name FROM items")}
        locs = {r["id"]: r["code"] for r in _b().all("SELECT id, code FROM locations")}
        lead = {(r["item_id"], r["location_id"]): r["lead_time_days"] for r in
                _b().all("SELECT item_id, location_id, lead_time_days FROM item_location_settings")}
        for r in rows:
            r["item_code"], r["item_name"] = names[r["item_id"]]["item_code"], names[r["item_id"]]["item_name"]
            r["location"], r["lead_time_days"] = locs[r["location_id"]], lead.get((r["item_id"], r["location_id"]), 0)
        rows.sort(key=lambda r: (r["location"], r["available"], r["item_name"]))
        cols = ["item_code", "item_name", "location", "on_hand", "reserved", "available", "rop", "max_level", "suggested_qty", "lead_time_days"]
    elif name == "movements":
        d_from, d_to = _dates(args)
        where, p = "", {"f": d_from, "t": d_to + " 23:59:59"}
        if loc:
            where += " AND sl.location_id = :loc"; p["loc"] = loc
        if q.strip():
            where += " AND (LOWER(i.item_name) LIKE :q OR LOWER(i.item_code) LIKE :q)"; p["q"] = _like(q)
        rows = _b().all(
            "SELECT sl.created_at AS date, l.code AS location, i.item_code, i.item_name, sl.movement_type, sl.qty_change, "
            "sl.balance_after, sl.ref_no, sl.remarks FROM stock_ledger sl JOIN items i ON i.id = sl.item_id "
            "JOIN locations l ON l.id = sl.location_id WHERE sl.created_at >= :f AND sl.created_at <= :t" + where +
            " ORDER BY sl.created_at DESC, sl.id DESC", **p)
        cols = ["date", "location", "item_code", "item_name", "movement_type", "qty_change", "balance_after", "ref_no", "remarks"]
    elif name == "sales":
        d_from, d_to = _dates(args)
        where, p = "", {"f": d_from, "t": d_to}
        if loc:
            where += " AND si.location_id = :loc"; p["loc"] = loc
        if q.strip():
            where += " AND (LOWER(i.item_name) LIKE :q OR LOWER(si.issue_no) LIKE :q OR LOWER(COALESCE(si.customer_name, '')) LIKE :q)"; p["q"] = _like(q)
        rows = _b().all(
            "SELECT si.issue_no, si.issue_date, l.code AS location, si.customer_name, si.document_ref, si.reason, "
            "i.item_code, i.item_name, x.qty, si.status FROM stock_issues si JOIN stock_issue_items x ON x.issue_id = si.id "
            "JOIN items i ON i.id = x.item_id JOIN locations l ON l.id = si.location_id "
            "WHERE si.issue_date >= :f AND si.issue_date <= :t" + where + " ORDER BY si.issue_date DESC, si.id DESC, i.item_name", **p)
        cols = ["issue_no", "issue_date", "location", "customer_name", "document_ref", "reason", "item_code", "item_name", "qty", "status"]
    elif name == "adjustments":
        d_from, d_to = _dates(args)
        where, p = "", {"f": d_from, "t": d_to + " 23:59:59"}
        if loc:
            where += " AND a.location_id = :loc"; p["loc"] = loc
        if q.strip():
            where += " AND (LOWER(i.item_name) LIKE :q OR LOWER(a.adj_no) LIKE :q)"; p["q"] = _like(q)
        rows = _b().all(
            "SELECT a.adj_no, a.created_at AS date, l.code AS location, a.reason, a.status, i.item_code, i.item_name, "
            "x.qty_system, x.qty_actual, x.qty_actual - x.qty_system AS difference, ru.full_name AS requested_by, "
            "vu.full_name AS reviewed_by, a.review_remarks FROM stock_adjustments a "
            "JOIN stock_adjustment_items x ON x.adjustment_id = a.id JOIN items i ON i.id = x.item_id "
            "JOIN locations l ON l.id = a.location_id JOIN users ru ON ru.id = a.requested_by "
            "LEFT JOIN users vu ON vu.id = a.reviewed_by WHERE a.created_at >= :f AND a.created_at <= :t" + where +
            " ORDER BY a.id DESC, i.item_name", **p)
        cols = ["adj_no", "date", "location", "reason", "status", "item_code", "item_name", "qty_system", "qty_actual",
                "difference", "requested_by", "reviewed_by", "review_remarks"]
    else:
        return None
    return cols, rows
