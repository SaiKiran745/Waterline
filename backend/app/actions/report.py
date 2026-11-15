"""Resilience report (HTML) for lenders and insurers. Phase 5B enriches it; this version is complete but plain."""
import html

from app.loss import mitigations as engine
from app.loss import model

e = html.escape


def money(lo, hi) -> str:
    return f"${lo:,.0f}-{hi:,.0f}"


def central(lo, med, hi) -> str:
    """A simulated figure: the median and its 80% interval (contracts v1.3)."""
    return f"about ${med:,.0f} (80% interval ${lo:,.0f}-{hi:,.0f})"


def band(r) -> str:
    if r is None:
        return "none surveyed"
    return f"{r[0]:g} ft" if r[0] == r[1] else f"{r[0]:g}-{r[1]:g} ft"


def measured_lines(table: dict, s: dict, depth_ft: float) -> list[str]:
    """What the scan measures, with no dollar assumption: items reached and the threshold depths."""
    w, t = s["items_in_water"], table["thresholds"]
    reach = (f"{w['count_low']}" if w["count_low"] == w["count_high"] else f"{w['count_low']}-{w['count_high']}")
    share = (f"{w['share_low']:.0%}" if w["share_low"] == w["share_high"] else f"{w['share_low']:.0%}-{w['share_high']:.0%}")
    lines = [f"At {depth_ft:g} ft the water reaches {reach} of {w['of']} contents items ({share}).",
             f"First item reached at {band(t['first_loss_ft'])}; half the items at {band(t['half_items_ft'])}; "
             f"80% of them at {band(t['most_items_ft'])} (earliest from the bottom of each item's height range, latest "
             f"from the top)."]
    for c in t["critical_systems"]:
        name = c["name"][0].upper() + c["name"][1:]
        lines.append(f"{name} ({c['items']} item{'s' if c['items'] != 1 else ''}): first reached at "
                     f"{band(c['first_reached_ft'])}." if c["items"] else f"{name}: none surveyed.")
    lines.append(f"Heights: {t['heights_from_mesh']} of {t['contents_items']} measured from the 3D scan's mesh, "
                 f"{t['heights_estimated']} visual estimates.")
    return lines


def standard_lines(table: dict, s: dict, depth_ft: float) -> list[str]:
    from app.loss import sim
    sm = table.get("standard_method")
    if not sm or s.get("standard_contents_usd_median") is None:
        return []
    v, ratio = sim.verdict(s["loss_usd_median"], s["standard_contents_usd_median"])
    fn = "; ".join(f"{f['kind']} function {f['function_id']} ({f['description']}, {f['source']})" for f in sm["functions"])
    return [f"At {depth_ft:g} ft the Hazus-style contents loss on the same item values is about "
            f"${s['standard_contents_usd_median']:,.0f}; Waterline's is about ${s['loss_usd_median']:,.0f}, "
            f"{v}" + (f" ({ratio:.1f} times)" if ratio is not None and v != "about the same" else "") + ".",
            sm["statement"], sm["why_shapes_differ"],
            f"Method: {sm['method']}: {fn}. {sm['value_basis']} Source: {sm['citation']}."]


def survey_line(bid: str, assets: list[dict]) -> str:
    """The stored survey, said the same way as /triage and the agent: "N of M scan positions read"."""
    from app.loss import rank
    try:
        st = rank.survey_status(bid, assets)
    except FileNotFoundError:
        return "The interior survey has not run."
    return st["note"]


