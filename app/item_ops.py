"""Item master data: the list, and adding / editing items (owner).

Items are classified by their specs only: category, brand, model, size, ply and pattern.
Brand and pattern are "pick-lists" built from what the items already use, so a new product is
spelled the same way as the existing ones (JK TYRE and jk tyre become one brand). The owner can
still type a new brand or pattern; that is how the list grows.
"""
import re

from . import inventory_service as inv
from .inventory_service import InventoryError

PAGE_SIZE = 50
CATEGORIES = [("tire", "Tire"), ("tube", "Tube"), ("flap", "Flap"), ("other", "Other (rim, accessory)")]
CODE_PREFIX = {"tire": "TIR", "tube": "TUB", "flap": "FLP", "other": "OTH"}


def _b():
    return inv.backend()


def _squash(v):
    return re.sub(r"\s+", " ", (v or "").strip())


# ---------------------------------------------------------------- lists for the pick-lists

def brands():
    return [r["brand"] for r in _b().all("SELECT DISTINCT brand FROM items ORDER BY brand")]


def patterns():
    return [r["pattern"] for r in _b().all(
        "SELECT DISTINCT pattern FROM items WHERE pattern IS NOT NULL AND pattern <> 'N/A' ORDER BY pattern")]


def _canon(value, existing):
    """Use the spelling that already exists (any capitals). Returns (value, is_new)."""
    for e in existing:
        if e.lower() == value.lower():
            return e, False
    return value, True


# ---------------------------------------------------------------- reading

