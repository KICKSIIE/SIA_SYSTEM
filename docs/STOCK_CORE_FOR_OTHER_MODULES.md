# How Requisition, Purchasing and Delivery use the Inventory module

Written for the people building the other modules. Inventory owns **all stock numbers**. Never write your own
`UPDATE stock_balances`. Call the functions below.

```python
from app import inventory_service as inv      # stock, reservations, numbers, audit
from app import inventory_ops as ops          # alerts, RF queue
from app.inventory_service import InventoryError
from app.session_user import current_user, scope_location
```

## The pattern for every save

The functions never commit. Do everything that belongs together, then commit once:

```python
try:
    ...                      # your inserts, change_stock(...), inv.write_audit(...)
    inv.commit()
except InventoryError as e:  # a business rule, the message is safe to show
    inv.rollback()
    flash(str(e), "error")
```

`InventoryError` is raised for: not enough stock, reserved stock, a quantity that is not a whole number above zero,
an unknown movement type. A failed save writes nothing, and it does not use up a document number.

## Quick reference

| Need | Call |
|---|---|
| Stock now | `inv.get_balance(item_id, location_id)` gives `on_hand`, `reserved`, `available` |
| Add or remove stock | `inv.change_stock(item_id, location_id, +qty or -qty, movement_type, ref_type=..., ref_id=..., ref_no=..., remarks=..., user_id=...)` |
| Document number | `inv.next_doc_no("RF")` gives `RF-2026-0001`. Types: ISS, ADJ, RF, REF, RFQ, PO, TS, AR, RM, DR |
| Audit log | `inv.write_audit(user_id, "create", "requisitions", record_id, old=None, new={...})` |
| Items at or below ROP | `inv.items_below_rop(location_id)` includes `suggested_qty` (max level minus available) |
| After stock of items changed | `ops.refresh_alerts(location_id, [item_ids])` adds or clears the low-stock / restock alert rows |

Movement types: `opening`, `supplier_receipt`, `transfer_out`, `transfer_in`, `issue`, `adjustment`.
**Available = on hand minus reserved.** Reserved stock cannot be sold or adjusted away.

## Requisition (Module 1)

* **Alerts** are rows in `notifications` (+ `notification_items`). Inventory creates and updates them, you read them:
  `low_stock` for a shop (shop manager), `restock` for the warehouse. One **active** alert per type and location.
  Each item row has `current_qty`, `rop`, `suggested_qty` and a `reason` (`below_rop` or `shortage`).
* **Dismiss** needs a reason (the table refuses `dismissed` without `dismissed_reason`). Set `closed_by` and `closed_at`.
  A dismissed alert is not reopened by itself. The next movement of an item that is still low creates a new one.
* **Create an RF** from an alert: use each item's `suggested_qty` as the default quantity. Number: `inv.next_doc_no("RF")`.
  Shop and warehouse must differ. Set `status = 'open'` and `submitted_at` when the shop manager submits.
  The RF then appears in the warehouse manager's **RF queue** (Inventory module). You do not build that screen.
* **Cancel an RF:** a reason is required. Free every active reservation:
  `inv.release_reservation(reservation_id, "cancelled")`, then set the RF `cancelled`.

## Purchasing (Module 3)

* The warehouse **restock alert** is the starting point of a REF. Lines that the RF queue could not fully reserve show up
  as `reason = 'shortage'`.
* When you finish with an alert (REF created) set its `status = 'completed'`, `closed_by`, `closed_at`.
  Inventory removes `below_rop` rows by itself once stock recovers, but **never removes `shortage` rows**, because only
  Purchasing knows when that shortage is handled.
* Goods arriving from a supplier (receiving memo): see Delivery below.

## Delivery (Module 4)

* **Receive from a supplier** (warehouse):
  `inv.change_stock(item, warehouse, +qty, "supplier_receipt", ref_type="RM", ref_id=rm_id, ref_no=rm_no, user_id=...)`
  then `ops.refresh_alerts(warehouse, item_ids)`.
* **Release a transfer slip (TS)**, the stock leaves the warehouse. Use the reservation made in the RF queue:
  `inv.consume_reservation(reservation_id, ref_type="TS", ref_id=ts_id, ref_no=ts_no, user_id=...)`.
  It deducts the stock, closes the reservation and writes a `transfer_out` ledger row in one step.
  Then call `ops.refresh_alerts(warehouse, item_ids)`.
* **Shop signs the AR** (stock arrives at the shop):
  `inv.change_stock(item, shop, +qty_received, "transfer_in", ref_type="AR", ref_id=ar_id, ref_no=ar_no, user_id=...)`,
  then raise `requisition_items.qty_delivered` and set the RF `partially_delivered` or `closed`.
* **Variance** (received less than sent): receive what was counted. The difference goes in your discrepancy report.

### What the RF line quantities mean (important)

| Column | Meaning |
|---|---|
| `qty_requested` | what the shop asked for |
| `qty_reserved` | **everything reserved so far, including units already shipped.** The RF queue adds to it. **Delivery must not decrease it.** |
| `qty_delivered` | units the shop has signed for (you update this at the AR) |

Still to reserve = `qty_requested - qty_reserved`. Still to deliver = `qty_reserved - qty_delivered`.

## What Inventory already does for you

* Sale or issue, adjustment approval, confirming a void and the RF queue all update stock and alerts for you.
* Stock list, stock card (with ledger), ROP settings, items, brands and patterns, reports (stock, reorder, movements, sales, adjustments).

## Rules to keep

1. Only the stock functions change stock. Reports and the audit trail depend on that.
2. Filter every list by location unless the role is the owner (`scope_location(current_user())`).
3. Write an audit row for every create, update, approve or cancel.
4. Run the tests before merging: `python -m unittest discover tests -v`.
