# Data notes

Phase 0 discovery, re-run 2026-11-14 with the sponsor kit and keys.

Labels used in this file:
- **VERIFIED**: we made a real call or read the real file, and the result is cached under `data/cache/`.
- **DOCS**: read in the kit or the vendor's docs, but not exercised.
- **NOT VERIFIED**: still open.

This file is committed to a public repo. It contains field names, counts and redacted shapes only. Raw sponsor data stays in `data/cache/` and `data/toolkit/`, which are both git-ignored.

## 0. Where things are

| What | Path | Notes |
|---|---|---|
| CoStar kit | `data/toolkit/costar-hackathon-kit/` | Not in `docs/toolkit/`. Git-ignored. |
| Vexcel tutorial and quickstart | `data/toolkit/vexcel/Vexcel_API_Hackathon_Tutorial_PDF_PY/` | Git-ignored. |
| Matterport connection material | missing | The kit's `index.md` says it "is provided in a separate zip file". That zip was not in the materials, so we used the public docs at developers.matterport.com. |
| Caches | `data/cache/{costar,matterport,vexcel,public}/` | Git-ignored. |

## 1. What the kit offers

**CoStar: local files only.** There is no hosted API, no MCP server and no SDK.
- `schemas/openapi.yaml` is OpenAPI 3.0.3 with `paths: {}`. It describes record shapes, not endpoints.
- The kit includes:
  - 8 JSON Lines datasets in `data/`
  - starter CSVs (`commercial-properties.csv` with PropertyId, MatterportModelId, Address, City and State; `residential-listings.csv`)
  - one model page per dataset in `models/`
  - background pages in `concepts/`
  - JSON Schema (draft 2020-12) per dataset, plus `schemas/enums.json`, a lookup from integer enum to name
  - `tools/expand_records.py`, which only writes pretty-printed copies of records to `records/`

| Dataset | Records | Key |
|---|---|---|
| commercial-property | 3,339 | `id` (PropertyId) |
| commercial-listing-summary | 1,022 | `id` |
| location-occupancy | 74,093 | `id`; `propertyId`, `tenantLocationId` |
| company-detail | 49,575 | `id` (= `tenantLocationId`) |
| commercial-sale-comp | 6,120 | `id`; `entities[].propertyId` |
| apartment-listing | 1,747 | `id`; `propertyId` |
| residential-listings | 2,120 | `id` |
| residential-listing-features | 1,899 | `id` |

**Vexcel:** REST API 2.0 at `https://api.vexcelgroup.com/v2`, plus the tutorial PDF and `vexcel_quickstart.py`. There is no SDK and no MCP server. The full interactive docs at that URL need a sign-in we do not have.

**Matterport:** the GraphQL Model API and the Showcase SDK (Embed and Bundle), both from the public docs.

## 2. CoStar (VERIFIED by streaming `data/commercial-property.jsonl`)

**Scope.**
- Houston is `primaryAddress.researchMarketId == 14`, with 1,758 properties. Los Angeles (`20`) has 1,581.
- To list Houston buildings, stream the file and filter on that field, then on `propertyType`.

**Houston properties by type** (properties / with a Matterport scan):

| Type | Properties | With scan |
|---|---|---|
| Multifamily | 1,348 | 1,343 |
| Office | 191 | 182 |
| Industrial | 98 | 93 |
| Hospitality | 54 | 54 |
| GeneralRetail | 41 | 36 |
| Flex | 21 | 20 |
| Land / Specialty / Healthcare | 2 / 2 / 1 | 0 / 2 / 1 |

There are 410 Houston commercial properties that are not multifamily; 388 of them have a scan.

**Fields per building.** "Fill" is the count of Houston retail, industrial and flex records (n = 160) where the field is not null.

