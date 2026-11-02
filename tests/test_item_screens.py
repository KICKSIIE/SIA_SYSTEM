"""Tests for the item list and the Add / Edit Item screens."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from app import create_app
from app import inventory_service as inv
from sqlite_schema import SqliteBackend


class ItemScreenTests(unittest.TestCase):
    def setUp(self):
        self.be = SqliteBackend()
        inv.set_backend(self.be)
        inv._backend_supports_locking = False
        b = self.be
        for code in ("owner", "warehouse_manager", "shop_staff"):
            b.execute("INSERT INTO roles (code, name) VALUES (:c, :c)", c=code)
        b.execute("INSERT INTO locations (code, name, loc_type) VALUES ('WH', 'Warehouse', 'warehouse')")
        for name, role, loc in (("owner", "owner", None), ("whmgr", "warehouse_manager", 1), ("shopstaff", "shop_staff", 1)):
            b.execute("INSERT INTO users (username, full_name, role_id, location_id) VALUES (:u, :u, "
                      "(SELECT id FROM roles WHERE code = :r), :l)", u=name, r=role, l=loc)
        self.uid = {r["username"]: r["id"] for r in b.all("SELECT id, username FROM users")}
        b.execute("INSERT INTO items (item_code, item_name, brand, model, size, ply_rating, pattern, category) VALUES "
                  "('TIR-0001', 'ANSU 215/75R17.5 18PR BY616 RIB', 'ANSU', 'BY616', '215/75R17.5', '18PR', 'Rib', 'tire')")
        b.execute("INSERT INTO items (item_code, item_name, brand, model, size, ply_rating, pattern, category) VALUES "
                  "('TIR-0002', 'JK TYRE 1200-20 18PR JETWAY', 'JK TYRE', 'JETWAY', '1200-20', '18PR', 'Lug', 'tire')")
        b.execute("INSERT INTO items (item_code, item_name, brand, size, pattern, category) VALUES "
                  "('TUB-0001', 'JK TYRE TUBES 1200-20', 'JK TYRE', '1200-20', 'N/A', 'tube')")
        b.commit()
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.c = self.app.test_client()
        self.login("owner")

    def login(self, name):
        self.c.get("/dev/user/%d" % self.uid[name])

    def item(self, code):
        return self.be.one("SELECT * FROM items WHERE item_code = :c", c=code)

    def new(self, **over):
        data = {"category": "tire", "brand": "ansu", "model": "al505", "size": "12r22.5", "ply_rating": "18",
                "pattern": "rib", "item_name": "", "item_code": ""}
        data.update(over)
        return self.c.post("/admin/items/new", data=data)

    def test_add_item_generates_code_and_name_and_matches_existing_spelling(self):
        r = self.new()
        self.assertEqual(r.status_code, 302)
        it = self.item("TIR-0003")
        self.assertEqual((it["item_name"], it["brand"], it["ply_rating"], it["pattern"], it["size"]),
                         ("ANSU 12R22.5 18PR AL505", "ANSU", "18PR", "Rib", "12R22.5"))
        self.assertEqual(self.be.one("SELECT COUNT(*) AS n FROM audit_log WHERE table_name = 'items'")["n"], 1)

    def test_tube_gets_na_pattern_and_tubes_word_in_name(self):
        self.new(category="tube", brand="jk tyre", size="900-20", ply_rating="", model="", pattern="")
        it = self.item("TUB-0002")
        self.assertEqual((it["item_name"], it["pattern"], it["brand"]), ("JK TYRE TUBES 900-20", "N/A", "JK TYRE"))

    def test_validation(self):
        for bad, expect in ((dict(brand=""), "Brand is required"), (dict(size=""), "Size is required"),
                            (dict(pattern=""), "Pattern is required"), (dict(ply_rating="18X"), "Ply rating"),
                            (dict(category=""), "Select a category"), (dict(item_code="a b"), "Item code")):
            r = self.new(**bad)
            self.assertEqual(r.status_code, 200)
            self.assertIn(expect, r.get_data(as_text=True))
        self.assertEqual(self.be.one("SELECT COUNT(*) AS n FROM items")["n"], 3)

    def test_duplicates_are_refused(self):
        r = self.new(brand="ansu", model="by616", size="215/75R17.5", ply_rating="18PR", pattern="RIB")
        self.assertIn("exactly these specs", r.get_data(as_text=True))
        r = self.new(item_name="ansu 215/75r17.5 18pr by616 rib", model="OTHER")
        self.assertIn("already exists", r.get_data(as_text=True))
        r = self.new(item_code="tir-0001", model="NEW1")
        self.assertIn("already used", r.get_data(as_text=True))

    def test_new_brand_and_pattern_are_added_with_a_notice(self):
        r = self.new(brand="Newbrand", pattern="Mud Special")
        self.assertEqual(r.status_code, 302)
        page = self.c.get("/admin/items/new").get_data(as_text=True)
        self.assertIn('value="NEWBRAND"', page)
        self.assertIn('value="Mud Special"', page)

    def test_edit_changes_item_and_keeps_code(self):
        r = self.c.post("/admin/items/1/edit", data={"category": "tire", "brand": "ansu", "model": "BY616X", "size": "215/75R17.5",
                        "ply_rating": "20PR", "pattern": "Rib", "item_name": "ANSU 215/75R17.5 20PR BY616X RIB", "is_active": "on"})
        self.assertEqual(r.status_code, 302)
        it = self.item("TIR-0001")
        self.assertEqual((it["ply_rating"], it["model"], it["item_code"]), ("20PR", "BY616X", "TIR-0001"))
        row = self.be.one("SELECT old_values, new_values FROM audit_log WHERE action = 'update'")
        self.assertIn("20PR", row["new_values"])
        again = self.c.post("/admin/items/1/edit", data={"category": "tire", "brand": "ansu", "model": "BY616X", "size": "215/75R17.5",
                            "ply_rating": "20PR", "pattern": "Rib", "item_name": "ANSU 215/75R17.5 20PR BY616X RIB", "is_active": "on"})
        self.assertEqual(self.be.one("SELECT COUNT(*) AS n FROM audit_log WHERE action = 'update'")["n"], 1)   # no change, no audit

    def test_cannot_deactivate_item_with_stock(self):
        inv.change_stock(1, 1, 5, "opening")
        self.be.commit()
        form = {"category": "tire", "brand": "ANSU", "model": "BY616", "size": "215/75R17.5", "ply_rating": "18PR",
                "pattern": "Rib", "item_name": "ANSU 215/75R17.5 18PR BY616 RIB"}
        r = self.c.post("/admin/items/1/edit", data=form)                        # checkbox not sent = untick
        self.assertIn("5 units are still in stock", r.get_data(as_text=True))
        self.assertEqual(self.item("TIR-0001")["is_active"], 1)
        inv.change_stock(1, 1, -5, "adjustment")
        self.be.commit()
        self.assertEqual(self.c.post("/admin/items/1/edit", data=form).status_code, 302)
        self.assertEqual(self.item("TIR-0001")["is_active"], 0)
        self.assertNotIn("TIR-0001", self.c.get("/admin/items").get_data(as_text=True))          # hidden by default
        self.assertIn("TIR-0001", self.c.get("/admin/items?status=inactive").get_data(as_text=True))

    def test_list_filters_and_roles(self):
        page = self.c.get("/admin/items?q=jetway").get_data(as_text=True)
        self.assertIn("TIR-0002", page)
        self.assertNotIn("TIR-0001", page)
        self.assertIn("TUB-0001", self.c.get("/admin/items?category=tube").get_data(as_text=True))
        self.assertIn("TIR-0001", self.c.get("/admin/items?brand=ANSU").get_data(as_text=True))
        self.login("whmgr")                                                      # can view, cannot change
        page = self.c.get("/admin/items").get_data(as_text=True)
        self.assertEqual(self.c.get("/admin/items").status_code, 200)
        self.assertNotIn("/admin/items/new", page)
        self.assertEqual(self.c.get("/admin/items/new").status_code, 403)
        self.assertEqual(self.c.post("/admin/items/1/edit", data={}).status_code, 403)
        self.login("shopstaff")
        self.assertEqual(self.c.get("/admin/items").status_code, 403)

    def test_edit_unknown_item_is_404(self):
        self.assertEqual(self.c.get("/admin/items/999/edit").status_code, 404)


if __name__ == "__main__":
    unittest.main()
