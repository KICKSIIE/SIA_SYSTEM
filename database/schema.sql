-- =====================================================================
-- Inventory System: Requisition, Inventory, Purchasing, Delivery
-- PostgreSQL 13+ (uses GENERATED ... AS IDENTITY and generated columns)
-- Structure only: tables, constraints and indexes. No functions or triggers yet.
-- Run once on an empty database:  psql -d inventory_db -f schema.sql
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. MASTER DATA
-- ---------------------------------------------------------------------

-- Document numbers (RF-2025-0001, PO-2025-0001, ...). The app reads and bumps last_no.
CREATE TABLE document_sequences (
    doc_type    VARCHAR(10) NOT NULL,           -- ISS, RF, REF, RFQ, PO, TS, AR, RM, DR, ADJ
    doc_year    SMALLINT    NOT NULL,
    last_no     INTEGER     NOT NULL DEFAULT 0,
    PRIMARY KEY (doc_type, doc_year)
);

CREATE TABLE roles (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code        VARCHAR(30) NOT NULL UNIQUE,
    name        VARCHAR(60) NOT NULL
);

-- Shops and warehouses (one table, separated by type)
CREATE TABLE locations (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code        VARCHAR(20)  NOT NULL UNIQUE,
    name        VARCHAR(100) NOT NULL,
    loc_type    VARCHAR(10)  NOT NULL CHECK (loc_type IN ('shop', 'warehouse')),
    address     VARCHAR(200),
    is_active   BOOLEAN      NOT NULL DEFAULT TRUE
);

