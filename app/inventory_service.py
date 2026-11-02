"""Stock core: the ONLY place that changes stock.

Everyone (Requisition, Purchasing, Delivery, Inventory screens) calls these
functions instead of writing their own UPDATE on stock_balances.

Rules enforced here
  * Stock never goes below zero.
  * On hand can never drop below reserved (reserved stock belongs to an RF).
  * Every stock change writes one stock_ledger row, in the same transaction
    as the balance update.

Transactions
  These functions do NOT commit. The caller commits once, after everything
  that belongs together has been saved (for example: issue header + issue
  lines + stock change + audit log):

      try:
          change_stock(...)
          write_audit(...)
          db.session.commit()
      except InventoryError as e:
          db.session.rollback()
          flash(str(e), "error")

Available stock = on_hand - reserved.
"""
import json
from datetime import date

VALID_MOVEMENTS = ("opening", "supplier_receipt", "transfer_out",
                   "transfer_in", "issue", "adjustment")


class InventoryError(Exception):
    """A business-rule problem. The message is safe to show to the user."""


# ---------------------------------------------------------------------
# Database access (kept in one small place so it can be swapped in tests)
# ---------------------------------------------------------------------

class _SqlAlchemyBackend:
    """Default backend: runs plain SQL through Flask-SQLAlchemy's session."""

    def _run(self, sql, params):
        from sqlalchemy import text
        from .extensions import db
        return db.session.execute(text(sql), params)

    def execute(self, sql, **params):
        self._run(sql, params)

    def one(self, sql, **params):
        row = self._run(sql, params).mappings().first()
        return dict(row) if row else None

    def all(self, sql, **params):
        return [dict(r) for r in self._run(sql, params).mappings().all()]

    def commit(self):
        from .extensions import db
        db.session.commit()

    def rollback(self):
        from .extensions import db
        db.session.rollback()


_backend = _SqlAlchemyBackend()


def backend():
    """The active database backend (used by inventory_ops.py)."""
    return _backend


def commit():
    _backend.commit()


def rollback():
    _backend.rollback()


def set_backend(backend):
    """Used by the tests. Not needed in the app."""
    global _backend
    _backend = backend


_backend_supports_locking = True   # tests on SQLite switch this off


def _lock(sql):
    """Row lock so two users cannot change the same stock at once."""
    return sql + " FOR UPDATE" if _backend_supports_locking else sql


# ---------------------------------------------------------------------
# Reading stock
# ---------------------------------------------------------------------

def get_balance(item_id, location_id):
    """Return {'on_hand', 'reserved', 'available'}. Zeros if there is no row yet."""
    row = _backend.one(
        "SELECT on_hand, reserved FROM stock_balances "
        "WHERE item_id = :i AND location_id = :l", i=item_id, l=location_id)
    on_hand = row["on_hand"] if row else 0
    reserved = row["reserved"] if row else 0
    return {"on_hand": on_hand, "reserved": reserved, "available": on_hand - reserved}


def get_available(item_id, location_id):
    return get_balance(item_id, location_id)["available"]


def _locked_balance(item_id, location_id):
    """Make sure the row exists, then lock it and return it."""
    _backend.execute(
        "INSERT INTO stock_balances (item_id, location_id, on_hand, reserved) "
        "VALUES (:i, :l, 0, 0) ON CONFLICT (item_id, location_id) DO NOTHING",
        i=item_id, l=location_id)
    return _backend.one(
        _lock("SELECT on_hand, reserved FROM stock_balances "
              "WHERE item_id = :i AND location_id = :l"),
        i=item_id, l=location_id)


# ---------------------------------------------------------------------
# Changing stock
# ---------------------------------------------------------------------

