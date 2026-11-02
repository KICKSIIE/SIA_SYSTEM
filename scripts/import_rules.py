"""All the rules for turning an item NAME into columns (brand, model, size, ply, pattern, category), and for making demo data.

Everything here is a rule of thumb, not tire-industry fact. Change a rule here and re-run
scripts/import_excel.py to rebuild the SQL.
"""
import random
import re
import zlib

CODE_PREFIX = {"tire": "TIR", "tube": "TUB", "flap": "FLP", "other": "OTH"}

# Names the reader cannot cut correctly as written. Only the text used for READING is replaced,
# the item name itself stays as the client typed it.
NAME_FIXES = {
    "ANSU 9.5R/7.5 18PR BY996 LUG": ("ANSU 9.5R17.5 18PR BY996 LUG", "size looks mistyped, read as 9.5R17.5"),
    "CEAT 750-16PR MILE XL LUG": ("CEAT 750-16 MILE XL LUG", "'16PR' glued to the size, ply unknown"),
    "EMRALD 8.15/28X9 15 EMPOWER SOLID": ("EMRALD 28X9-15 EMPOWER SOLID", "size read as 28X9-15"),
    "JK TYRE 16/70-20 405/70-20 14PR TUFF GRIP MPTTL": ("JK TYRE 16/70-20 14PR TUFF GRIP MPTTL", "two sizes, kept the first"),
    "TRIANGLE 1400R 25/385/95R 25 TB586": ("TRIANGLE 1400R25 TB586", "two sizes, kept 1400R25"),
    "WHEEL RIM 75-20 10 HOLES 16MM": ("WHEEL RIM 7.5-20 10 HOLES 16MM", "size looks mistyped, read as 7.5-20"),
    "O-RING JK 05-2021": ("JK O-RING", "not a tire size (looks like a date), treated as an accessory"),
}
BRAND_FIXES = {"JK": "JK TYRE", "DUOBLE COIN": "DOUBLE COIN", "CHALLENGE": "CHALLENGER", "U-T TUBE": "U-T"}

TREAD_WORDS = [  # (word in name, pattern). First match in the name wins.
    ("RIB", "Rib"), ("MLUG", "Lug"), ("LUG", "Lug"), ("MIX", "Mixed"), ("SOLID", "Solid"),
    ("FORKLIFT", "Forklift"), ("LOADER", "Loader (L3)"), ("ROCK", "Rock (E3/L4)"),
    ("FARM", "Farm (R-1)"), ("FARMAX", "Farm (R-1)"), ("AGRI", "Farm (R-1)"), ("TRACTOR", "Farm (R-1)"),
    ("R1", "Farm (R-1)"), ("AT", "All-Terrain"),
]
DROP_FROM_MODEL = {"TL", "TT", "TUBELESS", "TUBETYPE", "R1", "XL"}
RIM_TOKEN = re.compile(r"^\d+(\.\d+)?C?$")


def clean_name(v):
    return re.sub(r"\s+", " ", str(v)).strip() if v is not None else ""


def category_of(sheet, name):
    s = sheet.upper()
    if s.endswith("TUBES"):
        return "tube"
    if s.endswith("FLAPS"):
        return "flap"
    if name.upper().startswith("WHEEL RIM") or name.upper().endswith("O-RING"):
        return "other"
    return "tire"


def _glue(words):
    """'235/70R 15' -> '235/70R15', '295/80R22.518PR' -> '295/80R22.5', '18PR'."""
    out, i = [], 0
    while i < len(words):
        w = words[i]
        m = re.fullmatch(r"(.*R\d+\.5)(\d{1,2}PR)", w, flags=re.I)
        if m:
            out += [m.group(1), m.group(2)]
        elif re.search(r"\dR$", w, flags=re.I) and i + 1 < len(words) and RIM_TOKEN.match(words[i + 1]):
            out.append(w + words[i + 1])
            i += 1
        else:
            out.append(w)
        i += 1
    return out


def parse_item(name, sheet=""):
    read_as, note = NAME_FIXES.get(name, (name, None))
    category = category_of(sheet, read_as)
    words = _glue(read_as.split())
    # brand = words before the first word that has a digit
    first = next((i for i, w in enumerate(words) if re.search(r"\d", w)), None)
    if first is None:
        brand_words, rest = words[:-1] or words, words[-1:] if len(words) > 1 else []
        if read_as.upper().endswith("O-RING"):
            brand_words, rest = ["JK"], []
    else:
        brand_words, rest = words[:first], words[first:]
    brand = " ".join(w for w in brand_words if w.upper() not in ("TUBES", "FLAPS", "TUBE", "FLAP")) or "UNKNOWN"
    brand = BRAND_FIXES.get(brand.upper(), brand)

    size = ply = None
    if rest:
        size = rest[0]
        rest = rest[1:]
    # a second "size-like" or ply token
    ply_i = next((i for i, w in enumerate(rest) if re.fullmatch(r"\d+PR", w, flags=re.I)), None)
    if ply_i is not None:
        ply = rest[ply_i].upper()
        rest = rest[:ply_i] + rest[ply_i + 1:]
    # tread word
    pattern, made_up = None, False
    upper_rest = [w.upper() for w in rest]
    if category == "tire":
        for word, label in TREAD_WORDS:
            if word in upper_rest:
                pattern = label
                break
    model_words = [w for w in rest if w.upper() not in DROP_FROM_MODEL and not (pattern and any(
        w.upper() == tw and lab == pattern for tw, lab in TREAD_WORDS))]
    model = " ".join(model_words)[:40] or None

    if size and size.upper().startswith("TYRE"):
        size = size[4:]
    if category != "tire":
        pattern = "N/A"
    elif pattern is None:
        pattern, made_up = made_up_pattern(name, size), True
    return {"name": name, "brand": brand[:50], "model": model, "size": (size or None) and size[:30], "ply": ply,
            "pattern": pattern, "pattern_made_up": made_up, "category": category,
            "rim": rim_inches(size, category), "parse_note": note}