CREATE TABLE users (
    id            INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username      VARCHAR(50)  NOT NULL UNIQUE,
    full_name     VARCHAR(100) NOT NULL,
    email         VARCHAR(120),
    password_hash VARCHAR(255) NOT NULL,
    role_id       INTEGER NOT NULL REFERENCES roles(id),
    location_id   INTEGER REFERENCES locations(id),   -- the shop or warehouse the user works in
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Tires, tubes and flaps
CREATE TABLE items (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    item_code   VARCHAR(30)  NOT NULL UNIQUE,
    item_name   VARCHAR(150) NOT NULL UNIQUE,       -- e.g. ANSU 9.5R17.5 18PR BY616
    brand       VARCHAR(50)  NOT NULL,
    size        VARCHAR(30),
    ply_rating  VARCHAR(10),
    pattern     VARCHAR(40),
    category    VARCHAR(10)  NOT NULL DEFAULT 'tire' CHECK (category IN ('tire', 'tube', 'flap', 'other')),
    unit        VARCHAR(10)  NOT NULL DEFAULT 'pc',
    is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- ROP and max level per item AND per location (set by the owner)
CREATE TABLE item_location_settings (
    item_id        INTEGER NOT NULL REFERENCES items(id),
    location_id    INTEGER NOT NULL REFERENCES locations(id),
    rop            INTEGER NOT NULL DEFAULT 0 CHECK (rop >= 0),
    max_level      INTEGER NOT NULL DEFAULT 0,
    lead_time_days INTEGER NOT NULL DEFAULT 0 CHECK (lead_time_days >= 0),
    updated_by     INTEGER REFERENCES users(id),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (item_id, location_id),
    CHECK (max_level >= rop)
);

-- Current stock per item and location (the ledger below keeps the history)
CREATE TABLE stock_balances (
    item_id      INTEGER NOT NULL REFERENCES items(id),
    location_id  INTEGER NOT NULL REFERENCES locations(id),
    on_hand      INTEGER NOT NULL DEFAULT 0 CHECK (on_hand >= 0),          -- stock cannot go below zero
    reserved     INTEGER NOT NULL DEFAULT 0 CHECK (reserved >= 0),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (item_id, location_id),
    CHECK (reserved <= on_hand)
);

CREATE TABLE suppliers (
    id             INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    supplier_name  VARCHAR(120) NOT NULL UNIQUE,
    contact_person VARCHAR(100),
    email          VARCHAR(120),
    phone          VARCHAR(30),
    address        VARCHAR(200),
    is_regular     BOOLEAN NOT NULL DEFAULT FALSE,   -- regular supplier: RFQ can be skipped
    is_active      BOOLEAN NOT NULL DEFAULT TRUE
);

-- Agreed prices of regular suppliers
CREATE TABLE supplier_items (
    id           INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    supplier_id  INTEGER NOT NULL REFERENCES suppliers(id),
    item_id      INTEGER NOT NULL REFERENCES items(id),
    agreed_price NUMERIC(12,2) NOT NULL CHECK (agreed_price >= 0),
    valid_from   DATE NOT NULL DEFAULT CURRENT_DATE,
    valid_to     DATE,
    UNIQUE (supplier_id, item_id, valid_from)
);

-- Drivers and vehicles have no login. They are only named on the Transfer Slip.
CREATE TABLE drivers (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name   VARCHAR(100) NOT NULL,
    contact_no  VARCHAR(30),
    license_no  VARCHAR(30),
    is_active   BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE vehicles (
    id            INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plate_no      VARCHAR(20) NOT NULL UNIQUE,
    vehicle_type  VARCHAR(40),
    is_active     BOOLEAN NOT NULL DEFAULT TRUE
);

-- ---------------------------------------------------------------------
-- 2. ALERTS (shared by Requisition and Purchasing)
--    One active alert per type and location. It lists many items and stays
--    active until the RF/REF is created or the alert is dismissed with a reason.
-- ---------------------------------------------------------------------

CREATE TABLE notifications (
    id               INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    notif_type       VARCHAR(10) NOT NULL CHECK (notif_type IN ('low_stock', 'restock')),   -- low_stock -> shop manager, restock -> warehouse manager
    location_id      INTEGER NOT NULL REFERENCES locations(id),
    status           VARCHAR(10) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'completed', 'dismissed')),
    dismissed_reason TEXT,
    closed_by        INTEGER REFERENCES users(id),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at        TIMESTAMPTZ,
    CHECK (status <> 'dismissed' OR dismissed_reason IS NOT NULL)
);
CREATE UNIQUE INDEX uq_active_notification ON notifications (notif_type, location_id) WHERE status = 'active';

CREATE TABLE notification_items (
    id              INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    notification_id INTEGER NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
    item_id         INTEGER NOT NULL REFERENCES items(id),
    current_qty     INTEGER NOT NULL,
    rop             INTEGER NOT NULL,
    suggested_qty   INTEGER NOT NULL CHECK (suggested_qty > 0),        -- max level minus current stock
    reason          VARCHAR(10) NOT NULL DEFAULT 'below_rop' CHECK (reason IN ('shortage', 'below_rop')),
    UNIQUE (notification_id, item_id)
);

-- ---------------------------------------------------------------------
-- 3. REQUISITION MODULE (shop -> warehouse)
-- ---------------------------------------------------------------------

CREATE TABLE requisitions (
    id              INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    rf_no           VARCHAR(20) NOT NULL UNIQUE,
    shop_id         INTEGER NOT NULL REFERENCES locations(id),
    warehouse_id    INTEGER NOT NULL REFERENCES locations(id),
    notification_id INTEGER REFERENCES notifications(id),
    status          VARCHAR(20) NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'open', 'partially_delivered', 'closed', 'cancelled')),
    requested_by    INTEGER NOT NULL REFERENCES users(id),
    remarks         TEXT,
    cancel_reason   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    submitted_at    TIMESTAMPTZ,
    closed_at       TIMESTAMPTZ,
    CHECK (shop_id <> warehouse_id),
    CHECK (status <> 'cancelled' OR cancel_reason IS NOT NULL)
);