def change_stock(item_id, location_id, qty_change, movement_type, *,
                 ref_type=None, ref_id=None, ref_no=None, remarks=None,
                 user_id=None, from_reserved=False):
    """Add (+) or remove (-) stock and write the ledger row.

    qty_change     positive = in, negative = out. Cannot be zero.
    movement_type  opening, supplier_receipt, transfer_out, transfer_in,
                   issue or adjustment.
    ref_*          the document that caused it (ISS, TS, AR, RM, ADJ).
    from_reserved  True only when the stock leaving was already reserved
                   (the warehouse releasing a TS). The reserved quantity is
                   reduced by the same amount. Prefer consume_reservation().

    Returns the new {'on_hand', 'reserved', 'available'}.
    """
    if not isinstance(qty_change, int) or isinstance(qty_change, bool) or qty_change == 0:
        raise InventoryError("Quantity must be a whole number and not zero.")
    if movement_type not in VALID_MOVEMENTS:
        raise InventoryError("Unknown movement type: %s" % movement_type)
    if from_reserved and qty_change > 0:
        raise InventoryError("Only stock going out can come from a reservation.")

    bal = _locked_balance(item_id, location_id)
    new_on_hand = bal["on_hand"] + qty_change
    new_reserved = bal["reserved"]

    if from_reserved:
        new_reserved -= -qty_change
        if new_reserved < 0:
            raise InventoryError("Cannot take more than the reserved quantity.")

    if new_on_hand < 0:
        raise InventoryError(
            "Not enough stock: %d on hand, %d requested." % (bal["on_hand"], -qty_change))
    if new_on_hand < new_reserved:
        raise InventoryError(
            "Not enough available stock: %d available (the rest is reserved), %d requested."
            % (bal["on_hand"] - bal["reserved"], -qty_change))

    _backend.execute(
        "UPDATE stock_balances SET on_hand = :oh, reserved = :rs, updated_at = CURRENT_TIMESTAMP "
        "WHERE item_id = :i AND location_id = :l",
        oh=new_on_hand, rs=new_reserved, i=item_id, l=location_id)
    _backend.execute(
        "INSERT INTO stock_ledger (item_id, location_id, movement_type, qty_change, balance_after, "
        "ref_type, ref_id, ref_no, remarks, created_by) "
        "VALUES (:i, :l, :mt, :q, :ba, :rt, :rid, :rno, :rem, :u)",
        i=item_id, l=location_id, mt=movement_type, q=qty_change, ba=new_on_hand,
        rt=ref_type, rid=ref_id, rno=ref_no, rem=remarks, u=user_id)

    return {"on_hand": new_on_hand, "reserved": new_reserved,
            "available": new_on_hand - new_reserved}


# ---------------------------------------------------------------------
# Reservations (warehouse stock held for an RF line)
# ---------------------------------------------------------------------

def reserve(rf_item_id, item_id, location_id, qty, user_id=None):
    """Hold stock for an RF line. Returns the new reservation id."""
    if not isinstance(qty, int) or isinstance(qty, bool) or qty <= 0:
        raise InventoryError("Reserved quantity must be a whole number above zero.")
    bal = _locked_balance(item_id, location_id)
    available = bal["on_hand"] - bal["reserved"]
    if qty > available:
        raise InventoryError("Only %d available to reserve, %d requested." % (available, qty))

    _backend.execute(
        "UPDATE stock_balances SET reserved = reserved + :q, updated_at = CURRENT_TIMESTAMP "
        "WHERE item_id = :i AND location_id = :l", q=qty, i=item_id, l=location_id)
    row = _backend.one(
        "INSERT INTO reservations (rf_item_id, item_id, location_id, qty, status, reserved_by) "
        "VALUES (:rf, :i, :l, :q, 'reserved', :u) RETURNING id",
        rf=rf_item_id, i=item_id, l=location_id, q=qty, u=user_id)
    return row["id"]


def _open_reservation(reservation_id):
    res = _backend.one(
        _lock("SELECT id, item_id, location_id, qty, status FROM reservations WHERE id = :r"),
        r=reservation_id)
    if res is None:
        raise InventoryError("Reservation not found.")
    if res["status"] != "reserved":
        raise InventoryError("This reservation is already %s." % res["status"])
    return res


