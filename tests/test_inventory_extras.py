"""Alerts, voiding a sale, the RF queue, brands / patterns and reports."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from app import create_app
from app import inventory_service as inv
from sqlite_schema import SqliteBackend

WH, SHOP = 1, 2
A, B = 1, 2          # item ids


class Base(unittest.TestCase):
    def setUp(self):
        self.be = SqliteBackend()
        inv.set_backend(self.be)
        inv._backend_supports_locking = False
        b = self.be
        for code in ("owner", "shop_manager", "shop_staff", "warehouse_manager", "warehouse_staff"):
            b.execute("INSERT INTO roles (code, name) VALUES (:c, :c)", c=code)
        b.execute("INSERT INTO locations (code, name, loc_type) VALUES ('WH', 'Warehouse', 'warehouse')")
        b.execute("INSERT INTO locations (code, name, loc_type) VALUES ('SHOP', 'Shop', 'shop')")
        for name, role, loc in (("owner", "owner", None), ("whmgr", "warehouse_manager", WH), ("whstaff", "warehouse_staff", WH),
                                ("shopmgr", "shop_manager", SHOP), ("shopstaff", "shop_staff", SHOP)):
            b.execute("INSERT INTO users (username, full_name, role_id, location_id) VALUES (:u, :u, "
                      "(SELECT id FROM roles WHERE code = :r), :l)", u=name, r=role, l=loc)
        self.uid = {r["username"]: r["id"] for r in b.all("SELECT id, username FROM users")}
        b.execute("INSERT INTO items (item_code, item_name, brand, model, size, ply_rating, pattern, category) VALUES "
                  "('TIR-0001', 'ANSU 12R22.5 18PR AL505', 'ANSU', 'AL505', '12R22.5', '18PR', 'Rib', 'tire')")
        b.execute("INSERT INTO items (item_code, item_name, brand, model, size, ply_rating, pattern, category) VALUES "
                  "('TIR-0002', 'JK TYRE 1200-20 18PR JETWAY', 'JK TYRE', 'JETWAY', '1200-20', '18PR', 'Lug', 'tire')")
        b.execute("INSERT INTO item_location_settings (item_id, location_id, rop, max_level, lead_time_days) VALUES (1, 2, 5, 20, 3)")
        b.execute("INSERT INTO item_location_settings (item_id, location_id, rop, max_level, lead_time_days) VALUES (1, 1, 8, 40, 30)")
        b.execute("INSERT INTO item_location_settings (item_id, location_id, rop, max_level, lead_time_days) VALUES (2, 1, 3, 12, 30)")
        inv.change_stock(A, SHOP, 10, "opening")
        inv.change_stock(A, WH, 20, "opening")
        inv.change_stock(B, WH, 4, "opening")
        b.commit()
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.c = self.app.test_client()

    def login(self, name):
        self.c.get("/dev/user/%d" % self.uid[name])

    def bal(self, item, loc):
        return inv.get_balance(item, loc)

    def sell(self, qty, item=A, who="shopstaff"):
        self.login(who)
        return self.c.post("/inventory/issues/new", data={"issue_date": "2026-10-30", "reason": "sale",
                           "item_id[]": [str(item)], "qty[]": [str(qty)]})

    def alerts(self, ntype="low_stock"):
        return self.be.all("SELECT n.id, n.status, ni.item_id, ni.current_qty, ni.rop, ni.suggested_qty, ni.reason FROM notifications n "
                           "LEFT JOIN notification_items ni ON ni.notification_id = n.id WHERE n.notif_type = :t ORDER BY n.id", t=ntype)


class AlertTests(Base):
    def test_sale_that_reaches_rop_creates_one_low_stock_alert(self):
        self.sell(3)                                       # 10 -> 7, above ROP 5
        self.assertEqual(self.alerts(), [])
        self.sell(2)                                       # 7 -> 5, at ROP
        rows = self.alerts()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["item_id"], rows[0]["current_qty"], rows[0]["rop"], rows[0]["suggested_qty"], rows[0]["reason"]),
                         (A, 5, 5, 15, "below_rop"))
        self.sell(1)                                       # 5 -> 4, same alert is updated, not duplicated
        rows = self.alerts()
        self.assertEqual((len(rows), rows[0]["current_qty"], rows[0]["suggested_qty"]), (1, 4, 16))

    def test_stock_recovering_removes_the_item_and_closes_the_alert(self):
        self.sell(6)                                       # 10 -> 4
        self.assertEqual(len(self.alerts()), 1)
        self.login("shopstaff")
        self.c.post("/inventory/adjustments/new", data={"reason": "Count difference", "item_id[]": [str(A)], "qty_actual[]": ["12"]})
        self.login("shopmgr")
        self.c.post("/inventory/adjustments/1/review", data={"decision": "approve", "review_remarks": "recount"})
        self.assertEqual(self.bal(A, SHOP)["on_hand"], 12)
        row = self.be.one("SELECT status FROM notifications")
        self.assertEqual(row["status"], "completed")
        self.assertEqual(self.be.one("SELECT COUNT(*) AS n FROM notification_items")["n"], 0)

    def test_dismissed_alert_is_not_reopened_until_the_next_movement(self):
        self.sell(6)
        self.be.execute("UPDATE notifications SET status = 'dismissed', dismissed_reason = 'not now'")
        self.be.commit()
        self.assertEqual(self.be.one("SELECT COUNT(*) AS n FROM notifications WHERE status = 'active'")["n"], 0)
        self.sell(1)                                       # item is still low and moved again: a new alert
        self.assertEqual(self.be.one("SELECT COUNT(*) AS n FROM notifications WHERE status = 'active'")["n"], 1)

    def test_warehouse_below_rop_makes_a_restock_alert(self):
        self.login("whstaff")
        self.c.post("/inventory/adjustments/new", data={"reason": "Damaged", "item_id[]": [str(A)], "qty_actual[]": ["6"]})
        self.login("whmgr")
        self.c.post("/inventory/adjustments/1/review", data={"decision": "approve", "review_remarks": "ok"})
        rows = self.alerts("restock")
        self.assertEqual((len(rows), rows[0]["current_qty"]), (1, 6))


class VoidTests(Base):
    def req(self, who="shopstaff", reason="Wrong item", issue=1):
        self.login(who)
        return self.c.post("/inventory/issues/%d/void-request" % issue, data={"void_reason": reason})

    def review(self, who, decision="confirm", remarks="", issue=1):
        self.login(who)
        return self.c.post("/inventory/issues/%d/void-review" % issue, data={"decision": decision, "remarks": remarks})

    def status(self):
        return self.be.one("SELECT status FROM stock_issues")["status"]

    def test_staff_requests_manager_confirms_and_stock_returns(self):
        self.sell(6)
        self.assertEqual(len(self.alerts()), 1)
        self.assertEqual(self.req(reason="").status_code, 302)                 # reason is required
        self.assertEqual(self.status(), "posted")
        self.req()
        self.assertEqual(self.status(), "void_requested")
        self.assertEqual(self.bal(A, SHOP)["on_hand"], 4)                      # the sale still counts until confirmed
        self.assertIn("waiting for the shop manager", self.c.get("/inventory/issues/1").get_data(as_text=True))
        self.review("shopmgr")
        self.assertEqual(self.status(), "voided")
        self.assertEqual(self.bal(A, SHOP)["on_hand"], 10)
        row = self.be.one("SELECT void_reason, void_requested_by, voided_by FROM stock_issues")
        self.assertEqual((row["void_reason"], row["void_requested_by"], row["voided_by"]),
                         ("Wrong item", self.uid["shopstaff"], self.uid["shopmgr"]))
        led = self.be.one("SELECT qty_change, ref_no, remarks FROM stock_ledger ORDER BY id DESC LIMIT 1")
        self.assertEqual((led["qty_change"], led["ref_no"]), (6, "ISS-2026-0001"))
        self.assertIn("Voided: Wrong item", led["remarks"])
        self.assertEqual(self.be.one("SELECT COUNT(*) AS n FROM notification_items")["n"], 0)    # alert cleared
        self.review("shopmgr")                                                 # nothing left to confirm
        self.assertEqual(self.bal(A, SHOP)["on_hand"], 10)
        page = self.c.get("/inventory/issues/1").get_data(as_text=True)
        self.assertIn("Confirmed by", page)
        self.assertNotIn("Request void", page)

    def test_reject_keeps_the_sale(self):
        self.sell(2)
        self.req()
        r = self.review("shopmgr", "reject", "")
        self.assertIn("Remarks are required", self.c.get(r.headers["Location"]).get_data(as_text=True))
        self.assertEqual(self.status(), "void_requested")
        self.review("shopmgr", "reject", "Customer did buy it")
        self.assertEqual(self.status(), "posted")
        self.assertEqual(self.bal(A, SHOP)["on_hand"], 8)
        self.assertIsNone(self.be.one("SELECT void_reason FROM stock_issues")["void_reason"])
        self.assertEqual(self.be.one("SELECT COUNT(*) AS n FROM audit_log WHERE action = 'void_reject'")["n"], 1)
        self.req(reason="Second try")                                          # can be requested again
        self.assertEqual(self.status(), "void_requested")

    def test_who_may_request_and_who_may_confirm(self):
        self.sell(2)
        self.login("whmgr")
        self.assertEqual(self.c.post("/inventory/issues/1/void-request", data={"void_reason": "x"}).status_code, 403)
        self.login("owner")
        self.assertEqual(self.c.post("/inventory/issues/1/void-request", data={"void_reason": "x"}).status_code, 403)
        self.req()
        for who in ("shopstaff", "whmgr", "whstaff"):                          # staff cannot confirm their own or anyone's
            self.assertEqual(self.review(who).status_code, 403, who)
        self.assertEqual(self.status(), "void_requested")
        self.be.execute("UPDATE users SET location_id = 1 WHERE username = 'shopmgr'")    # manager of another place
        self.be.commit()
        self.review("shopmgr")
        self.assertEqual(self.status(), "void_requested")
        self.review("owner", remarks="ok")                                     # owner can confirm
        self.assertEqual(self.status(), "voided")

    def test_manager_request_must_be_confirmed_by_someone_else(self):
        self.sell(2, who="shopmgr")
        self.req(who="shopmgr", reason="my mistake")
        self.review("shopmgr")                                                 # cannot confirm own request
        self.assertEqual(self.status(), "void_requested")
        self.review("owner")
        self.assertEqual(self.status(), "voided")
        self.assertEqual(self.bal(A, SHOP)["on_hand"], 10)

    def test_cannot_request_twice_or_after_void(self):
        self.sell(2)
        self.req()
        r = self.req(reason="again")
        self.assertIn("already requested", self.c.get(r.headers["Location"]).get_data(as_text=True))
        self.review("shopmgr")
        r = self.req(reason="again")
        self.assertIn("already voided", self.c.get(r.headers["Location"]).get_data(as_text=True))
        self.assertEqual(self.bal(A, SHOP)["on_hand"], 10)

    def test_dashboard_counts_requests_waiting_for_the_manager(self):
        self.sell(2)
        self.req()
        self.login("shopmgr")
        self.assertIn("Waiting for your confirmation: 1", self.c.get("/").get_data(as_text=True))


class RfQueueTests(Base):
    def make_rf(self, lines):
        self.be.execute("INSERT INTO requisitions (rf_no, shop_id, warehouse_id, status, requested_by, submitted_at) "
                        "VALUES ('RF-2026-0001', 2, 1, 'open', :u, '2026-10-30')", u=self.uid["shopmgr"])
        for item, qty in lines:
            self.be.execute("INSERT INTO requisition_items (rf_id, item_id, qty_requested) VALUES (1, :i, :q)", i=item, q=qty)
        self.be.commit()

    def test_queue_review_and_reserve_with_a_shortage(self):
        self.make_rf([(A, 10), (B, 9)])                    # warehouse has 20 of A, only 4 of B
        self.login("whmgr")
        page = self.c.get("/inventory/rf-queue").get_data(as_text=True)
        self.assertIn("RF-2026-0001", page)
        review = self.c.get("/inventory/rf-queue/1").get_data(as_text=True)
        self.assertIn('name="qty_reserve[]" value="10"', review)          # suggests the full 10 of A
        self.assertIn('name="qty_reserve[]" value="4"', review)           # only 4 of B available
        r = self.c.post("/inventory/rf-queue/1", data={"rf_item_id[]": ["1", "2"], "qty_reserve[]": ["10", "4"]})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.bal(A, WH), {"on_hand": 20, "reserved": 10, "available": 10})
        self.assertEqual(self.bal(B, WH)["reserved"], 4)
        lines = self.be.all("SELECT qty_reserved FROM requisition_items ORDER BY id")
        self.assertEqual([x["qty_reserved"] for x in lines], [10, 4])
        self.assertEqual(self.be.one("SELECT COUNT(*) AS n FROM reservations WHERE status = 'reserved'")["n"], 2)
        short = [x for x in self.alerts("restock") if x["reason"] == "shortage"]
        self.assertEqual([(x["item_id"]) for x in short], [B])
        self.assertIn("5 still needed", self.c.get("/inventory/rf-queue/1").get_data(as_text=True))
        self.assertIn("1</td><td>", self.c.get("/inventory/rf-queue").get_data(as_text=True))

    def test_cannot_reserve_more_than_available_or_needed(self):
        self.make_rf([(A, 10), (B, 9)])
        self.login("whmgr")
        r = self.c.post("/inventory/rf-queue/1", data={"rf_item_id[]": ["2"], "qty_reserve[]": ["5"]})   # only 4 on hand
        self.assertEqual(r.status_code, 200)
        self.assertIn("Only 4 available", r.get_data(as_text=True))
        r = self.c.post("/inventory/rf-queue/1", data={"rf_item_id[]": ["1"], "qty_reserve[]": ["11"]})
        self.assertIn("only 10 still needed", r.get_data(as_text=True))
        self.assertEqual(self.be.one("SELECT COUNT(*) AS n FROM reservations")["n"], 0)

    def test_reserving_the_rest_after_stock_arrives(self):
        self.make_rf([(B, 9)])
        self.login("whmgr")
        self.c.post("/inventory/rf-queue/1", data={"rf_item_id[]": ["1"], "qty_reserve[]": ["4"]})
        inv.change_stock(B, WH, 10, "supplier_receipt")
        self.be.commit()
        r = self.c.post("/inventory/rf-queue/1", data={"rf_item_id[]": ["1"], "qty_reserve[]": ["5"]})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.be.one("SELECT qty_reserved FROM requisition_items")["qty_reserved"], 9)
        self.assertIn("Fully reserved", self.c.get("/inventory/rf-queue/1").get_data(as_text=True))

    def test_only_the_warehouse_manager_of_that_warehouse(self):
        self.make_rf([(A, 2)])
        for who in ("shopstaff", "shopmgr", "whstaff", "owner"):
            self.login(who)
            self.assertEqual(self.c.get("/inventory/rf-queue").status_code, 403, who)
        self.be.execute("UPDATE users SET location_id = 2 WHERE username = 'whmgr'")
        self.be.commit()
        self.login("whmgr")
        self.assertEqual(self.c.get("/inventory/rf-queue/1").status_code, 404)
        self.be.execute("UPDATE users SET location_id = 1 WHERE username = 'whmgr'")
        self.be.execute("UPDATE requisitions SET status = 'closed'")
        self.be.commit()
        self.login("whmgr")
        r = self.c.post("/inventory/rf-queue/1", data={"rf_item_id[]": ["1"], "qty_reserve[]": ["1"]})
        self.assertIn("nothing can be reserved", r.get_data(as_text=True))


class BrandTests(Base):
    def test_rename_and_merge_brands(self):
        self.login("owner")
        self.be.execute("INSERT INTO items (item_code, item_name, brand, size, pattern, category) VALUES "
                        "('TIR-0003', 'JK 900-20', 'JK', '900-20', 'Rib', 'tire')")
        self.be.commit()
        page = self.c.get("/admin/classification").get_data(as_text=True)
        self.assertIn("JK TYRE", page)
        r = self.c.post("/admin/classification", data={"kind": "brand", "old": "JK", "new": "jk tyre"})
        msg = self.c.get(r.headers["Location"]).get_data(as_text=True)
        self.assertIn("Merged JK into JK TYRE (1 item)", msg)
        self.assertEqual({x["brand"] for x in self.be.all("SELECT brand FROM items")}, {"ANSU", "JK TYRE"})
        self.assertEqual(self.be.one("SELECT item_name FROM items WHERE item_code = 'TIR-0003'")["item_name"], "JK 900-20")  # names untouched
        r = self.c.post("/admin/classification", data={"kind": "brand", "old": "ANSU", "new": "ANSU TYRE"})
        self.assertIn("Renamed ANSU into ANSU TYRE", self.c.get(r.headers["Location"]).get_data(as_text=True))
        self.assertEqual(self.be.one("SELECT COUNT(*) AS n FROM audit_log WHERE action IN ('merge', 'rename')")["n"], 2)

    def test_pattern_rename_and_protected_na(self):
        self.login("owner")
        r = self.c.post("/admin/classification", data={"kind": "pattern", "old": "Rib", "new": "Lug"})
        self.assertIn("Merged Rib into Lug", self.c.get(r.headers["Location"]).get_data(as_text=True))
        self.assertEqual({x["pattern"] for x in self.be.all("SELECT pattern FROM items")}, {"Lug"})
        r = self.c.post("/admin/classification", data={"kind": "pattern", "old": "N/A", "new": "Plain"})
        self.assertIn("cannot be renamed", self.c.get(r.headers["Location"]).get_data(as_text=True))
        r = self.c.post("/admin/classification", data={"kind": "brand", "old": "NOPE", "new": "X"})
        self.assertIn("No item uses NOPE", self.c.get(r.headers["Location"]).get_data(as_text=True))

    def test_merge_that_creates_identical_items_warns(self):
        self.login("owner")
        self.be.execute("INSERT INTO items (item_code, item_name, brand, model, size, ply_rating, pattern, category) VALUES "
                        "('TIR-0009', 'ANSU TYRE 12R22.5 18PR AL505', 'ANSU TYRE', 'AL505', '12R22.5', '18PR', 'Rib', 'tire')")
        self.be.commit()
        r = self.c.post("/admin/classification", data={"kind": "brand", "old": "ANSU TYRE", "new": "ansu"})
        page = self.c.get(r.headers["Location"]).get_data(as_text=True)
        self.assertIn("Merged ANSU TYRE into ANSU (1 item)", page)
        self.assertIn("exactly the same specs", page)

    def test_only_owner(self):
        for who in ("whmgr", "shopmgr", "shopstaff"):
            self.login(who)
            self.assertEqual(self.c.get("/admin/classification").status_code, 403, who)
            self.assertEqual(self.c.post("/admin/classification", data={}).status_code, 403, who)


class ReportTests(Base):
    def test_every_report_loads_and_downloads_csv(self):
        self.sell(6)
        self.login("owner")
        for name in ("stock", "reorder", "movements", "sales", "adjustments"):
            self.assertEqual(self.c.get("/reports/%s" % name).status_code, 200, name)
            r = self.c.get("/reports/%s?format=csv" % name)
            self.assertEqual(r.status_code, 200, name)
            self.assertIn("text/csv", r.headers["Content-Type"])
            self.assertIn("attachment", r.headers["Content-Disposition"])
        self.assertEqual(self.c.get("/reports/nope").status_code, 404)
        self.assertEqual(self.c.get("/reports").status_code, 200)

    def test_report_contents(self):
        self.sell(6)                                                    # shop A: 10 -> 4, at/below ROP 5
        self.login("owner")
        csv_text = self.c.get("/reports/reorder?format=csv").get_data(as_text=True)
        self.assertTrue(csv_text.startswith("\ufeffitem_code,item_name,location"))
        self.assertIn("TIR-0001,ANSU 12R22.5 18PR AL505,SHOP,4,0,4,5,20,16,3", csv_text)
        stock = self.c.get("/reports/stock?location=2&q=ansu").get_data(as_text=True)
        self.assertIn("Below ROP", stock)
        sales = self.c.get("/reports/sales?date_from=2026-10-01&date_to=2026-10-31&location=2").get_data(as_text=True)
        self.assertIn("ISS-2026-0001", sales)
        self.assertNotIn("ISS-2026-0001", self.c.get("/reports/sales?date_from=2026-09-01&date_to=2026-09-30").get_data(as_text=True))
        mov = self.c.get("/reports/movements?date_from=2000-01-01&date_to=2999-01-01&q=al505").get_data(as_text=True)
        self.assertIn("issue", mov)

    def test_only_owner_sees_reports(self):
        for who in ("shopmgr", "whmgr", "shopstaff", "whstaff"):
            self.login(who)
            self.assertEqual(self.c.get("/reports").status_code, 403, who)
            self.assertEqual(self.c.get("/reports/stock").status_code, 403, who)


if __name__ == "__main__":
    unittest.main()