def rim_inches(size, category="tire"):
    """Rim diameter in inches read from the size, or None. This is a SPEC, nothing is stored about vehicles."""
    s = (size or "").upper().replace(" ", "")
    if not s:
        return None
    if category == "other":                       # wheel rims: use the diameter (the larger number)
        nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", s)]
        return max(nums) if nums else None
    m = re.fullmatch(r"\d{3}/\d{2,3}R(\d{2}(?:\.5)?)C?", s)
    if m:
        return float(m.group(1))
    found = re.findall(r"[-RX](\d+(?:\.\d+)?)", s)
    return float(found[-1]) if found else None


def band(rim):
    """Size group used ONLY to shape the demo data and racks: 1 = up to 16 in, 2 = 17 to 19.5, 3 = 20 to 22.5, 4 = 23 and up."""
    if rim is None:
        return 3
    return 1 if rim <= 16 else 2 if rim < 20 else 3 if rim < 23 else 4


def _pick(name, options):
    return options[zlib.crc32(name.encode()) % len(options)]


def made_up_pattern(name, size):
    """Tread pattern invented from the size alone, when the name has none."""
    s = (size or "").upper().replace(" ", "")
    rim = rim_inches(size)
    metric = re.fullmatch(r"\d{3}/\d{2,3}R\d{2}(?:\.5)?C?", s) is not None
    b = band(rim)
    if metric and rim is not None and rim <= 18 and not s.endswith("C"):
        return _pick(name, ["All-Season", "Touring", "Highway Terrain"])
    if b == 1:
        return _pick(name, ["Rib", "Highway Terrain", "Mixed"] if s.endswith("C") else ["Rib", "Lug", "Mixed"])
    if b == 4:
        farm = re.search(r"-(2[4-9]|3\d)$", s) and not re.match(r"^(1[4-9]\d{2}|2\d{3}|\d{2}\.5)", s)
        return "Farm (R-1)" if farm else _pick(name, ["Loader (L3)", "Rock (E3/L4)"])
    return _pick(name, ["Rib", "Lug", "Mixed"])


# ------------------------------------------------------------------ demo data (made up, by size group)

ZONE = {1: "A", 2: "B", 3: "C", 4: "D"}                  # warehouse racks by rim size group
STOCK_RANGE = {1: (8, 35), 2: (6, 30), 3: (4, 30), 4: (1, 10)}
ROP_RANGE = {1: (4, 8), 2: (4, 8), 3: (3, 8), 4: (1, 3)}
SHOP_CARRIES = {1: 0.85, 2: 0.7, 3: 0.5, 4: 0.15}
FIXED_STOCK = {"tube": ((10, 50), (6, 12), 0.6, "E"), "flap": ((10, 50), (6, 12), 0.5, "E"),
               "other": ((3, 15), (2, 4), 0.3, "F")}


def demo_row(item, kind):
    """Made-up stock, ROP, lead time and rack for one item in the warehouse or the shop. None = not stocked here."""
    rng = random.Random("%s-%s" % (item["code"], kind))
    cat = item["category"]
    if cat in FIXED_STOCK:
        (lo, hi), (rlo, rhi), shop_p, zone = FIXED_STOCK[cat]
        shop_rack = 5 if cat != "other" else 6
    else:
        b = band(item["rim"])
        (lo, hi), (rlo, rhi), shop_p, zone = STOCK_RANGE[b], ROP_RANGE[b], SHOP_CARRIES[b], ZONE[b]
        shop_rack = b
    row_no = 1 + zlib.crc32(item["name"].encode()) % 6
    if kind == "shop":
        if rng.random() > shop_p:
            return None
        rop = rng.randint(rlo, rhi)
        qty, lead = rng.randint(lo, hi), rng.randint(2, 4)
        rack = "Shop Rack %d - Row %d" % (shop_rack, 1 + row_no % 4)
        max_level = rop * 3
    else:
        rop = max(1, round(rng.randint(rlo, rhi) * 1.5))
        qty, lead = round(rng.randint(lo, hi) * rng.uniform(1.5, 2.5)), rng.randint(21, 45)
        rack = "Rack %s - Row %d" % (zone, row_no)
        max_level = rop * 4
    if rng.random() < 0.12:                       # some rows deliberately at or below ROP, a few at zero
        qty = 0 if rng.random() < 0.25 else rng.randint(1, max(1, rop))
    else:
        qty = max(qty, rop + 1)
    return {"qty": qty, "rop": rop, "max_level": max(max_level, rop), "lead_time": lead, "rack": rack}