CREATE TABLE requisition_items (
    id             INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    rf_id          INTEGER NOT NULL REFERENCES requisitions(id) ON DELETE CASCADE,
    item_id        INTEGER NOT NULL REFERENCES items(id),
    qty_requested  INTEGER NOT NULL CHECK (qty_requested > 0),
    qty_reserved   INTEGER NOT NULL DEFAULT 0 CHECK (qty_reserved >= 0),
    qty_delivered  INTEGER NOT NULL DEFAULT 0 CHECK (qty_delivered >= 0),
    UNIQUE (rf_id, item_id),
    CHECK (qty_delivered <= qty_requested)
);

-- ---------------------------------------------------------------------
-- 4. INVENTORY MODULE
-- ---------------------------------------------------------------------

-- Every stock change is one row here (replaces the IN / OUT columns of the Excel file)
CREATE TABLE stock_ledger (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    item_id        INTEGER NOT NULL REFERENCES items(id),
    location_id    INTEGER NOT NULL REFERENCES locations(id),
    movement_type  VARCHAR(20) NOT NULL
                   CHECK (movement_type IN ('opening', 'supplier_receipt', 'transfer_out', 'transfer_in', 'issue', 'adjustment')),
    qty_change     INTEGER NOT NULL CHECK (qty_change <> 0),        -- + in, - out
    balance_after  INTEGER NOT NULL CHECK (balance_after >= 0),
    ref_type       VARCHAR(20),                                     -- ISS, TS, AR, RM, ADJ
    ref_id         INTEGER,
    ref_no         VARCHAR(30),
    remarks        VARCHAR(200),
    created_by     INTEGER REFERENCES users(id),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Sale / stock issue entry (a simple stock-out record, no prices)
CREATE TABLE stock_issues (
    id            INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    issue_no      VARCHAR(20) NOT NULL UNIQUE,
    location_id   INTEGER NOT NULL REFERENCES locations(id),
    customer_name VARCHAR(120),                                     -- optional, free text (walk-in, or the customer's name)
    issue_date    DATE NOT NULL DEFAULT CURRENT_DATE,
    document_ref  VARCHAR(40),                                      -- receipt or invoice number
    reason        VARCHAR(10) NOT NULL DEFAULT 'sale' CHECK (reason IN ('sale', 'other')),
    remarks       VARCHAR(200),
    recorded_by   INTEGER NOT NULL REFERENCES users(id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE stock_issue_items (
    id        INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    issue_id  INTEGER NOT NULL REFERENCES stock_issues(id) ON DELETE CASCADE,
    item_id   INTEGER NOT NULL REFERENCES items(id),
    qty       INTEGER NOT NULL CHECK (qty > 0)
);

-- Stock reserved in the warehouse for an RF line
CREATE TABLE reservations (
    id           INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    rf_item_id   INTEGER NOT NULL REFERENCES requisition_items(id),
    item_id      INTEGER NOT NULL REFERENCES items(id),
    location_id  INTEGER NOT NULL REFERENCES locations(id),
    qty          INTEGER NOT NULL CHECK (qty > 0),
    status       VARCHAR(10) NOT NULL DEFAULT 'reserved' CHECK (status IN ('reserved', 'released', 'cancelled')),
    reserved_by  INTEGER REFERENCES users(id),
    reserved_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    released_at  TIMESTAMPTZ
);

-- Count difference, damaged or lost items, delivery variance. Approved by the manager of the same location (warehouse manager or shop manager); the owner is notified.
CREATE TABLE stock_adjustments (
    id             INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    adj_no         VARCHAR(20) NOT NULL UNIQUE,
    location_id    INTEGER NOT NULL REFERENCES locations(id),
    reason         VARCHAR(20) NOT NULL
                   CHECK (reason IN ('count_difference', 'damaged', 'lost', 'delivery_variance', 'other')),
    status         VARCHAR(10) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    source_ar_id   INTEGER,                                          -- FK added at the end (AR table is created later)
    remarks        TEXT,
    requested_by   INTEGER NOT NULL REFERENCES users(id),
    reviewed_by    INTEGER REFERENCES users(id),
    review_remarks TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_at    TIMESTAMPTZ,
    CHECK (status = 'pending' OR reviewed_by IS NOT NULL),
    CHECK (reviewed_by IS NULL OR reviewed_by <> requested_by)       -- nobody approves their own adjustment
);

CREATE TABLE stock_adjustment_items (
    id             INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    adjustment_id  INTEGER NOT NULL REFERENCES stock_adjustments(id) ON DELETE CASCADE,
    item_id        INTEGER NOT NULL REFERENCES items(id),
    qty_system     INTEGER NOT NULL CHECK (qty_system >= 0),
    qty_actual     INTEGER NOT NULL CHECK (qty_actual >= 0),
    qty_diff       INTEGER GENERATED ALWAYS AS (qty_actual - qty_system) STORED,
    item_remarks   VARCHAR(200),
    UNIQUE (adjustment_id, item_id)
);

-- ---------------------------------------------------------------------
-- 5. PURCHASING MODULE (warehouse -> supplier)
-- ---------------------------------------------------------------------

CREATE TABLE replenishments (            -- REF
    id              INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ref_no          VARCHAR(20) NOT NULL UNIQUE,
    warehouse_id    INTEGER NOT NULL REFERENCES locations(id),
    notification_id INTEGER REFERENCES notifications(id),
    status          VARCHAR(20) NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'submitted', 'rfq_sent', 'for_approval', 'approved', 'receiving', 'closed', 'cancelled')),
    created_by      INTEGER NOT NULL REFERENCES users(id),
    remarks         TEXT,
    cancel_reason   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    submitted_at    TIMESTAMPTZ,
    closed_at       TIMESTAMPTZ,
    CHECK (status <> 'cancelled' OR cancel_reason IS NOT NULL)
);

CREATE TABLE replenishment_items (
    id            INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ref_id        INTEGER NOT NULL REFERENCES replenishments(id) ON DELETE CASCADE,
    item_id       INTEGER NOT NULL REFERENCES items(id),
    qty_requested INTEGER NOT NULL CHECK (qty_requested > 0),
    qty_received  INTEGER NOT NULL DEFAULT 0 CHECK (qty_received >= 0),
    reason        VARCHAR(10) NOT NULL DEFAULT 'below_rop' CHECK (reason IN ('shortage', 'below_rop')),
    rf_id         INTEGER REFERENCES requisitions(id),               -- the waiting RF, when the reason is a shortage
    UNIQUE (ref_id, item_id)
);

CREATE TABLE rfqs (
    id             INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    rfq_no         VARCHAR(20) NOT NULL UNIQUE,
    ref_id         INTEGER NOT NULL REFERENCES replenishments(id),
    reply_deadline DATE,
    terms          TEXT,
    status         VARCHAR(10) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'sent', 'closed')),
    created_by     INTEGER NOT NULL REFERENCES users(id),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at        TIMESTAMPTZ
);

