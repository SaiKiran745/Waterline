"""Pre-storm playbook (HTML), grouped by room and ordered by avoided loss."""
import html

from app.actions import report
from app.loss import mitigations as engine

e = html.escape


def render(building: dict, assets: list[dict], entry_points: list[dict], depth_ft: float) -> str:
    mits = engine.ranked(building["id"], engine.candidates(building["id"], assets, entry_points), assets, depth_ft,
                         engine.building_loss_fn(building))
    by_asset = {t: m for m in mits for t in m["targets"]}
    rooms: dict[str, list[dict]] = {}
    for a in assets:
        if a["value_basis"] != "V-VEHICLE":
            rooms.setdefault(a["room"], []).append(a)
    room_value = {r: sum(by_asset[a["id"]]["avoided_loss_usd_high"] for a in items if a["id"] in by_asset)
                  for r, items in rooms.items()}
    sections = []
    for room in sorted(rooms, key=lambda r: -room_value[r]):
        steps, done = [], set()
        for a in sorted(rooms[room], key=lambda a: a["height_ft_low"]):
            m = by_asset.get(a["id"])
            if m and m["id"] not in done and m["avoided_loss_usd_high"] > 0:
                steps.append(f"<li>{e(m['action'])} (avoids ${m['avoided_loss_usd_low']:,}-{m['avoided_loss_usd_high']:,} at {depth_ft:g} ft)</li>")
                done.add(m["id"])
        items = "".join(f"<li>{e(a['label'])}: lowest vulnerable part {a['height_ft_low']:.1f}-{a['height_ft_high']:.1f} ft</li>"
                        for a in sorted(rooms[room], key=lambda a: a["height_ft_low"]))
        sections.append(f"<h2>{e(room)}</h2><h3>Do first</h3><ol>{''.join(steps) or '<li>No action needed at this depth.</li>'}</ol>"
                        f"<h3>At risk</h3><ul>{items}</ul>")
    barrier = next((m for m in mits if m["kind"] == "entry_barrier"), None)
    lead = f"<p>Before anything else: {e(barrier['action'])}.</p>" if barrier and barrier["avoided_loss_usd_high"] > 0 else ""
    move = next((m for m in mits if m["basis"] == "M-MOVE-VEHICLES"), None)
    if move:
        listed = {a["id"]: a for a in assets}
        names = "".join(f"<li>{e(listed[t]['label'])} ({e(listed[t]['room'])})</li>" for t in move["targets"] if t in listed)
        lead += (f"<h2>Movable assets at risk</h2><p>{e(move['action'])}. {e(move['payback_note'])}.</p>"
                 f"<ul>{names}</ul>")
    return (f"<article><h1>Pre-storm playbook: {e(building['name'] or building['address'])}</h1>"
            f"<p>Planned for {depth_ft:g} ft of water above the ground-floor slab (a scenario, not a forecast). "
            f"Rooms are ordered by the loss their actions avoid. {e(report.survey_line(building['id'], assets))}</p>{lead}{''.join(sections) or '<p>No surveyed assets yet.</p>'}</article>")