def list_items(q="", category="", brand="", status="active", page=1):
    where, p = "", {}
    if q.strip():
        where += (" AND (LOWER(i.item_name) LIKE :q OR LOWER(i.item_code) LIKE :q OR LOWER(i.brand) LIKE :q "
                  "OR LOWER(COALESCE(i.model, '')) LIKE :q)")
        p["q"] = "%" + q.strip().lower() + "%"
    if category:
        where += " AND i.category = :cat"
        p["cat"] = category
    if brand:
        where += " AND i.brand = :brand"
        p["brand"] = brand
    if status == "active":
        where += " AND i.is_active"
    elif status == "inactive":
        where += " AND NOT i.is_active"
    total = _b().one("SELECT COUNT(*) AS n FROM items i WHERE 1 = 1" + where, **p)["n"]
    pages = max(1, -(-total // PAGE_SIZE))
    page = min(max(1, page), pages)
    rows = _b().all(
        "SELECT i.id, i.item_code, i.item_name, i.category, i.brand, i.model, i.size, i.ply_rating, i.pattern, i.is_active, "
        "COALESCE((SELECT SUM(b.on_hand) FROM stock_balances b WHERE b.item_id = i.id), 0) AS on_hand "
        "FROM items i WHERE 1 = 1" + where + " ORDER BY i.item_name LIMIT %d OFFSET %d" % (PAGE_SIZE, (page - 1) * PAGE_SIZE), **p)
    return {"rows": rows, "total": total, "page": page, "pages": pages}


def get_item(item_id):
    return _b().one("SELECT * FROM items WHERE id = :i", i=item_id)


def total_on_hand(item_id):
    return _b().one("SELECT COALESCE(SUM(on_hand), 0) AS n FROM stock_balances WHERE item_id = :i", i=item_id)["n"]


# ---------------------------------------------------------------- checking the form

def _read(form):
    """Clean and validate the form. Returns (values, notes). Raises InventoryError with a clear message."""
    category = (form.get("category") or "").strip().lower()
    if category not in dict(CATEGORIES):
        raise InventoryError("Select a category.")
    brand_in = _squash(form.get("brand")).upper()
    if not brand_in:
        raise InventoryError("Brand is required.")
    brand, new_brand = _canon(brand_in, brands())
    size = _squash(form.get("size")).upper().replace(" ", "")
    if not size and category != "other":
        raise InventoryError("Size is required.")
    ply = _squash(form.get("ply_rating")).upper().replace(" ", "")
    if ply.isdigit():
        ply += "PR"
    if ply and not re.fullmatch(r"\d{1,2}PR", ply):
        raise InventoryError("Ply rating must look like 18PR (or just the number 18).")
    model = _squash(form.get("model")).upper()
    pattern_in = _squash(form.get("pattern"))
    new_pattern = False
    if category != "tire":
        pattern = "N/A"
    else:
        if not pattern_in:
            raise InventoryError("Pattern is required for tires (the tread type, for example Rib, Lug or Mixed).")
        pattern, new_pattern = _canon(pattern_in, patterns())
    for label, value, limit in (("Brand", brand, 50), ("Model", model, 40), ("Size", size, 30), ("Pattern", pattern, 40)):
        if len(value) > limit:
            raise InventoryError("%s can be at most %d characters." % (label, limit))
    name = _squash(form.get("item_name"))
    if not name:
        parts = [brand] + ([{"tube": "TUBES", "flap": "FLAPS"}[category]] if category in ("tube", "flap") else []) \
            + [size, ply, model]
        name = " ".join(p for p in parts if p).upper()
    if len(name) > 150:
        raise InventoryError("Item name can be at most 150 characters.")
    notes = []
    if new_brand:
        notes.append("New brand added: %s." % brand)
    if new_pattern:
        notes.append("New pattern added: %s." % pattern)
    return {"category": category, "brand": brand, "size": size or None, "ply_rating": ply or None,
            "model": model or None, "pattern": pattern, "item_name": name}, notes


def _spec_duplicate(v, exclude_id=None):
    row = _b().one(
        "SELECT id, item_code, item_name FROM items WHERE category = :c AND UPPER(brand) = :b "
        "AND UPPER(COALESCE(size, '')) = :s AND UPPER(COALESCE(ply_rating, '')) = :p "
        "AND UPPER(COALESCE(model, '')) = :m AND UPPER(COALESCE(pattern, '')) = :pt AND id <> :x",
        c=v["category"], b=v["brand"].upper(), s=(v["size"] or "").upper(), p=(v["ply_rating"] or "").upper(),
        m=(v["model"] or "").upper(), pt=(v["pattern"] or "").upper(), x=exclude_id or 0)
    return row


def _check_unique(v, exclude_id=None, check_specs=True):
    same = _b().one("SELECT item_code FROM items WHERE LOWER(item_name) = LOWER(:n) AND id <> :x",
                    n=v["item_name"], x=exclude_id or 0)
    if same:
        raise InventoryError("The name %s already exists (%s). Change the name or the specs." % (v["item_name"], same["item_code"]))
    if check_specs:
        dup = _spec_duplicate(v, exclude_id)
        if dup:
            raise InventoryError("An item with exactly these specs already exists: %s, %s. Add a model or pattern that tells them apart."
                                 % (dup["item_code"], dup["item_name"]))


# ---------------------------------------------------------------- saving

def next_code(category):
    prefix = CODE_PREFIX[category]
    highest = 0
    for r in _b().all("SELECT item_code FROM items WHERE item_code LIKE :p", p=prefix + "-%"):
        m = re.fullmatch(prefix + r"-(\d+)", r["item_code"])
        if m:
            highest = max(highest, int(m.group(1)))
    return "%s-%04d" % (prefix, highest + 1)


def create_item(form, user_id):
    """Returns (item_id, code, notes)."""
    v, notes = _read(form)
    _check_unique(v)
    code = _squash(form.get("item_code")).upper()
    if code:
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9-]{1,29}", code):
            raise InventoryError("Item code can only use letters, numbers and dashes (2 to 30 characters).")
        if _b().one("SELECT id FROM items WHERE item_code = :c", c=code):
            raise InventoryError("Item code %s is already used." % code)
    else:
        code = next_code(v["category"])
    row = _b().one(
        "INSERT INTO items (item_code, item_name, brand, model, size, ply_rating, pattern, category) "
        "VALUES (:code, :n, :b, :m, :s, :p, :pt, :c) RETURNING id",
        code=code, n=v["item_name"], b=v["brand"], m=v["model"], s=v["size"], p=v["ply_rating"], pt=v["pattern"], c=v["category"])
    inv.write_audit(user_id, "create", "items", row["id"], new=dict(v, item_code=code))
    return row["id"], code, notes


def update_item(item_id, form, user_id):
    """Returns (changed, notes). The item code never changes after the item is created."""
    old = get_item(item_id)
    if old is None:
        raise InventoryError("Item not found.")
    v, notes = _read(form)
    v["is_active"] = bool(form.get("is_active"))
    spec_cols = ("category", "brand", "size", "ply_rating", "model", "pattern")
    specs_changed = any((old[c] or None) != (v[c] or None) for c in spec_cols)
    _check_unique(v, exclude_id=item_id, check_specs=specs_changed)
    if not v["is_active"] and old["is_active"]:
        on_hand = total_on_hand(item_id)
        if on_hand > 0:
            raise InventoryError("Cannot deactivate: %d units are still in stock. Adjust the stock to zero first." % on_hand)
    old_vals = {c: old[c] for c in spec_cols + ("item_name",)}
    new_vals = {c: v[c] for c in spec_cols + ("item_name",)}
    changes = {c: new_vals[c] for c in new_vals if (old_vals[c] or None) != (new_vals[c] or None)}
    if bool(old["is_active"]) != v["is_active"]:
        old_vals["is_active"], changes["is_active"] = bool(old["is_active"]), v["is_active"]
    if not changes:
        return False, []
    _b().execute(
        "UPDATE items SET item_name = :n, brand = :b, model = :m, size = :s, ply_rating = :p, pattern = :pt, "
        "category = :c, is_active = :a WHERE id = :i",
        n=v["item_name"], b=v["brand"], m=v["model"], s=v["size"], p=v["ply_rating"], pt=v["pattern"],
        c=v["category"], a=v["is_active"], i=item_id)
    inv.write_audit(user_id, "update", "items", item_id, old={k: old[k] for k in changes}, new=changes)
    return True, notes


# ---------------------------------------------------------------- brands and patterns (rename / merge)

def classification():
    """Brands and patterns with the number of items using each (active and inactive)."""
    brands_ = _b().all("SELECT brand AS name, COUNT(*) AS n FROM items GROUP BY brand ORDER BY brand")
    patterns_ = _b().all("SELECT pattern AS name, COUNT(*) AS n FROM items WHERE pattern IS NOT NULL "
                         "GROUP BY pattern ORDER BY pattern")
    return {"brands": brands_, "patterns": patterns_}


def _same_spec_groups(column, value):
    return _b().one(
        "SELECT COUNT(*) AS n FROM (SELECT 1 FROM items WHERE " + column + " = :v GROUP BY category, "
        "UPPER(COALESCE(size, '')), UPPER(COALESCE(ply_rating, '')), UPPER(COALESCE(model, '')), "
        "UPPER(COALESCE(brand, '')), UPPER(COALESCE(pattern, '')) HAVING COUNT(*) > 1) x", v=value)["n"]


def rename_value(kind, old, new, user_id):
    """Rename a brand or pattern everywhere. If `new` is already in use the two are merged.
    Item names are not touched, they stay as the client typed them. Returns a message for the user."""
    if kind not in ("brand", "pattern"):
        raise InventoryError("Unknown list.")
    column, limit = ("brand", 50) if kind == "brand" else ("pattern", 40)
    old, new = _squash(old), _squash(new)
    if kind == "brand":
        new = new.upper()
    if not new:
        raise InventoryError("Type the new name.")
    if len(new) > limit:
        raise InventoryError("The %s can be at most %d characters." % (kind, limit))
    if kind == "pattern" and "N/A" in (old.upper(), new.upper()):
        raise InventoryError("N/A is used by the system for tubes, flaps and rims and cannot be renamed or merged.")
    n_old = _b().one("SELECT COUNT(*) AS n FROM items WHERE " + column + " = :v", v=old)["n"]
    if n_old == 0:
        raise InventoryError("No item uses %s." % old)
    existing = [r["name"] for r in classification()[kind + "s"]]
    target, merging = new, False
    for e in existing:
        if e.lower() == new.lower() and e != old:
            target, merging = e, True        # use the spelling that already exists
    if target == old:
        return "Nothing changed."
    _b().execute("UPDATE items SET " + column + " = :new WHERE " + column + " = :old", new=target, old=old)
    inv.write_audit(user_id, "merge" if merging else "rename", "items", None,
                    old={kind: old}, new={kind: target, "items": n_old})
    msg = "%s %s into %s (%d item%s)." % ("Merged" if merging else "Renamed", old, target, n_old, "" if n_old == 1 else "s")
    dup = _same_spec_groups(column, target)
    if dup:
        msg += " %d group(s) of items now have exactly the same specs. Check them in the item list." % dup
    return msg