| Need | Field | Fill |
|---|---|---|
| Type | `propertyType`, `propertySubtype` (integers; decode with `enums.json` PropertyType and PropertySubtype) | 160 |
| Size | `grossBuildingAreaSquareFeet` (GBA) | 160 |
|  | `rentableBuildingAreaSquareFeet` (RBA) | 160 (kit-wide only 550 of 3,339) |
|  | Retail GLA: `propertyRetail.grossLeasableAreaSquareFeet` |  |
| Year built | `constructionEvents[]` where `eventType == 2` (ConstructionComplete), then `.year` (can be approximate) | 160 |
| Stories | `numStoriesAboveGrade` | 160 |
| Height | `buildingHeightInFeet` | 55 |
| Name | `buildingName` | 80 |
| Location | `primaryAddress.latitude`, `.longitude`, `.streetNumber`, `.streetName`, `.streetType`, `.city`, `.postcode`; `primarySubmarketId` | 160 |
| Floors | `floors[].floorName` (FloorName enum), `floors[].floorSize.squareFeet` | 160 |
| Entry-point hints | `propertyIndustrial` / `propertyFlex` / `propertyRetail`: `.numExternalLoadingDocks`, `.hasLoadingDocks`, `.driveInBays.numDriveInBays`, `.driveInBays.numFeetHigh`, `.hasDriveInBays` | varies |
| Scans | `attachments[]` where `videoExternalReferenceType` is 36 (MatterportScan) or 234 (MatterportStreamingKey); `videoKey` is the Matterport model id | 149 |
| Tenants | location-occupancy `propertyId`, `tenantLocationId`, `fromDate`, `toDate` (null = current), joined to company-detail `id` → `name` |  |
| Value | No value field on the property itself. See below. |  |

**Value.** commercial-sale-comp, via `entities[].propertyId`, has these fields:
- `soldForPrice` with `salePriceStatus`. It is often absent: Texas does not disclose sale prices.
- `soldDate`.
- `assessment.totalValue`, `.improvedValue` and `.landValue` (assessor values).
- `marketAssessment.marketTotalValue`.

commercial-listing-summary has `forSaleSummary.askingPrice`.

How we get a per-building value (`backend/app/sources/costar.py`, `assessor_values`):
- **Preferred: deed-level assessments matched by parcel number.** Take `transferDocuments[].assessments[]`, keep those whose `parcelNumber` matches one of the property's `parcelNumbers`, and sum `assessment.improvedValue` and `.totalValue` over distinct APNs. This works inside portfolio sales. Each record also carries `assessmentYear`.
- **Fallback: a single-property comp's own `assessment`.** A portfolio comp's top-level `assessment` can cover dozens of properties, so it is never used.
- **Coverage:** 62 of the 82 usable single-storey retail, industrial and flex candidates have a value this way. All 8 shortlisted buildings do.