def release_reservation(reservation_id, new_status="released"):
    """Free reserved stock WITHOUT moving it (RF cancelled, or reserved too much).

    new_status is 'released' or 'cancelled'.
    """
    if new_status not in ("released", "cancelled"):
        raise InventoryError("Invalid reservation status.")
    res = _open_reservation(reservation_id)
    _locked_balance(res["item_id"], res["location_id"])
    _backend.execute(
        "UPDATE stock_balances SET reserved = reserved - :q, updated_at = CURRENT_TIMESTAMP "
        "WHERE item_id = :i AND location_id = :l",
        q=res["qty"], i=res["item_id"], l=res["location_id"])
    _backend.execute(
        "UPDATE reservations SET status = :s, released_at = CURRENT_TIMESTAMP WHERE id = :r",
        s=new_status, r=reservation_id)


def consume_reservation(reservation_id, *, ref_type="TS", ref_id=None, ref_no=None,
                        remarks=None, user_id=None):
    """The reserved stock physically leaves (TS released): deduct it and close
    the reservation in one step. Writes a 'transfer_out' ledger row."""
    res = _open_reservation(reservation_id)
    result = change_stock(res["item_id"], res["location_id"], -res["qty"], "transfer_out",
                          ref_type=ref_type, ref_id=ref_id, ref_no=ref_no,
                          remarks=remarks, user_id=user_id, from_reserved=True)
    _backend.execute(
        "UPDATE reservations SET status = 'released', released_at = CURRENT_TIMESTAMP WHERE id = :r",
        r=reservation_id)
    return result


# ---------------------------------------------------------------------
# ROP checks (feed the low-stock and restock alerts)
# ---------------------------------------------------------------------

def items_below_rop(location_id=None):
    """Items whose AVAILABLE stock is at or below the ROP.

    Items with ROP = 0 are 'not set up yet' and are skipped.
    Returns rows with item_id, location_id, on_hand, reserved, available,
    rop, max_level and suggested_qty (max_level - available).
    """
    sql = (
        "SELECT s.item_id, s.location_id, "
        "COALESCE(b.on_hand, 0) AS on_hand, COALESCE(b.reserved, 0) AS reserved, "
        "COALESCE(b.on_hand, 0) - COALESCE(b.reserved, 0) AS available, "
        "s.rop, s.max_level, "
        "s.max_level - (COALESCE(b.on_hand, 0) - COALESCE(b.reserved, 0)) AS suggested_qty "
        "FROM item_location_settings s "
        "JOIN items i ON i.id = s.item_id AND i.is_active "
        "LEFT JOIN stock_balances b ON b.item_id = s.item_id AND b.location_id = s.location_id "
        "WHERE s.rop > 0 AND COALESCE(b.on_hand, 0) - COALESCE(b.reserved, 0) <= s.rop")
    if location_id is not None:
        return _backend.all(sql + " AND s.location_id = :l ORDER BY s.item_id", l=location_id)
    return _backend.all(sql + " ORDER BY s.location_id, s.item_id")


def is_below_rop(item_id, location_id):
    return any(r["item_id"] == item_id for r in items_below_rop(location_id))


# ---------------------------------------------------------------------
# Document numbers and the audit log
# ---------------------------------------------------------------------

def next_doc_no(doc_type, year=None):
    """Next number for ISS, ADJ, RF, REF, RFQ, PO, TS, AR, RM, DR.
    Returns for example 'ISS-2026-0001'. Safe when two users save at once."""
    year = year or date.today().year
    row = _backend.one(
        "INSERT INTO document_sequences (doc_type, doc_year, last_no) VALUES (:t, :y, 1) "
        "ON CONFLICT (doc_type, doc_year) DO UPDATE "
        "SET last_no = document_sequences.last_no + 1 RETURNING last_no",
        t=doc_type, y=year)
    return "%s-%d-%04d" % (doc_type, year, row["last_no"])


def write_audit(user_id, action, table_name, record_id=None, old=None, new=None, ip=None):
    """One audit_log row. old / new are dicts (or None)."""
    _backend.execute(
        "INSERT INTO audit_log (user_id, action, table_name, record_id, old_values, new_values, ip_address) "
        "VALUES (:u, :a, :t, :r, :o, :n, :ip)",
        u=user_id, a=action, t=table_name, r=record_id,
        o=json.dumps(old, default=str) if old is not None else None,
        n=json.dumps(new, default=str) if new is not None else None, ip=ip)
