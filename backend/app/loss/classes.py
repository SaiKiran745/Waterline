"""Value classes (assumptions.yaml `assets`) assigned from the vision label, with no model calls.

Rules are tried in order and the first match wins; when none matches, the vision category decides.
Building fabric (outlets, switches, fixed cabinetry) is A-FIN; road vehicles are V-VEHICLE (movable, not contents).
"""
import re

from app.loss import model

_W = lambda *words: re.compile(r"\b(" + "|".join(words) + r")\b", re.I)

FABRIC = re.compile(r"\b(outlets?|receptacles?|switch(?!gear|board)\w*|sockets?|cover plates?|"
                    r"(kitchen |lower |base |built-in )cabinet\w*|casework|countertops?)\b", re.I)
NOT_ROAD = _W(r"fork ?lifts?", r"hand trucks?", r"pallet trucks?", r"golf carts?")
VEHICLE = _W(r"pickups?", r"pickup trucks?", r"trucks?", r"cars?", r"automobiles?", r"suvs?", r"vans?", r"vehicles?",
             r"trailers?", r"motorcycles?", r"boats?")

RULES: list[tuple[str, re.Pattern]] = [
    ("V-FORKLIFT", _W(r"fork ?lifts?", r"lift trucks?", r"reach trucks?")),
    ("V-AERIAL-LIFT", _W(r"boom lifts?", r"scissor lifts?", r"genie", r"cherry pickers?", r"man ?lifts?", r"aerial lifts?")),
    ("V-PALLET-JACK", _W(r"pallet jacks?", r"pallet trucks?", r"hand trucks?", r"dolly", r"dollies")),
    ("V-IT", _W(r"computers?", r"monitors?", r"desktops?", r"laptops?", r"printers?", r"servers?", r"server racks?",
                r"network\w*", r"routers?", r"ups", r"copiers?", r"televisions?", r"tvs?", r"displays?")),
    ("V-ELEC-GEAR", _W(r"panels?", r"panelboards?", r"subpanels?", r"switchgear", r"switchboards?", r"disconnects?",
                       r"transformers?", r"breakers?", r"chargers?", r"meters?", r"control box\w*", r"junction box\w*",
                       r"electrical cabinets?", r"power distribution")),
    ("V-HVAC", _W(r"air handlers?", r"air condition\w*", r"ac units?", r"a/c", r"condens\w+", r"water heaters?",
                  r"heat pumps?", r"mini[- ]splits?", r"boilers?", r"hvac", r"rooftop units?")),
    ("V-MACHINE-TOOL", _W(r"lathes?", r"mills?", r"milling", r"drill press\w*", r"press", r"presses", r"band ?saws?",
                          r"saws?", r"cnc", r"burn tables?", r"plasma", r"grinders?", r"shears?", r"press brakes?",
                          r"manipulators?", r"furnaces?", r"ovens?", r"spray booths?", r"machining", r"machinery",
                          r"machine tools?")),
    ("V-SHOP-EQUIP", _W(r"weld\w*", r"compressors?", r"generators?", r"pressure washers?", r"power washers?",
                        r"heaters?", r"pumps?", r"wrappers?", r"wrapping", r"scrubbers?")),
    ("V-APPLIANCE", _W(r"refrigerators?", r"fridges?", r"freezers?", r"vending", r"washing machines?", r"washers?",
                       r"dryers?", r"microwaves?", r"fountains?", r"water coolers?", r"ice machines?", r"dishwashers?",
                       r"coffee", r"appliances?", r"stoves?")),
    ("V-RACKED-INV", _W(r"racks?", r"racking", r"shelving", r"shelf", r"shelves", r"bins")),
    ("V-HAND-TOOLS", _W(r"tools?", r"toolbox\w*", r"tool chests?", r"workbench\w*", r"work bench\w*", r"jack stands?",
                        r"carts?", r"shop vac\w*", r"vacuums?", r"work tables?", r"worktables?")),
    ("V-FLOOR-INV", _W(r"pallets?", r"box", r"boxes", r"cardboard", r"supplies", r"stock", r"materials?", r"crates?",
                       r"plywood", r"goods", r"bottled water", r"cases", r"merchandise", r"inventory", r"stored",
                       r"bags?", r"containers?", r"lumber", r"sheets")),
    ("V-OFFICE-FURN", _W(r"desks?", r"chairs?", r"tables?", r"cabinets?", r"files?", r"filing", r"cubicles?", r"sofas?",
                         r"couch\w*", r"recliners?", r"bookcases?", r"furniture", r"conference", r"seating",
                         r"benches", r"bench")),
    ("V-SMALL", _W(r"fans?", r"blowers?", r"trash", r"garbage", r"buckets?", r"extinguishers?", r"ladders?", r"cones?",
                   r"mats?", r"cords?", r"cables?", r"cabling", r"hoses?", r"cans?")),
]
BY_CATEGORY = {"electrical": "V-ELEC-GEAR", "it": "V-IT", "hvac": "V-HVAC", "inventory": "V-FLOOR-INV",
               "equipment": "V-OTHER", "furniture": "V-OFFICE-FURN", "finishes": "A-FIN", "other": "V-OTHER"}


def classify(label: str, category: str) -> str:
    label = label or ""
    if FABRIC.search(label):
        return "A-FIN"
    if VEHICLE.search(label) and not NOT_ROAD.search(label):
        return "V-VEHICLE"
    for cid, rx in RULES:
        if rx.search(label):
            return cid
    return BY_CATEGORY.get(category, "V-OTHER")


def value_class(cid: str) -> dict:
    a = model.assumption_by_id(cid)
    if a is None or a not in model.assumptions()["assets"]:
        raise KeyError(cid)
    return a


def category_for(cid: str, vision_category: str) -> str:
    """The contract category for a class; V-OTHER keeps the vision model's category."""
    return vision_category if cid == "V-OTHER" else value_class(cid)["category"]


def is_movable(cid: str) -> bool:
    return bool((model.assumption_by_id(cid) or {}).get("movable"))
