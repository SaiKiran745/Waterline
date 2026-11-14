"""CoStar hackathon kit reader (local JSON Lines files in data/toolkit/costar-hackathon-kit/).

There is no hosted CoStar API. Files are streamed line by line, never loaded whole.
Field names and enum codes are from the kit's models/ pages and schemas/enums.json.
"""
import json
import re
from functools import lru_cache
from typing import Iterable, Iterator

from app.config import KIT

HOUSTON_MARKET = 14
MATTERPORT_REF_TYPES = {36, 234}          # MatterportScan, MatterportStreamingKey
CONSTRUCTION_COMPLETE = 2                  # ConstructionEventType
EXISTING = 1                               # ConstructionStatus
TARGET_TYPES = {"GeneralRetail", "Industrial", "Flex"}


@lru_cache(maxsize=1)
def enums() -> dict:
    return json.loads((KIT / "schemas" / "enums.json").read_text())


def decode(enum_name: str, value) -> str | None:
    if value is None:
        return None
    return enums()[enum_name].get(str(value), str(value))


def iter_records(dataset: str) -> Iterator[dict]:
    with open(KIT / "data" / f"{dataset}.jsonl", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def matterport_model_ids(rec: dict) -> list[str]:
    ids = [a["videoKey"] for a in rec.get("attachments") or []
           if a.get("videoExternalReferenceType") in MATTERPORT_REF_TYPES and a.get("videoKey")]
    return list(dict.fromkeys(ids))


def type_block(rec: dict) -> dict:
    return rec.get("propertyIndustrial") or rec.get("propertyFlex") or rec.get("propertyRetail") or {}


def year_built(rec: dict) -> int | None:
    years = [e.get("year") for e in rec.get("constructionEvents") or []
             if e.get("eventType") == CONSTRUCTION_COMPLETE and e.get("year")]
    return max(years) if years else None


def address(rec: dict) -> str:
    pa = rec.get("primaryAddress") or {}
    street = " ".join(str(pa[k]) for k in ("streetNumber", "streetDirection", "streetName", "streetType") if pa.get(k))
    tail = ", ".join(x for x in (pa.get("city"), " ".join(y for y in (pa.get("state"), pa.get("postcode")) if y)) if x)
    return ", ".join(x for x in (street, tail) if x)


def houston_ground_floor_candidates() -> list[dict]:
    """Houston retail, industrial and flex properties, existing, single-storey, with at least one Matterport model."""
    out = []
    for rec in iter_records("commercial-property"):
        pa = rec.get("primaryAddress") or {}
        if pa.get("researchMarketId") != HOUSTON_MARKET or rec.get("constructionStatus") != EXISTING:
            continue
        if decode("PropertyType", rec.get("propertyType")) not in TARGET_TYPES or rec.get("numStoriesAboveGrade") != 1:
            continue
        models = matterport_model_ids(rec)
        if models and pa.get("latitude") is not None:
            out.append({"id": rec["id"], "type": decode("PropertyType", rec["propertyType"]),
                        "gba": rec.get("grossBuildingAreaSquareFeet"), "lat": pa["latitude"], "lng": pa["longitude"],
                        "models": models})
    return out


def property_records(ids: Iterable[int]) -> dict[int, dict]:
    wanted = set(ids)
    return {r["id"]: r for r in iter_records("commercial-property") if r["id"] in wanted}


def current_tenants(ids: Iterable[int]) -> dict[int, list[dict]]:
    """Tenancies with no `toDate` (current as of CoStar's last research), named via company-detail."""
    wanted = set(ids)
    occ: dict[int, list[dict]] = {i: [] for i in wanted}
    for r in iter_records("location-occupancy"):
        if r["propertyId"] in wanted and r.get("toDate") is None:
            occ[r["propertyId"]].append({"occupancy_id": r["id"], "tenant_location_id": r.get("tenantLocationId"),
                                         "from_date": r.get("fromDate")})
    loc_ids = {t["tenant_location_id"] for ts in occ.values() for t in ts if t["tenant_location_id"]}
    names = {r["id"]: r.get("name") for r in iter_records("company-detail") if r["id"] in loc_ids}
    for ts in occ.values():
        for t in ts:
            t["name"] = names.get(t["tenant_location_id"])
    return occ


def _apn(s) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", s or "").upper()


def assessor_values(ids: Iterable[int]) -> dict[int, dict]:
    """Assessor value per property from the most recent sale comp that has one.

    Preferred: deed-level assessments (`transferDocuments[].assessments[]`) whose `parcelNumber` matches one of
    the property's `parcelNumbers`, summed over distinct APNs. This works inside portfolio sales.
    Fallback: the comp-level `assessment` of a single-property sale (a portfolio's comp-level assessment may
    cover several properties, so it is never used).
    Sale prices are not used (Texas does not disclose them; see docs/DATA_NOTES.md).
    """
    wanted = set(ids)
    apns = {pid: {_apn(x) for x in rec.get("parcelNumbers") or [] if _apn(x)}
            for pid, rec in property_records(wanted).items()}
    best: dict[int, dict] = {}
    for r in iter_records("commercial-sale-comp"):
        ents = [e for e in r.get("entities") or [] if e.get("propertyId") is not None]
        sold = (r.get("soldDate") or "")[:10]
        for pid in {e["propertyId"] for e in ents} & wanted:
            per_apn = {}
            for d in r.get("transferDocuments") or []:
                for a in d.get("assessments") or []:
                    key = _apn(a.get("parcelNumber"))
                    val = a.get("assessment") or {}
                    if key in apns.get(pid, ()) and val.get("improvedValue") is not None and key not in per_apn:
                        per_apn[key] = (val, a.get("assessmentYear"))
            if per_apn:
                cand = {"value_usd": sum((v.get("totalValue") or 0) for v, _ in per_apn.values()) or None,
                        "improvement_value_usd": sum(v["improvedValue"] for v, _ in per_apn.values()),
                        "value_as_of": sold or None, "sale_comp_id": r["id"],
                        "basis": f"deed assessment, {len(per_apn)} parcel(s) matched by APN, "
                                 f"assessment year {max((y for _, y in per_apn.values() if y), default='unknown')}"}
            elif len(ents) == 1 and (r.get("assessment") or {}).get("improvedValue") is not None:
                a = r["assessment"]
                cand = {"value_usd": a.get("totalValue"), "improvement_value_usd": a["improvedValue"],
                        "value_as_of": sold or None, "sale_comp_id": r["id"], "basis": "sale comp assessment"}
            else:
                continue
            if pid not in best or (sold or "") > (best[pid]["value_as_of"] or ""):
                best[pid] = cand
    return best