**Limits and caveats (from the kit's own docs).**
- Values are as of CoStar's last research, not live.
- Enums are integers, and `0` means unknown.
- Every email address and phone number in the kit is fake.
- The kit covers CoStar's Matterport capture list, not a fair sample of Houston.
- Current tenancies can be stale.

**Redacted sample shape:**
```json
{"id": 0, "propertyType": 2, "propertySubtype": 0, "grossBuildingAreaSquareFeet": 0.0,
 "numStoriesAboveGrade": 1, "constructionEvents": [{"eventType": 2, "year": 0, "month": null}],
 "primaryAddress": {"researchMarketId": 14, "latitude": 0.0, "longitude": 0.0, "city": "…", "postcode": "…"},
 "propertyIndustrial": {"numExternalLoadingDocks": 0, "driveInBays": {"numDriveInBays": 0, "numFeetWide": 0, "numFeetHigh": 0}},
 "attachments": [{"attachmentType": 0, "caption": "…", "videoExternalReferenceType": 36, "videoKey": "<model id>"}]}
```

## 3. How the layers link

| From → to | Link | Evidence |
|---|---|---|
| CoStar → Matterport | **ID.** `attachments[].videoKey` is the Matterport model id. | VERIFIED: all 238 model ids on Houston retail, industrial and flex properties return a model from the Model API. Each model's `geocoordinates` sits a median 46 m from the CoStar point; 161 of 218 are within 100 m and 3 are more than 500 m away. |
| CoStar → Vexcel | **Latitude and longitude only.** There is no shared id. | VERIFIED: `property/extract` with `POINT(lng lat)` returns the parcel, with `request-information.inside-parcel`. On the test building, Vexcel `footprint.area` (203,919 sq ft) is close to CoStar GBA (200,000). The test point returned 6 parcel features. |
| CoStar → FEMA, USGS | Latitude and longitude. | VERIFIED |

## 4. Matterport

**Authentication** (DOCS: developers.matterport.com/api; VERIFIED in use).
- `POST https://api.matterport.com/api/models/graph` with HTTP Basic auth: the Token ID is the username and the Token Secret is the password.
- `MATTERPORT_API_KEY` is the Token ID (16 hex characters) and `MATTERPORT_API_TOKEN` is the Token Secret (32 hex). With them, calls return 200. The same query without credentials returns 401 `request.unauthorized`.
- The docs say these tokens are admin or all-access: they can archive models and make purchases. Use them **server-side only, read-only queries only**. Our probe script refused to send mutations.

**What is retrievable per scan position.** First tested on the scan of a single-storey test warehouse (not on the final shortlist; 10 positions, one floor; cache `data/cache/matterport/model/<id>/`), then pulled in full for all 8 shortlisted buildings. The schema came from introspection (`data/cache/matterport/schema/`). `panoLocations(ids:)` takes `[String!]`, not `[ID!]`.

| Element | Field | Our credentials return it? |
|---|---|---|
| Scan position | `model.locations` → `AnchorLocation { id label position {x y z} floor {id} room {id} neighbors tags }` | Yes, 10 of 10 positions with `room` and `neighbors` |
| Panorama image | `model.panoLocations` → `PanoramicImageLocation { id position rotation resolutions skybox(resolution: "2k") { status format children validUntil } }` | Yes. Resolutions on offer: `high`, `low`, `4k`, `2k`. `children` holds 6 cube-face URLs, and face 0 is the up face (we viewed it). |
| Floor | `model.floors { id label sequence }` | Yes. Labels are relative to the scan: a scan captioned "2nd Floor" reports `Floor 1`, sequence 0. |
| Room | `model.rooms { id label classifications {label confidence} dimensions(units) ceiling(units) {minHeight maxHeight} }` | Partly. Across the 8 shortlisted models there are 76 rooms; only 4 have labels and 24 have `ceiling.maxHeight`. |
| Dimensions | `model.dimensions(units: imperial) { areaFloor areaFloorIndoor height width depth }` | `areaFloor` yes. On the shortlist, scans cover 43% to 102% of CoStar GBA. |
| Mesh | `model.assets.meshes { format resolution status filename url validUntil }` | Yes: OBJ at `50k` and `500k`, available on 236 of 238 models. The 50k OBJ is 1.2–3.4 MB on the shortlist. On the test model it is z-up, its extent matches `areaFloor` if units are metres (inferred), and the floor sits near z = 0. |
| Mesh textures | `model.assets.textures(resolutions, qualities) { quality resolution textures status urlTemplate }` | **No usable textured mesh.** The 50k OBJ has no `vt`, `mtllib` or `usemtl` lines; 10–34 50k textures are listed with a `urlTemplate`, but without UVs they cannot be applied. The 500k OBJ does have UVs and `usemtl <name>_000.jpg` lines, and 87 500k textures are listed as available, but the API returns no URL for them and the `.mtl` is not listed. The OBJ and MatterPak zips under `assets.resources` are `unavailable` (paid bundles). |
| Depth maps | none found in Model, AnchorLocation, PanoramicImageLocation or ModelAssets | No |
| Existing tags | `model.mattertags { id label anchorPosition … }` | The field works; 0 tags on all 8 models checked in Phase 0. |
| Matterport object detections | `model.objectAnnotations { id label confidence classification {label} room floor }` | The field works; 0 annotations on all 8 models checked in Phase 0. |
| Geolocation | `model.geocoordinates { latitude longitude altitude source }` | Yes. `source` is `processing`. |
| Floor plans | `model.assets.floorplans { format provider status floor }` | Yes: jpg and png. |

**Limits.**
- Skybox and mesh URLs are signed and expire about 5 minutes after the query (`validUntil`). Download them in the same step as the query.
- 4096 px skyboxes need an add-on, according to the old snippets page. `4k` is listed in `resolutions` but untested.
- No rate limit is documented. 24 batched queries of 10 models each hit no 429.

**All Houston retail, industrial and flex scans** (`data/cache/matterport/bulk_summary.json`):
- 238 models, all `active`, created in the account on 2026-11-10/11.
- 223 have one floor and 15 have two.
- Scan positions per model: minimum 0, median 16, maximum 199.

**Redacted sample shape:**
```json
{"model": {"floors": [{"id": "…", "label": "Floor 1", "sequence": 0}],
  "locations": [{"id": "…", "position": {"x": 0.0, "y": 0.0, "z": 0.0}, "floor": {"id": "…"}, "room": {"id": "…"}, "neighbors": ["…"]}],
  "assets": {"meshes": [{"format": "obj", "resolution": "50k", "status": "available", "url": "<signed, ~5 min>"}]}}}
```

## 5. Ground floor

The Matterport floor label does not say which building floor a scan is on (see section 4). So "ground-floor scan" comes from CoStar: when `numStoriesAboveGrade == 1`, every scan of the building is on the ground floor.

| Houston properties with a scan | Count |
|---|---|
| All types | 1,731 |
| Single-storey, so the scans are ground floor | **168**: Industrial 91, GeneralRetail 30, Flex 20, Office 14, Multifamily 13 |
| Multi-storey or unknown, so the scan floor cannot be determined from data | 1,563 |
| **Retail, industrial or flex with a ground-floor scan** | **141** (Industrial 91, GeneralRetail 30, Flex 20) |
| Of those, ready for the demo (8 or more positions, a mesh, and the model within 150 m of the CoStar point) | **103** (Industrial 68, GeneralRetail 22, Flex 13) |

Some multi-storey properties have captions such as "1st Floor - 4,150SF" that name the floor, but captions are free text.

**Shared scans.** 10 Matterport models are attached to more than one candidate property (30 properties in all), for example one scan filed on every building in a park. A shared scan cannot be tied to one building, so the shortlist does not use them. Excluding them leaves 82 usable candidates.

## 6. Matterport SDK

- **Domains:** `MATTERPORT_SDK_DOMAINS` in `.env` has one entry, `localhost`, with no port. The key's real allow list lives in the Matterport account and cannot be read through the Model API.
- **Port:** the Bundle docs list `localhost` and `localhost:8080` as separate allow-list entries, which suggests entries are port-specific. Which port works is **NOT VERIFIED**.
- **Bundle SDK with our key: NOT VERIFIED.** It can only be tested in a browser on an allow-listed origin.
- **Scene and three.js** (DOCS: developers.matterport.com/reference/scene):
  - "The Scene namespace is currently only available for Bundle SDK distributions."
  - three.js is exposed as `sdk.Scene.THREE` ("Direct access to the three.js instance used by Showcase") and as `this.context.three` inside a component.
  - Pattern: `sdk.Scene.register(name, factory)`, then `sdk.Scene.createObjects(1)`, `object.addNode()`, `node.addComponent(name)`, and set `this.outputs.objectRoot = mesh`.
  - `createNode` and `createNodes` are deprecated.
  - The bundled three.js version is not stated.
- **Loading** (DOCS):
  - Self-host the bundle, iframe `showcase.html?m=<model>&applicationKey=<SDK key>`, then call `MP_SDK.connect(window)`.
  - The SDK key is public by design: it travels in the iframe URL. Hence the name `NEXT_PUBLIC_MATTERPORT_SDK_KEY`.

## 7. Vexcel (VERIFIED on a test warehouse; parcel and imagery pulled for all 8 shortlisted)

**Authentication:** the `X-API-KEY: <key>` header. Coordinates go in WKT as `POINT(lon lat)` with `srid=4326`.

**Calls made** (cache `data/cache/vexcel/prop_<id>/`):

| Call | Result |
|---|---|
| `GET property/extract?wkt&srid&layer=urban,urban-r,wide-area,urban-g&latest=true&include=precomputed&unit-system=imperial` | 200. GeoJSON FeatureCollection with the parcel, 75 parcel attributes, and `structures[]` with 90 keys each, including `footprint.area`, `footprint.wkt`, `ground-elevation.value`, `roof-characteristics.*` and `roof-objects.*`. |
| `GET oriented/collections?…&layer=urban&product-type=oblique&include=product-type,collection,last-capture-date` | 200. Obliques north, south, east and west from 2026 collections, plus older years. |
| `POST ortho/extract` | 200. JPEG with XMP: `Vexcel:product-type` spherical-ortho, `Vexcel:min-gsd`/`max-gsd` 0.072–0.076 m, `Vexcel:collection`, `Vexcel:first-capture-date`/`last-capture-date`, zoom 21, camera UltraCam Osprey 4.1. |
| `POST oriented/extract` (oblique-north) | 200. JPEG. |
| `GET dsm/collections?wkt&srid&include=min-gsd,max-gsd` | 200. 10 DSM collections at the point, GSD 0.072–0.151 m. |
| `GET dtm/collections?wkt&srid` | 200. 1 DTM collection: `n29w95-us-tx-houston-2025`. |
| `GET property/extract?…&include=calculated` | 200. Returns `roof-characteristics.elevation` and `roof-characteristics.height`, but the values are inconsistent: roof elevation 113.9 is below ground elevation 117. **Do not use.** |

**Imagery:** ortho and four obliques at about 7.5 cm GSD. On the shortlist, the latest oblique captures fall between 2026-01-02 and 2026-02-12. Not every direction exists in the newest collection: Building B has no east view and Building G has only a west view.

**Precomputed attributes can lag the imagery.** On the test building, `metadata.collection` for property/extract is `us-tx-cypressr2-2023` (ortho-date estimate 2023-11-28), while the image itself is `us-tx-cypress-2026`.

**Elevation.**
- DSM and DTM coverage is listed for our key.
- The endpoint that downloads DSM or DTM tiles is not in the tutorial or the public migration guide: **NOT VERIFIED**.
- `structures[].ground-elevation.value` (feet, with imperial units) is available now. On the Phase 0 shortlist it was between 1.1 ft below and 3.8 ft above USGS EPQS at the CoStar point.
- **Work stopped (human decision, 2026-11-14).** We no longer pursue DSM/DTM downloads or roof heights. Elevation is shown as context only, from USGS EPQS.

**Limits (tutorial).**
- A 429 response means retry with backoff.
- One extract is capped at 1,024 tiles.
- Images come back as bytes with XMP metadata.
- A 404 from `property/extract` means there is no parcel at that point.

## 8. Flood zones: FEMA NFHL (VERIFIED, public, no key)

- Service: `https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer`.
- Layer 28, Flood Hazard Zones: `FLD_ZONE`, `ZONE_SUBTY`, `SFHA_TF`, `STATIC_BFE`, `DEPTH`, `V_DATUM`, `DFIRM_ID`.
- Layer 3, FIRM Panels: `FIRM_PAN`, `EFF_DATE` (epoch milliseconds).
- `-9999` means null.
- The toolkit has no flood layer.
- **The 149 Houston retail, industrial and flex candidates** (`data/cache/public/fema/candidate_zones.json`):
  - 17 are in the SFHA: AE 14, AE floodway 2, AO 1.
  - 22 are in shaded X (0.2%).
  - 110 are in minimal-hazard X.
  - None of the 8 Phase 0 shortlist buildings had a `STATIC_BFE`.

## 9. Ground elevation: USGS EPQS (VERIFIED, public, no key)

- `GET https://epqs.nationalmap.gov/v1/json?x=<lng>&y=<lat>&wkid=4326&units=Feet&includeDate=false`. The elevation is in `value`.
- The response states no vertical datum.
- The first call took 8 s (later calls were not timed), so cache every point.
- On the shortlist, values range from 34.6 to 111.9 ft.

## 10. Failed or unverified

1. The Matterport connection zip that the kit mentions is missing.
2. The Bundle SDK has not been tested with our key, and the allowed localhost port is unknown. Option A is now optional (docs/DECISIONS.md).
3. Vexcel DSM and DTM downloads and roof heights: work stopped by decision; elevation is context only.
4. Vexcel `include=calculated` roof values are inconsistent and must not be used.
5. Matterport room labels are sparse. There are no tags, object annotations or depth maps on the models checked.
6. No usable textured mesh (section 4): the 3D view will be an untextured mesh.
7. Model keys: on 2026-11-14 `GEMINI_API_KEY` got HTTP 400 "API key not valid" and `ANTHROPIC_API_KEY` got HTTP 401 "invalid x-api-key" on a model lookup. Both are being replaced.
8. Python: the backend uses Homebrew Python 3.14 in `backend/.venv` (pyenv's 3.10.1 is too old).
9. Building B has no east oblique and Building G only a west oblique in the newest Vexcel collection.

## 11. Cache layout

```
data/cache/shortlist.json                     letter -> CoStar id and Matterport model (sponsor data; never commit)
data/cache/http/<source>/<key>.json           every external JSON response, keyed by request (matterport, vexcel, fema, usgs)
data/cache/costar/property/<id>.json          raw CoStar record per shortlisted building
data/cache/buildings/<id>/parts.json          everything pulled for a building
data/cache/buildings/<id>/building.json       the Building contract record served by the API
data/cache/media/<id>/manifest.json           mesh, panorama and aerial URLs for the front end
data/cache/media/<id>/panos/<pano>/face0-5.jpg  2k skybox faces for every scan position
data/cache/media/<id>/mesh/mesh_50k.obj       Matterport 50k OBJ (untextured)
data/cache/media/<id>/aerial/*.jpg             Vexcel ortho and obliques, with *.meta.json (request and XMP)
data/cache/pull_report.json                   last pull summary
data/cache/costar/, matterport/, vexcel/, public/   Phase 0 discovery files
```
