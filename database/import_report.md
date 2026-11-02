# Excel import report

Source: `INVENTORY__1_.xlsx` (item names only; stock, dates and customers are ignored).

| | |
|---|---|
| Unique items | 416 (367 tire, 13 other, 28 tube, 8 flap) |
| Pattern found in the name | 147 |
| Pattern MADE UP (name had none) | 220 |
| Demo stock rows (item x location) | 634 |

## How it was decided

- Items are classified by their specs only: category, brand, model, size, ply and pattern. There is no vehicle type.
- Pattern is the tread type. If the name has a tread word (RIB, LUG, MIX, SOLID, LOADER...) it is used. Otherwise one is made up from the size (small metric sizes get All-Season / Touring, truck sizes get Rib / Lug / Mixed, very large sizes get Farm / Loader / Rock). Tubes, flaps and rims get `N/A`.
- Model is what is left of the name after size, ply and tread word (for example `BY616`).
- Ply is only what the name says. Nothing is made up for it.
- Item codes are generated (TIR-0001, TUB-0001, FLP-0001, OTH-0001). The client has no codes of their own.
- Demo racks are grouped by rim size: A up to 16 in, B 17 to 19.5, C 20 to 22.5, D 23 and up, E tubes and flaps, F rims.
- Item names are kept exactly as the client wrote them. Obvious brand typos are fixed in the brand column only.
- Unit price is not stored: this system has no prices.

## Names that needed a manual fix before reading (7)

- `ANSU 9.5R/7.5 18PR BY996 LUG`: size looks mistyped, read as 9.5R17.5
- `CEAT 750-16PR MILE XL LUG`: '16PR' glued to the size, ply unknown
- `EMRALD 8.15/28X9 15 EMPOWER SOLID`: size read as 28X9-15
- `JK TYRE 16/70-20 405/70-20 14PR TUFF GRIP MPTTL`: two sizes, kept the first
- `O-RING JK 05-2021`: not a tire size (looks like a date), treated as an accessory
- `TRIANGLE 1400R 25/385/95R 25 TB586`: two sizes, kept 1400R25
- `WHEEL RIM 75-20 10 HOLES 16MM`: size looks mistyped, read as 7.5-20

## Tires whose size could not be read (0). Please check

None.
