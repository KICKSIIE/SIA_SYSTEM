"""Small SQLite copy of the tables the Inventory screens use (for tests only)."""
SCHEMA = """
CREATE TABLE roles (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE, name TEXT);
CREATE TABLE locations (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE, name TEXT, loc_type TEXT, is_active INTEGER DEFAULT 1);
CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, full_name TEXT, role_id INTEGER, location_id INTEGER, is_active INTEGER DEFAULT 1);
CREATE TABLE items (id INTEGER PRIMARY KEY AUTOINCREMENT, item_code TEXT UNIQUE, item_name TEXT UNIQUE, brand TEXT, size TEXT,
  ply_rating TEXT, pattern TEXT, model TEXT, category TEXT DEFAULT 'tire', unit TEXT DEFAULT 'pc', is_active INTEGER DEFAULT 1);
CREATE TABLE item_location_settings (item_id INTEGER, location_id INTEGER, rop INTEGER DEFAULT 0, max_level INTEGER DEFAULT 0,
  lead_time_days INTEGER DEFAULT 0, rack TEXT, updated_by INTEGER, updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (item_id, location_id), CHECK (max_level >= rop));
CREATE TABLE stock_balances (item_id INTEGER, location_id INTEGER, on_hand INTEGER NOT NULL DEFAULT 0 CHECK (on_hand >= 0),
  reserved INTEGER NOT NULL DEFAULT 0 CHECK (reserved >= 0), updated_at TEXT, PRIMARY KEY (item_id, location_id), CHECK (reserved <= on_hand));
CREATE TABLE stock_ledger (id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER, location_id INTEGER, movement_type TEXT,
  qty_change INTEGER CHECK (qty_change <> 0), balance_after INTEGER CHECK (balance_after >= 0), ref_type TEXT, ref_id INTEGER,
  ref_no TEXT, remarks TEXT, created_by INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE stock_issues (id INTEGER PRIMARY KEY AUTOINCREMENT, issue_no TEXT UNIQUE, location_id INTEGER, customer_name TEXT,
  issue_date TEXT, document_ref TEXT, reason TEXT CHECK (reason IN ('sale','other')), remarks TEXT, recorded_by INTEGER,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  status TEXT NOT NULL DEFAULT 'posted' CHECK (status IN ('posted','void_requested','voided')),
  void_reason TEXT, void_requested_by INTEGER, void_requested_at TEXT, voided_by INTEGER, voided_at TEXT,
  CHECK (status = 'posted' OR (void_reason IS NOT NULL AND void_requested_by IS NOT NULL)),
  CHECK (status <> 'voided' OR voided_by IS NOT NULL),
  CHECK (voided_by IS NULL OR voided_by <> void_requested_by));
CREATE TABLE stock_issue_items (id INTEGER PRIMARY KEY AUTOINCREMENT, issue_id INTEGER, item_id INTEGER, qty INTEGER CHECK (qty > 0));
CREATE TABLE reservations (id INTEGER PRIMARY KEY AUTOINCREMENT, rf_item_id INTEGER, item_id INTEGER, location_id INTEGER,
  qty INTEGER CHECK (qty > 0), status TEXT, reserved_by INTEGER, reserved_at TEXT, released_at TEXT);
CREATE TABLE acknowledgment_receipts (id INTEGER PRIMARY KEY AUTOINCREMENT, ar_no TEXT UNIQUE);
CREATE TABLE stock_adjustments (id INTEGER PRIMARY KEY AUTOINCREMENT, adj_no TEXT UNIQUE, location_id INTEGER, reason TEXT,
  status TEXT DEFAULT 'pending', source_ar_id INTEGER, remarks TEXT, requested_by INTEGER NOT NULL, reviewed_by INTEGER,
  review_remarks TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, reviewed_at TEXT,
  CHECK (status = 'pending' OR reviewed_by IS NOT NULL), CHECK (reviewed_by IS NULL OR reviewed_by <> requested_by));
CREATE TABLE stock_adjustment_items (id INTEGER PRIMARY KEY AUTOINCREMENT, adjustment_id INTEGER, item_id INTEGER,
  qty_system INTEGER, qty_actual INTEGER, item_remarks TEXT, UNIQUE (adjustment_id, item_id));
CREATE TABLE notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, notif_type TEXT CHECK (notif_type IN ('low_stock','restock')),
  location_id INTEGER, status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','completed','dismissed')), dismissed_reason TEXT,
  closed_by INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP, closed_at TEXT, CHECK (status <> 'dismissed' OR dismissed_reason IS NOT NULL));
CREATE TABLE notification_items (id INTEGER PRIMARY KEY AUTOINCREMENT, notification_id INTEGER, item_id INTEGER, current_qty INTEGER,
  rop INTEGER, suggested_qty INTEGER CHECK (suggested_qty > 0), reason TEXT NOT NULL DEFAULT 'below_rop' CHECK (reason IN ('shortage','below_rop')),
  UNIQUE (notification_id, item_id));
CREATE TABLE requisitions (id INTEGER PRIMARY KEY AUTOINCREMENT, rf_no TEXT UNIQUE, shop_id INTEGER, warehouse_id INTEGER, notification_id INTEGER,
  status TEXT DEFAULT 'draft' CHECK (status IN ('draft','open','partially_delivered','closed','cancelled')), requested_by INTEGER, remarks TEXT,
  cancel_reason TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, submitted_at TEXT, closed_at TEXT, CHECK (shop_id <> warehouse_id));
CREATE TABLE requisition_items (id INTEGER PRIMARY KEY AUTOINCREMENT, rf_id INTEGER, item_id INTEGER, qty_requested INTEGER CHECK (qty_requested > 0),
  qty_reserved INTEGER NOT NULL DEFAULT 0 CHECK (qty_reserved >= 0), qty_delivered INTEGER NOT NULL DEFAULT 0 CHECK (qty_delivered >= 0),
  UNIQUE (rf_id, item_id), CHECK (qty_delivered <= qty_requested));
CREATE TABLE document_sequences (doc_type TEXT, doc_year INTEGER, last_no INTEGER DEFAULT 0, PRIMARY KEY (doc_type, doc_year));
CREATE TABLE audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, action TEXT, table_name TEXT, record_id INTEGER,
  old_values TEXT, new_values TEXT, ip_address TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
"""


class SqliteBackend:
    def __init__(self):
        import sqlite3
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def execute(self, sql, **p):
        self.db.execute(sql, p)

    def one(self, sql, **p):
        r = self.db.execute(sql, p).fetchone()
        return dict(r) if r else None

    def all(self, sql, **p):
        return [dict(r) for r in self.db.execute(sql, p).fetchall()]

    def commit(self):
        self.db.commit()

    def rollback(self):
        self.db.rollback()
