"""Tests for app/inventory_service.py.

Run from the project folder:   python -m unittest discover tests -v

They use an in-memory SQLite copy of only the tables the stock core touches,
so they need no PostgreSQL. SQLite is close but not identical, so run the
real screens against PostgreSQL too.
"""
import json
import sqlite3
import unittest

from app import inventory_service as inv

SCHEMA = """
CREATE TABLE items (id INTEGER PRIMARY KEY, item_code TEXT, is_active INTEGER DEFAULT 1);
CREATE TABLE stock_balances (
  item_id INTEGER, location_id INTEGER,
  on_hand INTEGER NOT NULL DEFAULT 0 CHECK (on_hand >= 0),
  reserved INTEGER NOT NULL DEFAULT 0 CHECK (reserved >= 0),
  updated_at TEXT, PRIMARY KEY (item_id, location_id), CHECK (reserved <= on_hand));
CREATE TABLE stock_ledger (
  id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER, location_id INTEGER,
  movement_type TEXT, qty_change INTEGER CHECK (qty_change <> 0),
  balance_after INTEGER CHECK (balance_after >= 0),
  ref_type TEXT, ref_id INTEGER, ref_no TEXT, remarks TEXT, created_by INTEGER, created_at TEXT);
CREATE TABLE reservations (
  id INTEGER PRIMARY KEY AUTOINCREMENT, rf_item_id INTEGER, item_id INTEGER, location_id INTEGER,
  qty INTEGER CHECK (qty > 0), status TEXT, reserved_by INTEGER, reserved_at TEXT, released_at TEXT);
CREATE TABLE item_location_settings (
  item_id INTEGER, location_id INTEGER, rop INTEGER, max_level INTEGER, PRIMARY KEY (item_id, location_id));
CREATE TABLE document_sequences (doc_type TEXT, doc_year INTEGER, last_no INTEGER DEFAULT 0,
  PRIMARY KEY (doc_type, doc_year));
CREATE TABLE audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, action TEXT,
  table_name TEXT, record_id INTEGER, old_values TEXT, new_values TEXT, ip_address TEXT, created_at TEXT);
"""