CREATE TABLE rfq_suppliers (
    rfq_id       INTEGER NOT NULL REFERENCES rfqs(id) ON DELETE CASCADE,
    supplier_id  INTEGER NOT NULL REFERENCES suppliers(id),
    sent_at      TIMESTAMPTZ,
    replied_at   TIMESTAMPTZ,
    PRIMARY KEY (rfq_id, supplier_id)
);

-- Suppliers reply by email. The warehouse manager records the reply here.
CREATE TABLE quotations (
    id             INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    rfq_id         INTEGER NOT NULL REFERENCES rfqs(id),
    supplier_id    INTEGER NOT NULL REFERENCES suppliers(id),
    quotation_ref  VARCHAR(50),
    quotation_date DATE NOT NULL DEFAULT CURRENT_DATE,
    valid_until    DATE,
    total_amount   NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (total_amount >= 0),
    notes          TEXT,
    recorded_by    INTEGER NOT NULL REFERENCES users(id),
    recorded_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (rfq_id, supplier_id)
);

CREATE TABLE quotation_items (
    id                    INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    quotation_id          INTEGER NOT NULL REFERENCES quotations(id) ON DELETE CASCADE,
    replenishment_item_id INTEGER NOT NULL REFERENCES replenishment_items(id),
    item_id               INTEGER NOT NULL REFERENCES items(id),
    qty_offered           INTEGER NOT NULL CHECK (qty_offered >= 0),
    unit_price            NUMERIC(12,2) NOT NULL CHECK (unit_price >= 0),
    lead_time_days        INTEGER CHECK (lead_time_days >= 0),
    UNIQUE (quotation_id, replenishment_item_id)
);

