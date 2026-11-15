"""Build app/loss/curves.yaml from FEMA's Hazus 6.1 flood structure damage functions.

    python -m app.loss.build_curves

Source: FEMA Hazus team extract `HazusFloodDamageFunctions_Hazus61.xlsx`, structural sheet as published in
NHERI SimCenter's Damage and Loss Model Library (data_sources/flood/building/portfolio/Hazus v6.1/input_files/
HazusFloodDamageFunctions_Hazus61_structural.csv). Cached at data/cache/public/hazus/.
Depth is water depth above the first finished floor in feet, the same reference as the Waterline slider.
For each occupancy: the Hazus default function is recorded, and the low-high range is the 25th-75th percentile
across the USACE Galveston district functions for that occupancy (the district that covers Houston).
"""
import csv

import httpx
import numpy as np
import yaml

from app.config import CACHE, ROOT

URL = ("https://raw.githubusercontent.com/NHERI-SimCenter/DamageAndLossModelLibrary/main/data_sources/flood/"
       "building/portfolio/Hazus%20v6.1/input_files/HazusFloodDamageFunctions_Hazus61_structural.csv")
SRC = CACHE / "public" / "hazus" / "HazusFloodDamageFunctions_Hazus61_structural.csv"
# Contents and inventory sheets, same folder: used only for the standard-method comparison (contracts v1.3), never in
# Waterline's own loss.
OTHER = {kind: (URL.replace("_structural.csv", f"_{kind}.csv"),
                CACHE / "public" / "hazus" / f"HazusFloodDamageFunctions_Hazus61_{kind}.csv") for kind in ("contents", "inventory")}
OUT = ROOT / "backend" / "app" / "loss" / "curves.yaml"
DEPTHS = list(range(0, 9))
COLS = [f"ft{d:02d}" for d in DEPTHS]
OCCUPANCIES = {"COM1": "Retail trade", "COM2": "Wholesale trade (warehouse)", "IND2": "Light industrial"}
MAPPING = {   # Waterline building -> Hazus occupancy
    "GeneralRetail": "COM1",
    "Industrial_Warehouse": "COM2", "Industrial_Distribution": "COM2", "Industrial_TruckTerminal": "COM2",
    "Industrial": "IND2", "Flex": "IND2",
}


def main() -> None:
    if not SRC.exists():
        SRC.parent.mkdir(parents=True, exist_ok=True)
        SRC.write_bytes(httpx.get(URL, timeout=120, follow_redirects=True).content)
    rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
    curves = {}
    for occ, name in OCCUPANCIES.items():
        mine = [r for r in rows if r["Occupancy"].strip() == occ]
        default = next(r for r in mine if r["Default"].strip() == "1")
        local = np.array([[float(r[c]) for c in COLS] for r in mine if r["Source"].strip() == "USACE - Galveston"])
        lo = np.minimum(np.percentile(local, 25, axis=0), [float(default[c]) for c in COLS])
        hi = np.maximum(np.percentile(local, 75, axis=0), [float(default[c]) for c in COLS])
        curves[occ] = {
            "name": name,
            "id": f"C-HAZUS-{occ}",
            "default_function_id": int(default["BldgDmgFnID"]),
            "default_description": default["Description"].strip(),
            "default_source": default["Source"].strip(),
            "depth_ft": DEPTHS,
            "default_pct": [round(float(default[c]), 1) for c in COLS],
            "low_pct": [round(float(x), 1) for x in lo],
            "high_pct": [round(float(x), 1) for x in hi],
            "range_basis": f"25th-75th percentile of {len(local)} USACE Galveston Hazus 6.1 structure functions for {occ}, widened to include the default",
        }
    standard = {}
    for kind, (url, path) in OTHER.items():
        if not path.exists():
            path.write_bytes(httpx.get(url, timeout=120, follow_redirects=True).content)
        other = list(csv.DictReader(open(path, encoding="utf-8-sig")))
        for occ in OCCUPANCIES:
            d = next(r for r in other if r["Occupancy"].strip() == occ and r["Default"].strip() == "1")
            standard.setdefault(occ, {})[kind] = {
                "function_id": int(list(d.values())[0]), "description": d["Description"].strip(),
                "source": d["Source"].strip(), "depth_ft": DEPTHS, "pct": [round(float(d[c]), 1) for c in COLS]}
    doc = {
        "source": "FEMA Hazus 6.1 flood structure damage functions (HazusFloodDamageFunctions_Hazus61.xlsx, FEMA Hazus team extract), "
                  "structural sheet as published in NHERI SimCenter Damage and Loss Model Library",
        "source_url": URL,
        "depth_reference": "water depth above first finished floor, ft (Hazus); same as the Waterline slider",
        "zero_depth_rule": "depth 0 means no water inside, so damage is 0 (the Hazus ft00 value applies just above 0)",
        "mapping": MAPPING,
        "curves": curves,
        "standard_contents": {
            "use": "Standard-method comparison only (contracts v1.3): the Hazus 6.1 default contents and inventory "
                   "functions for the occupancy, applied to the same item values as Waterline's own contents loss.",
            "source": "FEMA Hazus 6.1 flood contents and inventory damage functions (HazusFloodDamageFunctions_Hazus61.xlsx), "
                      "contents and inventory sheets as published in NHERI SimCenter Damage and Loss Model Library",
            "source_url": URL.replace("_structural.csv", "_{contents,inventory}.csv"),
            "occupancies": standard},
    }
    OUT.write_text("# Generated by `python -m app.loss.build_curves`. Do not edit by hand.\n" + yaml.safe_dump(doc, sort_keys=False, width=140))
    for occ, c in curves.items():
        print(occ, "default", c["default_pct"], "| low", c["low_pct"], "| high", c["high_pct"])
    for occ, k in standard.items():
        print(occ, {kind: (v["function_id"], v["pct"]) for kind, v in k.items()})


if __name__ == "__main__":
    main()
