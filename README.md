# Inventory System (Flask + PostgreSQL)

Structure for the four modules: **Requisition, Inventory, Purchasing, Delivery**.
Status: the **Inventory module works** (stock, ROP, sales / issues and void requests, adjustments, items, brands and patterns, alerts, RF queue, reports). Requisition, Purchasing and Delivery
are still placeholder screens: their save buttons say "not implemented yet". See `CHANGES_AND_MISSING_PARTS.md`.

## Run it (Windows PowerShell)

```powershell
# 1. Python packages
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# 2. settings: copy the example, then open .env and put your postgres password in DATABASE_URL
copy .env.example .env

# 3. database (psql must be on PATH, see below)
createdb -U postgres inventory_db
psql -U postgres -d inventory_db -v ON_ERROR_STOP=1 -f database/schema.sql
psql -U postgres -d inventory_db -v ON_ERROR_STOP=1 -f database/seed_items.sql
psql -U postgres -d inventory_db -v ON_ERROR_STOP=1 -f database/seed_users.sql
psql -U postgres -d inventory_db -v ON_ERROR_STOP=1 -f database/seed_demo_stock.sql   # optional, DEMO data

# 4. start
python run.py                  # open http://127.0.0.1:5000
```

If `psql` is not recognized, add PostgreSQL to PATH for this window (change 18 to your version):
`$env:Path += ";C:\Program Files\PostgreSQL\18\bin"`

Use "Preview as another role" at the top to log in as a demo user of each role (password of all demo users: `changeme`).
The real login is not built yet.

## Folders

| Path | What it is |
|---|---|
| `database/schema.sql` | all 39 tables, constraints and indexes |
| `app/__init__.py` | app factory, registers the blueprints |
| `app/inventory_service.py` | **stock core**: the only place that changes stock (`change_stock`, `reserve`, `release_reservation`, `consume_reservation`, `items_below_rop`, `next_doc_no`, `write_audit`). Other modules call these, never write their own stock UPDATE |
| `app/inventory_ops.py` | Inventory module queries and save workflows (ROP, stock list, issues, adjustments, dashboard numbers) |
| `app/report_ops.py` | the owner's inventory reports (page and CSV) |
| `docs/STOCK_CORE_FOR_OTHER_MODULES.md` | **read this if you build Requisition, Purchasing or Delivery**: which stock functions to call, and when |
| `app/item_ops.py` | item list, add and edit item (owner), brand and pattern pick-lists |
| `app/session_user.py` | who is logged in and which location they may see |
| `scripts/import_excel.py`, `scripts/import_rules.py` | turn the client's Excel item names into seed SQL (see below) |
| `tests/` | `python -m unittest discover tests -v` (runs on SQLite, no PostgreSQL needed) |
| `app/roles.py` | roles, the sidebar menu per role, `roles_required` |
| `app/blueprints/` | `requisition.py`, `inventory.py`, `purchasing.py`, `auth.py`, `dashboard.py`. `delivery/` and `admin/` are folders with one file per owner (`transfers.py`, `shop_receiving.py`, `supplier_receiving.py`, `people.py`, `items.py`) so team members do not edit the same file |
| `app/templates/<module>/` | one HTML file per screen (lists, forms, details) |
| `app/templates/dashboard/` | one dashboard per role |
| `app/static/` | `css/style.css`, `js/app.js` (add/remove rows in item tables) |

## Where to start coding

1. Real login (users table, password hash) and replace `/dev/role/<role>`.
2. Items, locations and ROP settings (owner), so there is data to work with.
3. Record sale / issue, then stock ledger and stock balances.
4. Requisition, then reserve and transfer slip, then receive (AR).
5. Alerts, then purchasing (REF, RFQ, approval, PO), then receiving (RM).

Each route has a `TODO` where the database work goes. Document numbers (RF-2025-0001 and so on) use the `document_sequences` table.


## About the seed files

`seed_items.sql` is the item list (names from the client Excel). `seed_users.sql` creates demo locations and demo users.
`seed_demo_stock.sql` is made-up stock, ROP, lead times and racks for development only. For real use skip it, delete the demo
users, and enter the real stock through approved adjustments.

## Rebuilding the seed files from the client Excel

```
pip install openpyxl
python scripts/import_excel.py INVENTORY.xlsx
```

The Excel is used only for the item names. The script cuts each name into brand, model, size, ply, pattern and
category (rules in `scripts/import_rules.py`, one place to change), and writes `database/seed_items.sql`,
`database/seed_demo_stock.sql` and `database/import_report.md`. Read the report: it lists what was guessed or made up.
Items are classified only by their specs. There is no vehicle type.

## Tests

`python -m unittest discover tests -v` (58 tests, run on SQLite, no PostgreSQL needed).