-- The owner's single approval: supplier and price (from a quotation, or the agreed price of a regular supplier)
CREATE TABLE purchase_approvals (
    id            INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ref_id        INTEGER NOT NULL REFERENCES replenishments(id),
    supplier_id   INTEGER NOT NULL REFERENCES suppliers(id),
    basis         VARCHAR(15) NOT NULL CHECK (basis IN ('quotation', 'agreed_price')),
    quotation_id  INTEGER REFERENCES quotations(id),
    decision      VARCHAR(10) NOT NULL DEFAULT 'pending' CHECK (decision IN ('pending', 'approved', 'rejected')),
    submitted_by  INTEGER NOT NULL REFERENCES users(id),
    submitted_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_by    INTEGER REFERENCES users(id),
    decided_at    TIMESTAMPTZ,
    remarks       TEXT,
    CHECK (basis <> 'quotation' OR quotation_id IS NOT NULL),
    CHECK (decision = 'pending' OR decided_by IS NOT NULL)
);

CREATE TABLE purchase_orders (
    id            INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    po_no         VARCHAR(20) NOT NULL UNIQUE,
    ref_id        INTEGER NOT NULL REFERENCES replenishments(id),
    supplier_id   INTEGER NOT NULL REFERENCES suppliers(id),
    approval_id   INTEGER NOT NULL UNIQUE REFERENCES purchase_approvals(id),
    po_date       DATE NOT NULL DEFAULT CURRENT_DATE,
    expected_date DATE,
    terms         TEXT,
    status        VARCHAR(20) NOT NULL DEFAULT 'draft'
                  CHECK (status IN ('draft', 'sent', 'partially_received', 'received', 'cancelled')),
    total_amount  NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (total_amount >= 0),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at       TIMESTAMPTZ
);

CREATE TABLE purchase_order_items (
    id                    INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    po_id                 INTEGER NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
    replenishment_item_id INTEGER NOT NULL REFERENCES replenishment_items(id),
    item_id               INTEGER NOT NULL REFERENCES items(id),
    qty_ordered           INTEGER NOT NULL CHECK (qty_ordered > 0),
    unit_price            NUMERIC(12,2) NOT NULL CHECK (unit_price >= 0),
    qty_received          INTEGER NOT NULL DEFAULT 0 CHECK (qty_received >= 0),
    UNIQUE (po_id, replenishment_item_id),
    CHECK (qty_received <= qty_ordered)
);

-- ---------------------------------------------------------------------
-- 6. DELIVERY MODULE
--    (a) receiving from the supplier   (b) transfer from warehouse to shop
-- ---------------------------------------------------------------------