class SqliteBackend:
    def __init__(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def execute(self, sql, **p):
        self.db.execute(sql, p)

    def one(self, sql, **p):
        r = self.db.execute(sql, p).fetchone()
        return dict(r) if r else None

    def all(self, sql, **p):
        return [dict(r) for r in self.db.execute(sql, p).fetchall()]


WH, SHOP = 1, 2     # location ids
TIRE, TUBE = 10, 11  # item ids


class StockCoreTests(unittest.TestCase):
    def setUp(self):
        self.be = SqliteBackend()
        inv.set_backend(self.be)
        inv._backend_supports_locking = False
        self.be.execute("INSERT INTO items (id, item_code) VALUES (10, 'T1'), (11, 'T2')")

    def ledger(self):
        return self.be.all("SELECT * FROM stock_ledger ORDER BY id")

    def test_stock_in_updates_balance_and_ledger(self):
        r = inv.change_stock(TIRE, WH, 20, "opening", user_id=1)
        self.assertEqual(r, {"on_hand": 20, "reserved": 0, "available": 20})
        led = self.ledger()
        self.assertEqual(len(led), 1)
        self.assertEqual((led[0]["qty_change"], led[0]["balance_after"]), (20, 20))

    def test_cannot_go_below_zero(self):
        inv.change_stock(TIRE, SHOP, 3, "opening")
        with self.assertRaises(inv.InventoryError):
            inv.change_stock(TIRE, SHOP, -4, "issue")
        self.assertEqual(inv.get_balance(TIRE, SHOP)["on_hand"], 3)
        self.assertEqual(len(self.ledger()), 1)   # nothing written for the failed change

    def test_cannot_issue_reserved_stock(self):
        inv.change_stock(TIRE, WH, 10, "opening")
        inv.reserve(1, TIRE, WH, 8)
        with self.assertRaises(inv.InventoryError):
            inv.change_stock(TIRE, WH, -3, "issue")      # only 2 available
        inv.change_stock(TIRE, WH, -2, "issue")          # exactly the available part is fine
        self.assertEqual(inv.get_balance(TIRE, WH), {"on_hand": 8, "reserved": 8, "available": 0})

    def test_bad_quantities(self):
        for q in (0, 1.5, True):
            with self.assertRaises(inv.InventoryError):
                inv.change_stock(TIRE, WH, q, "adjustment")
        with self.assertRaises(inv.InventoryError):
            inv.change_stock(TIRE, WH, 1, "gift")

    def test_reserve_more_than_available_fails(self):
        inv.change_stock(TIRE, WH, 5, "opening")
        with self.assertRaises(inv.InventoryError):
            inv.reserve(1, TIRE, WH, 6)
        inv.reserve(1, TIRE, WH, 5)
        with self.assertRaises(inv.InventoryError):
            inv.reserve(2, TIRE, WH, 1)

    def test_release_frees_stock_without_moving_it(self):
        inv.change_stock(TIRE, WH, 10, "opening")
        rid = inv.reserve(1, TIRE, WH, 4)
        self.assertEqual(inv.get_available(TIRE, WH), 6)
        inv.release_reservation(rid, "cancelled")
        self.assertEqual(inv.get_balance(TIRE, WH), {"on_hand": 10, "reserved": 0, "available": 10})
        with self.assertRaises(inv.InventoryError):       # cannot release twice
            inv.release_reservation(rid)

    def test_consume_reservation_deducts_and_closes(self):
        inv.change_stock(TIRE, WH, 10, "opening")
        rid = inv.reserve(1, TIRE, WH, 4)
        r = inv.consume_reservation(rid, ref_no="TS-2026-0001", user_id=2)
        self.assertEqual(r, {"on_hand": 6, "reserved": 0, "available": 6})
        last = self.ledger()[-1]
        self.assertEqual((last["movement_type"], last["qty_change"], last["ref_no"]),
                         ("transfer_out", -4, "TS-2026-0001"))
        with self.assertRaises(inv.InventoryError):
            inv.consume_reservation(rid)

    def test_below_rop_uses_available_and_skips_unset_items(self):
        s = "INSERT INTO item_location_settings VALUES (%d, %d, %d, %d)"
        self.be.execute(s % (TIRE, WH, 5, 20))
        self.be.execute(s % (TUBE, WH, 0, 0))             # ROP not set up yet
        inv.change_stock(TIRE, WH, 10, "opening")
        inv.change_stock(TUBE, WH, 0 + 1, "opening")
        self.assertEqual(inv.items_below_rop(WH), [])
        inv.reserve(1, TIRE, WH, 6)                        # available 4 <= ROP 5
        rows = inv.items_below_rop(WH)
        self.assertEqual([(r["item_id"], r["available"], r["suggested_qty"]) for r in rows],
                         [(TIRE, 4, 16)])
        self.assertTrue(inv.is_below_rop(TIRE, WH))
        self.assertFalse(inv.is_below_rop(TUBE, WH))

    def test_item_with_no_stock_row_counts_as_zero(self):
        self.be.execute("INSERT INTO item_location_settings VALUES (10, 2, 3, 10)")
        rows = inv.items_below_rop(SHOP)
        self.assertEqual((rows[0]["on_hand"], rows[0]["suggested_qty"]), (0, 10))

    def test_document_numbers_count_up_per_type_and_year(self):
        self.assertEqual(inv.next_doc_no("ISS", 2026), "ISS-2026-0001")
        self.assertEqual(inv.next_doc_no("ISS", 2026), "ISS-2026-0002")
        self.assertEqual(inv.next_doc_no("ADJ", 2026), "ADJ-2026-0001")
        self.assertEqual(inv.next_doc_no("ISS", 2027), "ISS-2027-0001")

    def test_audit_log(self):
        inv.write_audit(1, "create", "stock_issues", 7, new={"issue_no": "ISS-2026-0001"})
        row = self.be.one("SELECT * FROM audit_log")
        self.assertEqual((row["action"], row["record_id"], row["old_values"]), ("create", 7, None))
        self.assertEqual(json.loads(row["new_values"]), {"issue_no": "ISS-2026-0001"})


if __name__ == "__main__":
    unittest.main()
