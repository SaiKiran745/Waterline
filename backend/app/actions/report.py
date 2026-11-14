"""Resilience report (HTML) for lenders and insurers. Phase 5B enriches it; this version is complete but plain."""
import html

from app.loss import mitigations as engine
from app.loss import model

e = html.escape


def money(lo, hi) -> str:
    return f"${lo:,.0f}-{hi:,.0f}"


def render(building: dict, assets: list[dict], entry_points: list[dict], depth_ft: float) -> str:
    s = model.scenario(building, assets, depth_ft)
    mits = engine.ranked(building["id"], engine.candidates(building["id"], assets, entry_points), assets, depth_ft,
                         engine.building_loss_fn(building))
    hit = {h["asset_id"]: h["status"] for h in s["assets_hit"]}
    cov = building.get("scan_coverage")
    rows = "".join(
        f"<tr><td>{e(a['room'])}</td><td>{e(a['label'])}</td><td>{a['height_ft_low']:.1f}-{a['height_ft_high']:.1f} ft</td>"
        f"<td>{a['confidence']:.2f}</td><td>{money(a['value_usd_low'], a['value_usd_high'])}</td><td>{hit.get(a['id'], '')}</td></tr>"
        for a in sorted(assets, key=lambda a: a["height_ft_low"]))
    mit_rows = "".join(
        f"<tr><td>{m['rank']}</td><td>{e(m['action'])}</td><td>{money(m['cost_usd_low'], m['cost_usd_high'])}</td>"
        f"<td>{money(m['avoided_loss_usd_low'], m['avoided_loss_usd_high'])}</td><td>{e(m['payback_note'])}</td></tr>"
        for m in mits)
    eps = "".join(f"<li>{e(p['kind'])}: {e(p['evidence'])} (confidence {p['confidence']:.2f})</li>" for p in entry_points) \
        or "<li>Entry points not surveyed yet.</li>"
    assumptions = "".join(
        f"<li><b>{e(a['id'])}</b>{' <b>PLACEHOLDER</b>' if a['placeholder'] else ''}: {e(a['text'])} <i>Source: {e(a['source'])}</i></li>"
        for a in s["assumptions"])
    return f"""<article>
<h1>Flood resilience report: {e(building['name'] or building['address'])}</h1>
<p>{e(building['address'])}. {e(building['property_subtype'] or building['property_type'])}, {building['size_sqft']:,.0f} sq ft (GBA),
built {building['year_built'] or 'unknown'}, {building['stories']} storey. FEMA zone {e(building['flood_zone'] or 'unknown')}
({'inside' if building['in_mapped_flood_zone'] else 'outside'} the 1% annual-chance area; {e(building['flood_zone_source'] or '')}).</p>
<p><b>Scenario:</b> {depth_ft:g} ft of water above the ground-floor slab. This is a scenario chosen by the user, not a prediction.</p>
<p><b>Contents loss:</b> {money(s['loss_usd_low'], s['loss_usd_high'])}. <b>Structure loss:</b> {money(s['structure_loss_usd_low'], s['structure_loss_usd_high'])}.</p>
<p><b>Scope:</b> the 3D scan covers {building['scan_area_sqft'] or 0:,.0f} sq ft, {cov:.0%} of the building. Contents loss counts only what the scan shows;
structure loss is scaled to the scanned share.</p>
<h2>Where water gets in</h2><ul>{eps}</ul>
<h2>Exposed assets</h2><table><tr><th>Room</th><th>Asset</th><th>Lowest vulnerable part</th><th>Confidence</th><th>Value</th><th>At {depth_ft:g} ft</th></tr>{rows}</table>
<h2>Ranked mitigations at {depth_ft:g} ft</h2><table><tr><th>#</th><th>Action</th><th>Cost</th><th>Avoided loss</th><th>Payback</th></tr>{mit_rows}</table>
<h2>Assumptions</h2><ul>{assumptions}</ul>
<h2>Limitations</h2><ul><li>Asset heights come from the 3D mesh where it resolves the item, otherwise from a visual estimate with lower confidence.</li>
<li>Values marked PLACEHOLDER are team assumptions without a cited source.</li><li>Ground elevation is context only and is not used in any number.</li></ul>
</article>"""