CREATE TABLE goods_receipts (             -- RM
    id             INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    rm_no          VARCHAR(20) NOT NULL UNIQUE,
    po_id          INTEGER NOT NULL REFERENCES purchase_orders(id),
    supplier_dr_no VARCHAR(40),                                      -- the supplier's Delivery Receipt number
    received_date  DATE NOT NULL DEFAULT CURRENT_DATE,
    received_by    INTEGER NOT NULL REFERENCES users(id),
    remarks        TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE goods_receipt_items (
    id            INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    rm_id         INTEGER NOT NULL REFERENCES goods_receipts(id) ON DELETE CASCADE,
    po_item_id    INTEGER NOT NULL REFERENCES purchase_order_items(id),
    item_id       INTEGER NOT NULL REFERENCES items(id),
    qty_delivered INTEGER NOT NULL CHECK (qty_delivered >= 0),
    qty_accepted  INTEGER NOT NULL CHECK (qty_accepted >= 0),
    qty_rejected  INTEGER NOT NULL DEFAULT 0 CHECK (qty_rejected >= 0),
    reject_reason VARCHAR(200),
    CHECK (qty_accepted + qty_rejected = qty_delivered)
);

CREATE TABLE discrepancy_reports (
    id              INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    report_no       VARCHAR(20) NOT NULL UNIQUE,
    rm_id           INTEGER NOT NULL REFERENCES goods_receipts(id),
    po_id           INTEGER NOT NULL REFERENCES purchase_orders(id),
    status          VARCHAR(10) NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'follow_up', 'resolved')),
    follow_up_notes TEXT,
    created_by      INTEGER NOT NULL REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at     TIMESTAMPTZ
);

CREATE TABLE discrepancy_items (
    id           INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    report_id    INTEGER NOT NULL REFERENCES discrepancy_reports(id) ON DELETE CASCADE,
    po_item_id   INTEGER NOT NULL REFERENCES purchase_order_items(id),
    item_id      INTEGER NOT NULL REFERENCES items(id),
    qty_short    INTEGER NOT NULL DEFAULT 0 CHECK (qty_short >= 0),
    qty_rejected INTEGER NOT NULL DEFAULT 0 CHECK (qty_rejected >= 0),
    reason       VARCHAR(200)
);

CREATE TABLE transfer_slips (             -- TS
    id               INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ts_no            VARCHAR(20) NOT NULL UNIQUE,
    rf_id            INTEGER NOT NULL REFERENCES requisitions(id),
    from_location_id INTEGER NOT NULL REFERENCES locations(id),
    to_location_id   INTEGER NOT NULL REFERENCES locations(id),
    driver_id        INTEGER REFERENCES drivers(id),
    vehicle_id       INTEGER REFERENCES vehicles(id),
    status           VARCHAR(25) NOT NULL DEFAULT 'draft'
                     CHECK (status IN ('draft', 'assigned', 'loaded', 'in_transit', 'delivered', 'delivered_with_variance', 'cancelled')),
    prepared_by      INTEGER NOT NULL REFERENCES users(id),
    loaded_by        INTEGER REFERENCES users(id),                   -- warehouse staff who loaded and checked
    released_by      INTEGER REFERENCES users(id),                   -- warehouse manager who signed the TS
    released_at      TIMESTAMPTZ,                                    -- warehouse stock is deducted here
    delivered_at     TIMESTAMPTZ,
    remarks          TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (from_location_id <> to_location_id),
    CHECK (status IN ('draft', 'cancelled') OR (driver_id IS NOT NULL AND vehicle_id IS NOT NULL))
);

CREATE TABLE transfer_slip_items (
    id            INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ts_id         INTEGER NOT NULL REFERENCES transfer_slips(id) ON DELETE CASCADE,
    rf_item_id    INTEGER NOT NULL REFERENCES requisition_items(id),
    item_id       INTEGER NOT NULL REFERENCES items(id),
    qty_released  INTEGER NOT NULL CHECK (qty_released > 0),
    loaded        BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (ts_id, rf_item_id)
);

