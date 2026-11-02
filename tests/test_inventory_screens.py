"""Click-through tests for the Inventory screens, as each role.

Run:  python -m unittest discover tests -v
Uses an in-memory SQLite copy of the tables (no PostgreSQL needed). Still run the
screens against PostgreSQL by hand once, SQLite is close but not identical.
"""
import os, re, sys
sys.path.insert(0, os.path.dirname(__file__))
import unittest

from app import create_app
from app import inventory_service as inv
from sqlite_schema import SqliteBackend

TIRE_A, TIRE_B = 1, 2


class ScreenTests(unittest.TestCase):
    def setUp(self):
        self.be = SqliteBackend()
        inv.set_backend(self.be)
        inv._backend_supports_locking = False
        b = self.be
        for code in ("owner", "shop_manager", "shop_staff", "warehouse_manager", "warehouse_staff"):
            b.execute("INSERT INTO roles (code, name) VALUES (:c, :c)", c=code)
        b.execute("INSERT INTO locations (code, name, loc_type) VALUES ('B1', 'Branch 1', 'warehouse')")
        b.execute("INSERT INTO locations (code, name, loc_type) VALUES ('B2', 'Branch 2', 'shop')")
        users = [("owner", "owner", None), ("whmgr", "warehouse_manager", 1), ("whstaff", "warehouse_staff", 1),
                 ("shopmgr", "shop_manager", 2), ("shopstaff", "shop_staff", 2)]
        self.uid = {}
        for name, role, loc in users:
            b.execute("INSERT INTO users (username, full_name, role_id, location_id) VALUES (:u, :u, "
                      "(SELECT id FROM roles WHERE code = :r), :l)", u=name, r=role, l=loc)
            self.uid[name] = b.one("SELECT id FROM users WHERE username = :u", u=name)["id"]
        b.execute("INSERT INTO items (item_code, item_name, brand) VALUES ('TIR-0001', 'ANSU 12R22.5 18PR AL505', 'ANSU')")
        b.execute("INSERT INTO items (item_code, item_name, brand) VALUES ('TIR-0002', 'RODEO 1200R20 20PR RT201', 'RODEO')")
        inv.change_stock(TIRE_A, 1, 10, "opening")      # warehouse has 10
        inv.change_stock(TIRE_A, 2, 10, "opening")      # shop has 10
        inv.change_stock(TIRE_B, 2, 4, "opening")
        b.commit()
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.c = self.app.test_client()

    def login(self, name):
        self.c.get("/dev/user/%d" % self.uid[name])

    def bal(self, item, loc):
        return inv.get_balance(item, loc)["on_hand"]

    def flashes(self, resp):
        return re.findall(r'class="flash [a-z]+">([^<]*)<', resp.get_data(as_text=True))

    # ---- sales / issues ----
    def test_sale_deducts_stock_and_writes_ledger(self):
        self.login("shopstaff")
        r = self.c.post("/inventory/issues/new", data={"issue_date": "2026-10-30", "reason": "sale",
                        "customer_name": "Walk-in", "item_id[]": [str(TIRE_A)], "qty[]": ["3"]})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.bal(TIRE_A, 2), 7)
        self.assertEqual(self.bal(TIRE_A, 1), 10)                      # warehouse untouched
        led = self.be.one("SELECT * FROM stock_ledger WHERE movement_type = 'issue'")
        self.assertEqual((led["qty_change"], led["ref_type"]), (-3, "ISS"))
        page = self.c.get(r.headers["Location"]).get_data(as_text=True)
        self.assertIn("ISS-2026-0001", page)

    def test_oversell_is_rejected_and_nothing_is_saved(self):
        self.login("shopstaff")
        r = self.c.post("/inventory/issues/new", data={"issue_date": "2026-10-30", "reason": "sale",
                        "item_id[]": [str(TIRE_B)], "qty[]": ["5"]})
        self.assertEqual(r.status_code, 200)
        self.assertIn("Not enough stock", " ".join(self.flashes(r)))
        self.assertEqual(self.bal(TIRE_B, 2), 4)
        self.assertEqual(self.be.one("SELECT COUNT(*) AS n FROM stock_issues")["n"], 0)
        # the failed try must not burn a document number
        self.c.post("/inventory/issues/new", data={"issue_date": "2026-10-30", "reason": "sale",
                    "item_id[]": [str(TIRE_B)], "qty[]": ["1"]})
        self.assertEqual(self.be.one("SELECT issue_no FROM stock_issues")["issue_no"], "ISS-2026-0001")

    def test_reserved_stock_cannot_be_sold(self):
        inv.reserve(1, TIRE_A, 2, 8)
        self.be.commit()
        self.login("shopstaff")
        r = self.c.post("/inventory/issues/new", data={"issue_date": "2026-10-30", "reason": "sale",
                        "item_id[]": [str(TIRE_A)], "qty[]": ["3"]})
        self.assertIn("reserved", " ".join(self.flashes(r)))
        self.assertEqual(self.bal(TIRE_A, 2), 10)

    def test_same_item_twice_is_merged_and_form_validation(self):
        self.login("shopstaff")
        self.c.post("/inventory/issues/new", data={"issue_date": "2026-10-30", "reason": "sale",
                    "item_id[]": [str(TIRE_A), str(TIRE_A)], "qty[]": ["2", "3"]})
        self.assertEqual(self.bal(TIRE_A, 2), 5)
        for bad in ({"issue_date": "2999-01-01", "reason": "sale"}, {"issue_date": "2026-10-30", "reason": ""}):
            r = self.c.post("/inventory/issues/new", data=dict(bad, **{"item_id[]": [str(TIRE_A)], "qty[]": ["1"]}))
            self.assertEqual(r.status_code, 200)
        r = self.c.post("/inventory/issues/new", data={"issue_date": "2026-10-30", "reason": "sale",
                        "item_id[]": [str(TIRE_A)], "qty[]": ["0"]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.bal(TIRE_A, 2), 5)

    def test_shop_user_cannot_open_another_locations_issue(self):
        self.login("shopstaff")
        self.c.post("/inventory/issues/new", data={"issue_date": "2026-10-30", "reason": "sale",
                    "item_id[]": [str(TIRE_A)], "qty[]": ["1"]})
        self.be.execute("UPDATE users SET location_id = 1 WHERE username = 'shopmgr'")
        self.be.commit()
        self.login("shopmgr")
        self.assertEqual(self.c.get("/inventory/issues/1").status_code, 404)
        self.login("owner")
        self.assertEqual(self.c.get("/inventory/issues/1").status_code, 200)

    def test_warehouse_roles_cannot_record_sales(self):
        self.login("whstaff")
        self.assertEqual(self.c.get("/inventory/issues/new").status_code, 403)

    # ---- ROP ----
    def test_owner_sets_rop_and_validation(self):
        self.login("owner")
        form = {"location_id[]": ["1", "2"], "rop[]": ["5", "6"], "max_level[]": ["20", "30"], "lead_time_days[]": ["7", "3"]}
        r = self.c.post("/inventory/rop/1/edit", data=form)
        self.assertEqual(r.status_code, 302)
        row = self.be.one("SELECT * FROM item_location_settings WHERE item_id = 1 AND location_id = 2")
        self.assertEqual((row["rop"], row["max_level"], row["lead_time_days"]), (6, 30, 3))
        self.assertEqual(self.be.one("SELECT COUNT(*) AS n FROM audit_log WHERE table_name = 'item_location_settings'")["n"], 2)
        bad = dict(form, **{"max_level[]": ["20", "2"]})
        r = self.c.post("/inventory/rop/1/edit", data=bad)
        self.assertIn("Max level", " ".join(self.flashes(r)))
        self.assertEqual(self.be.one("SELECT max_level FROM item_location_settings WHERE item_id = 1 AND location_id = 2")["max_level"], 30)
        r = self.c.post("/inventory/rop/1/edit", data=dict(form, **{"rop[]": ["x", "6"]}))
        self.assertEqual(r.status_code, 200)

    def test_only_owner_opens_rop_screens(self):
        for who in ("shopmgr", "whmgr", "shopstaff", "whstaff"):
            self.login(who)
            self.assertEqual(self.c.get("/inventory/rop").status_code, 403, who)
            self.assertEqual(self.c.post("/inventory/rop/1/edit", data={}).status_code, 403, who)
        self.login("owner")
        self.assertEqual(self.c.get("/inventory/rop").status_code, 200)
        self.assertEqual(self.c.get("/inventory/rop?show=missing&q=ansu").status_code, 200)

    # ---- stock list ----
    def test_stock_list_is_scoped_by_location_and_status_filter(self):
        self.be.execute("INSERT INTO item_location_settings (item_id, location_id, rop, max_level) VALUES (2, 2, 5, 20)")
        self.be.commit()
        self.login("shopstaff")
        html = self.c.get("/inventory/stock").get_data(as_text=True)
        self.assertIn("ANSU 12R22.5", html)
        self.assertNotIn("<td>B1</td>", html)
        self.login("owner")
        html = self.c.get("/inventory/stock").get_data(as_text=True)
        self.assertIn("<td>B1</td>", html)
        below = self.c.get("/inventory/stock?status=below").get_data(as_text=True)
        self.assertIn("RODEO", below)                  # 4 on hand <= ROP 5
        self.assertNotIn("ANSU", below)
        card = self.c.get("/inventory/stock/1").get_data(as_text=True)
        self.assertIn("opening", card)

    def test_rack_shows_and_can_be_edited(self):
        self.be.execute("UPDATE items SET model = 'AL505', pattern = 'Rib' WHERE id = 1")
        self.be.commit()
        self.login("owner")
        form = {"location_id[]": ["1", "2"], "rop[]": ["5", "5"], "max_level[]": ["20", "20"],
                "lead_time_days[]": ["30", "3"], "rack[]": ["Rack C - Row 2", "Shop Rack 3 - Row 1"]}
        self.assertEqual(self.c.post("/inventory/rop/1/edit", data=form).status_code, 302)
        self.assertEqual(self.be.one("SELECT rack FROM item_location_settings WHERE item_id = 1 AND location_id = 2")["rack"],
                         "Shop Rack 3 - Row 1")
        r = self.c.post("/inventory/rop/1/edit", data=dict(form, **{"rack[]": ["x" * 31, ""]}))
        self.assertIn("Rack can be at most 30", " ".join(self.flashes(r)))
        self.assertIn("Shop Rack 3 - Row 1", self.c.get("/inventory/stock").get_data(as_text=True))
        card = self.c.get("/inventory/stock/1").get_data(as_text=True)
        self.assertIn("AL505", card)
        self.assertIn("Rack C - Row 2", card)

    # ---- adjustments ----
    def raise_adjustment(self, who, item=TIRE_A, actual="8"):
        self.login(who)
        r = self.c.post("/inventory/adjustments/new", data={"reason": "Damaged", "item_id[]": [str(item)],
                        "qty_actual[]": [actual], "item_remarks[]": ["2 cracked"]})
        self.assertEqual(r.status_code, 302, self.flashes(r))
        return int(r.headers["Location"].rstrip("/").split("/")[-1])

    def test_adjustment_waits_for_manager_then_changes_stock(self):
        adj = self.raise_adjustment("whstaff")
        self.assertEqual(self.bal(TIRE_A, 1), 10)                                  # nothing yet
        self.assertEqual(self.c.get("/inventory/adjustments/%d/review" % adj).status_code, 403)   # staff cannot
        self.login("shopmgr")                                                      # wrong location
        r = self.c.get("/inventory/adjustments/%d/review" % adj)
        self.assertEqual(r.status_code, 302)
        self.login("owner")                                                        # owner only notified
        self.assertEqual(self.c.get("/inventory/adjustments/%d/review" % adj).status_code, 302)
        self.login("whmgr")
        self.assertIn("Review and decide", self.c.get("/inventory/adjustments/%d" % adj).get_data(as_text=True))
        r = self.c.post("/inventory/adjustments/%d/review" % adj, data={"decision": "approve", "review_remarks": ""})
        self.assertIn("Remarks are required", " ".join(self.flashes(r)))
        r = self.c.post("/inventory/adjustments/%d/review" % adj, data={"decision": "approve", "review_remarks": "Counted, ok"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.bal(TIRE_A, 1), 8)
        led = self.be.one("SELECT * FROM stock_ledger WHERE movement_type = 'adjustment'")
        self.assertEqual((led["qty_change"], led["ref_type"]), (-2, "ADJ"))
        r = self.c.post("/inventory/adjustments/%d/review" % adj, data={"decision": "approve", "review_remarks": "again"})
        self.assertEqual(self.bal(TIRE_A, 1), 8)                                   # cannot apply twice

    def test_reject_leaves_stock_alone(self):
        adj = self.raise_adjustment("shopstaff")
        self.login("shopmgr")
        self.c.post("/inventory/adjustments/%d/review" % adj, data={"decision": "reject", "review_remarks": "Recount first"})
        self.assertEqual(self.bal(TIRE_A, 2), 10)
        self.assertEqual(self.be.one("SELECT status FROM stock_adjustments")["status"], "rejected")

    def test_nobody_approves_their_own_and_owner_covers_manager_requests(self):
        adj = self.raise_adjustment("whmgr")
        r = self.c.get("/inventory/adjustments/%d/review" % adj)
        self.assertEqual(r.status_code, 302)                                       # own request blocked
        self.login("owner")
        r = self.c.post("/inventory/adjustments/%d/review" % adj, data={"decision": "approve", "review_remarks": "ok"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.bal(TIRE_A, 1), 8)

    def test_adjustment_input_rules(self):
        self.login("whstaff")
        same = self.c.post("/inventory/adjustments/new", data={"reason": "Lost", "item_id[]": ["1"], "qty_actual[]": ["10"]})
        self.assertIn("nothing to adjust", " ".join(self.flashes(same)))
        self.assertEqual(self.be.one("SELECT COUNT(*) AS n FROM stock_adjustments")["n"], 0)
        inv.reserve(1, TIRE_A, 1, 6); self.be.commit()
        low = self.c.post("/inventory/adjustments/new", data={"reason": "Lost", "item_id[]": ["1"], "qty_actual[]": ["4"]})
        self.assertIn("reserved", " ".join(self.flashes(low)))
        noar = self.c.post("/inventory/adjustments/new", data={"reason": "Lost", "ar_no": "AR-NOPE", "item_id[]": ["1"], "qty_actual[]": ["8"]})
        self.assertIn("not found", " ".join(self.flashes(noar)))

    def test_shop_staff_adjustment_is_scoped_to_their_shop(self):
        adj = self.raise_adjustment("shopstaff", item=TIRE_B, actual="3")
        self.login("whmgr")
        self.assertEqual(self.c.get("/inventory/adjustments/%d" % adj).status_code, 404)
        self.login("owner")
        self.assertEqual(self.c.get("/inventory/adjustments/%d" % adj).status_code, 200)

    def test_opening_stock_from_zero_through_an_approved_adjustment(self):
        b = self.be
        b.execute("INSERT INTO items (item_code, item_name, brand) VALUES ('TIR-0003', 'NEW ITEM 11R22.5', 'NEW')")
        b.commit()
        adj = self.raise_adjustment("whstaff", item=3, actual="25")
        self.assertEqual(self.bal(3, 1), 0)
        self.login("whmgr")
        self.c.post("/inventory/adjustments/%d/review" % adj, data={"decision": "approve", "review_remarks": "Opening count"})
        self.assertEqual(self.bal(3, 1), 25)

    # ---- dashboards ----
    def test_every_role_dashboard_and_menu_page_renders(self):
        self.raise_adjustment("whstaff")
        for who in self.uid:
            self.login(who)
            self.assertEqual(self.c.get("/").status_code, 200, who)
            for url in ("/inventory/stock", "/inventory/adjustments", "/inventory/adjustments/new"):
                code = self.c.get(url).status_code
                self.assertIn(code, (200, 403), (who, url))
        self.login("whmgr")
        self.assertIn("Warehouse adjustments to approve: 1", self.c.get("/").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
