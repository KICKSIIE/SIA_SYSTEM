# Inventory System (Flask + PostgreSQL)

Structure for the four modules: **Requisition, Inventory, Purchasing, Delivery**.
This is a starting skeleton: the database, the forms (HTML), the page flow for every role and the Flask structure.
**No business logic yet.** Every save button shows "not implemented yet".

## Run it

```bash
python -m venv venv
venv\Scripts\activate          # Windows   (Mac/Linux: source venv/bin/activate)
pip install -r requirements.txt

# 1. create the database and tables
createdb inventory_db
psql -d inventory_db -f database/schema.sql

# 2. settings
copy .env.example .env         # then edit DATABASE_URL and SECRET_KEY

# 3. start
python run.py                  # open http://127.0.0.1:5000
```

On the login page, pick a role to preview its menu and screens (temporary preview, remove when the real login is built).

## Folders

| Path | What it is |
|---|---|
| `database/schema.sql` | all 39 tables, constraints and indexes |
| `app/__init__.py` | app factory, registers the blueprints |
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