def render(building: dict, assets: list[dict], entry_points: list[dict], depth_ft: float) -> str:
    from app.loss import sim
    s = model.scenario(building, assets, depth_ft)
    table = model.scenario_table(building, assets)
    expected = sim.expected_by_asset(building, assets, depth_ft)
    mits = engine.ranked(building["id"], engine.candidates(building["id"], assets, entry_points), assets, depth_ft,
                         engine.building_loss_fn(building))
    hit = {h["asset_id"]: h["status"] for h in s["assets_hit"]}
    labels = {a["id"]: a for a in assets}
    cov = building.get("scan_coverage")
    rows = "".join(
        f"<tr><td>{e(a['room'])}</td><td>{e(a['label'])}</td><td>{a['height_ft_low']:.1f}-{a['height_ft_high']:.1f} ft</td>"
        f"<td>{a['confidence']:.2f}</td><td>{money(a['value_usd_low'], a['value_usd_high'])}</td><td>{hit.get(a['id'], '')}</td>"
        f"<td>{'$' + format(expected[a['id']], ',') if expected.get(a['id']) else ''}</td></tr>"
        for a in sorted(assets, key=lambda a: a["height_ft_low"]))
    mit_rows = "".join(
        f"<tr><td>{m['rank']}</td><td>{e(m['action'])}</td><td>{money(m['cost_usd_low'], m['cost_usd_high'])}</td>"
        f"<td>{central(m['avoided_loss_usd_low'], m['avoided_loss_usd_median'], m['avoided_loss_usd_high'])}</td>"
        f"<td>{e(m['payback_note'])}</td></tr>"
        for m in mits)
    top = "".join(f"<li>{e(labels[x['asset_id']]['label'])} ({e(labels[x['asset_id']]['room'])}): about "
                  f"${x['expected_loss_usd']:,.0f}, {x['share']:.0%} of the expected contents loss</li>"
                  for x in s["top_contributors"]) or "<li>No contents loss at this depth.</li>"
    eps = "".join(f"<li>{e(p['kind'])}: {e(p['evidence'])} (confidence {p['confidence']:.2f})</li>" for p in entry_points) \
        or "<li>Entry points not surveyed yet.</li>"
    assumptions = "".join(
        f"<li><b>{e(a['id'])}</b>{' (assumed range, editable)' if a['placeholder'] else ''}: {e(a['text'])} <i>Source: {e(a['source'])}</i></li>"
        for a in s["assumptions"])
    measured = "".join(f"<li>{e(x)}</li>" for x in measured_lines(table, s, depth_ft))
    standard = "".join(f"<p>{e(x)}</p>" for x in standard_lines(table, s, depth_ft)) or "<p>No Hazus occupancy mapping for this building.</p>"
    return f"""<article>
<h1>Flood resilience report: {e(building['name'] or building['address'])}</h1>
<p>{e(building['address'])}. {e(building['property_subtype'] or building['property_type'])}, {building['size_sqft']:,.0f} sq ft (GBA),
built {building['year_built'] or 'unknown'}, {building['stories']} storey. FEMA zone {e(building['flood_zone'] or 'unknown')}
({'inside' if building['in_mapped_flood_zone'] else 'outside'} the 1% annual-chance area; {e(building['flood_zone_source'] or '')}).</p>
<p><b>Scenario:</b> {depth_ft:g} ft of water above the ground-floor slab. This is a scenario chosen by the user, not a prediction.</p>
<p><b>Total loss:</b> {central(s['total_usd_low'], s['total_usd_median'], s['total_usd_high'])}.
<b>Contents:</b> {central(s['loss_usd_low'], s['loss_usd_median'], s['loss_usd_high'])}.
<b>Structure:</b> {central(s['structure_loss_usd_low'], s['structure_loss_usd_median'], s['structure_loss_usd_high'])}.
The median and 80% interval come from 4,000 simulated draws of every item's value and height (C-MC-*); percentiles do not add up across the parts.
The extreme bounds (every item at one end of its ranges) are in the assumptions.</p>
<p><b>Scope:</b> the 3D scan covers {building['scan_area_sqft'] or 0:,.0f} sq ft, {cov:.0%} of the building. {e(survey_line(building['id'], assets))}
Structure loss is scaled to the scanned share.</p>
<h2>What the scan measures (no dollar assumption)</h2><ul>{measured}</ul>
<h2>Largest contributors at {depth_ft:g} ft</h2><ol>{top}</ol>
<h2>Standard-method comparison</h2>{standard}
<h2>Where water gets in</h2><ul>{eps}</ul>
<h2>Exposed assets</h2><table><tr><th>Room</th><th>Asset</th><th>Lowest vulnerable part</th><th>Confidence</th><th>Value</th><th>At {depth_ft:g} ft</th><th>Expected loss</th></tr>{rows}</table>
<h2>Ranked mitigations at {depth_ft:g} ft</h2><table><tr><th>#</th><th>Action</th><th>Cost</th><th>Avoided loss</th><th>Payback</th></tr>{mit_rows}</table>
<h2>Assumptions</h2><ul>{assumptions}</ul>
<h2>Limitations</h2><ul><li>Asset heights come from the 3D mesh where it resolves the item, otherwise from a visual estimate with lower confidence.</li>
<li>Values marked "assumed range, editable" are team-set assumptions without a cited source; any asset's value or height can be corrected.</li><li>Ground elevation is context only and is not used in any number.</li></ul>
</article>"""
