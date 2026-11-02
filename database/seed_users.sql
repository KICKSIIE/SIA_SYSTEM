-- DEMO USERS for development only. Password for all of them: changeme
-- Run AFTER schema.sql and seed_items.sql. Delete before going live.
BEGIN;

-- DEMO locations, only created if you do not have a warehouse / shop yet. Rename them in the app later.
INSERT INTO locations (code, name, loc_type)
SELECT 'WH', 'Warehouse', 'warehouse' WHERE NOT EXISTS (SELECT 1 FROM locations WHERE loc_type = 'warehouse');
INSERT INTO locations (code, name, loc_type)
SELECT 'SHOP', 'Shop', 'shop' WHERE NOT EXISTS (SELECT 1 FROM locations WHERE loc_type = 'shop');

INSERT INTO users (username, full_name, password_hash, role_id, location_id) VALUES ('owner', 'Demo Owner', 'scrypt:32768:8:1$hp9pOIsWBBL3VasA$38b61ef1145982d71386b5113b556c879d688231fb62f04067e2be1cc63dcef1946fdd40c2f82a584d79c343d538f1d31a51c008e64fda457be6731ddc1c9f0e', (SELECT id FROM roles WHERE code = 'owner'), NULL);
INSERT INTO users (username, full_name, password_hash, role_id, location_id) VALUES ('whmgr', 'Demo Warehouse Manager', 'scrypt:32768:8:1$hp9pOIsWBBL3VasA$38b61ef1145982d71386b5113b556c879d688231fb62f04067e2be1cc63dcef1946fdd40c2f82a584d79c343d538f1d31a51c008e64fda457be6731ddc1c9f0e', (SELECT id FROM roles WHERE code = 'warehouse_manager'), (SELECT id FROM locations WHERE loc_type = 'warehouse' ORDER BY id LIMIT 1));
INSERT INTO users (username, full_name, password_hash, role_id, location_id) VALUES ('whstaff', 'Demo Warehouse Staff', 'scrypt:32768:8:1$hp9pOIsWBBL3VasA$38b61ef1145982d71386b5113b556c879d688231fb62f04067e2be1cc63dcef1946fdd40c2f82a584d79c343d538f1d31a51c008e64fda457be6731ddc1c9f0e', (SELECT id FROM roles WHERE code = 'warehouse_staff'), (SELECT id FROM locations WHERE loc_type = 'warehouse' ORDER BY id LIMIT 1));
INSERT INTO users (username, full_name, password_hash, role_id, location_id) VALUES ('shopmgr', 'Demo Shop Manager', 'scrypt:32768:8:1$hp9pOIsWBBL3VasA$38b61ef1145982d71386b5113b556c879d688231fb62f04067e2be1cc63dcef1946fdd40c2f82a584d79c343d538f1d31a51c008e64fda457be6731ddc1c9f0e', (SELECT id FROM roles WHERE code = 'shop_manager'), (SELECT id FROM locations WHERE loc_type = 'shop' ORDER BY id LIMIT 1));
INSERT INTO users (username, full_name, password_hash, role_id, location_id) VALUES ('shopstaff', 'Demo Shop Staff', 'scrypt:32768:8:1$hp9pOIsWBBL3VasA$38b61ef1145982d71386b5113b556c879d688231fb62f04067e2be1cc63dcef1946fdd40c2f82a584d79c343d538f1d31a51c008e64fda457be6731ddc1c9f0e', (SELECT id FROM roles WHERE code = 'shop_staff'), (SELECT id FROM locations WHERE loc_type = 'shop' ORDER BY id LIMIT 1));

COMMIT;