CREATE TABLE acknowledgment_receipts (    -- AR (signed by the shop manager)
    id            INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ar_no         VARCHAR(20) NOT NULL UNIQUE,
    ts_id         INTEGER NOT NULL UNIQUE REFERENCES transfer_slips(id),
    received_by   INTEGER NOT NULL REFERENCES users(id),
    received_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    has_variance  BOOLEAN NOT NULL DEFAULT FALSE,
    remarks       TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE acknowledgment_receipt_items (
    id              INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ar_id           INTEGER NOT NULL REFERENCES acknowledgment_receipts(id) ON DELETE CASCADE,
    ts_item_id      INTEGER NOT NULL REFERENCES transfer_slip_items(id),
    item_id         INTEGER NOT NULL REFERENCES items(id),
    qty_expected    INTEGER NOT NULL CHECK (qty_expected >= 0),
    qty_received    INTEGER NOT NULL CHECK (qty_received >= 0),
    qty_variance    INTEGER GENERATED ALWAYS AS (qty_received - qty_expected) STORED,
    variance_reason VARCHAR(200),
    UNIQUE (ar_id, ts_item_id)
);

ALTER TABLE stock_adjustments
    ADD CONSTRAINT fk_adjustment_source_ar FOREIGN KEY (source_ar_id) REFERENCES acknowledgment_receipts(id);

-- ---------------------------------------------------------------------
-- 7. AUDIT LOG (every change is saved here)
-- ---------------------------------------------------------------------

CREATE TABLE audit_log (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id),
    action      VARCHAR(30) NOT NULL,        -- create, update, approve, reject, release, receive, login, ...
    table_name  VARCHAR(60) NOT NULL,
    record_id   INTEGER,
    old_values  JSONB,
    new_values  JSONB,
    ip_address  VARCHAR(45),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- 8. INDEXES (foreign keys and the columns the screens filter on)
-- ---------------------------------------------------------------------

CREATE INDEX ix_users_role              ON users (role_id);
CREATE INDEX ix_items_category          ON items (category);
CREATE INDEX ix_ledger_item_loc_date    ON stock_ledger (item_id, location_id, created_at);
CREATE INDEX ix_ledger_ref              ON stock_ledger (ref_type, ref_id);
CREATE INDEX ix_issues_location_date    ON stock_issues (location_id, issue_date);
CREATE INDEX ix_issue_items_issue       ON stock_issue_items (issue_id);
CREATE INDEX ix_notif_status            ON notifications (status, notif_type);
CREATE INDEX ix_rf_status               ON requisitions (status);
CREATE INDEX ix_rf_shop                 ON requisitions (shop_id);
CREATE INDEX ix_rf_items_rf             ON requisition_items (rf_id);
CREATE INDEX ix_reservations_rf_item    ON reservations (rf_item_id);
CREATE INDEX ix_adjustments_status      ON stock_adjustments (status);
CREATE INDEX ix_ref_status              ON replenishments (status);
CREATE INDEX ix_ref_items_ref           ON replenishment_items (ref_id);
CREATE INDEX ix_rfq_ref                 ON rfqs (ref_id);
CREATE INDEX ix_quotation_items_q       ON quotation_items (quotation_id);
CREATE INDEX ix_approvals_decision      ON purchase_approvals (decision);
CREATE INDEX ix_po_status               ON purchase_orders (status);
CREATE INDEX ix_po_items_po             ON purchase_order_items (po_id);
CREATE INDEX ix_rm_po                   ON goods_receipts (po_id);
CREATE INDEX ix_ts_status               ON transfer_slips (status);
CREATE INDEX ix_ts_rf                   ON transfer_slips (rf_id);
CREATE INDEX ix_audit_table_record      ON audit_log (table_name, record_id);
CREATE INDEX ix_audit_created           ON audit_log (created_at);

-- ---------------------------------------------------------------------
-- 9. STARTER DATA
-- ---------------------------------------------------------------------

INSERT INTO roles (code, name) VALUES
    ('owner',             'Owner'),
    ('shop_manager',      'Shop Manager'),
    ('shop_staff',        'Shop Staff'),
    ('warehouse_manager', 'Warehouse Manager'),
    ('warehouse_staff',   'Warehouse Staff');
