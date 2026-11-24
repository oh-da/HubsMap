# מפת המתח״מים — תיעדוף · Hub Prioritization Map

An interactive map that visualizes the output of the **Hub Prioritization**
pipeline. It plots every transit hub (מתח״ם) on a Leaflet map, colored by
classification and sized by daily demand, with filtering, ranking context and a
per-hub detail drawer.

> נתיבי איילון · חטיבת תוכנית אב — אגף מודלים

## What it does

- **Map** — each hub is a circle: color = classification
  (ארצי / מטרופוליני / עירוני / לא מסווג), radius = daily demand (log scale).
- **Filters** (right rail) — by classification, metropolitan area, planned
  transport modes, minimum daily demand, and maximum rank.
- **Detail drawer** — click a hub for its contextual rank, daily demand, number
  of modes, 2050 population/employment catchment by ring (0–500 / 500–1,000 /
  1,000–1,500 m), planned modes and the lines passing through it.
- **Layers** — switch base map (light/gray/dark), toggle an inferred line
  network, toggle **shared layers** committed to the repo (see below), and
  upload your own GeoJSON overlays (persisted per-browser in `localStorage`).
- **PNG export** — the download button in the map's tool stack saves the current
  map view (base map, hubs, visible layers, title card and attribution) as a 2×
  PNG. The filter rail, detail drawer and buttons are left out.

## Project layout

| File | Purpose |
|------|---------|
| `index.html` | Dashboard shell, styles and layout |
| `app.js` | Map, filtering, ranking and detail-drawer logic |
| `hubs-data.js` | **Auto-generated** `window.HUBS` array consumed by `app.js` |
| `data/hub_prioritization_results.xlsx` | Source output of the prioritization pipeline |
| `scripts/generate_hubs_data.py` | Builds `hubs-data.js` from the xlsx |
| `layers/` | Shared GeoJSON layers shown to every viewer ([layers/README.md](layers/README.md)) |
| `compare/` | Network comparison against the agency network (see below) |
| `scripts/build_network_routes_map.py` | Builds `compare/mt_network_routes.html`, `compare/mt_network_lines.csv` and `compare/mt_network_decisions.csv` from the agency GeoPackage |
| `scripts/add_mot_differences.py` | Adds the marked differences of the agency GeoPackage to the two comparison pages |
| `.github/workflows/deploy-pages.yml` | Auto-deploys the site to GitHub Pages on push to `main` |

### `compare/`

Outputs of the network comparison run (our routes and hubs vs. the agency's
`MT_Network`). Nothing in the dashboard reads these files; the two HTML maps
are standalone pages.

| File | Purpose |
|------|---------|
| `compare_config.json` | Matching tolerances and thresholds used for the run |
| `compare_report.md`, `compare_report.json` | Run report: inputs, metrics and findings |
| `network_comparison.xlsx` | Comparison tables |
| `network_comparison.gpkg` | Comparison geometries (GeoPackage) |
| `network_comparison_routes.html` | Standalone map of the route comparison |
| `network_comparison_hubs.html` | Standalone map of the hub comparison |
| `MT_Network_12-11-2026.gpkg` | The agency network (layers `lines`, `stations`, `mot_differences`; EPSG:2039) |
| `MT_Network_MetaData.xlsx` | Code dictionary of the agency network (Hebrew labels) |
| `mt_network_routes.html` | Standalone map of the agency routes, coloured by mode, with route names; filters by mode and by opening year ("up to 2050" = every line that opens by 2050) |
| `mt_network_decisions.csv` | The decision for every route: the columns of `mt_network_lines.csv` plus `status` and `comment`. Written by the routes map (see "Decision tracking") |
| `mt_network_lines.csv` | The same routes as a table, one row per route: mode, line number and names, opening and closing year, plan, length and number of stops (UTF-8 with BOM, opens in Excel) |

The comparison files were produced by `hubs compare-network` of the
[HubPrioritizing](https://github.com/oh-da/HubPrioritizing) project from the
2026-11-04 run. The `lines` and `stations` layers of
`MT_Network_12-11-2026.gpkg` are the same network that run was compared with:
re-running the comparison against it reproduces every row of
`network_comparison.xlsx`, so the comparison files are current for it.

The two comparison pages also show the 18 points of the GeoPackage's
`mot_differences` layer as a set of their own ("Marked differences"): the
`line` points on the routes page, the `hub` points on the hubs page, each with
who is to correct it, the reason and the note. They are added by a script that
inserts one marked block into each page and can be run again at any time, also
after the pages are regenerated:

```bash
pip install geopandas
python3 scripts/add_mot_differences.py --gpkg compare/MT_Network_12-11-2026.gpkg
```

The agency file gives no origin or destination for a line, so the table has
none either.

To rebuild the routes map and the table after replacing the GeoPackage:

```bash
pip install geopandas openpyxl
python3 scripts/build_network_routes_map.py \
    --gpkg compare/MT_Network_12-11-2026.gpkg \
    --meta compare/MT_Network_MetaData.xlsx \
    --out compare/mt_network_routes.html \
    --csv compare/mt_network_lines.csv \
    --decisions compare/mt_network_decisions.csv --github-repo oh-da/HubsMap \
    --leaflet ../vendor/leaflet
```

Run it on an up-to-date checkout of `main`: the script rewrites
`mt_network_decisions.csv` with the current lines and keeps the status and
comment that are already in the file.

### Decision tracking

The routes map records, for every line, whether it has to be updated in the
Hubs model. Click a line (or pick it under "Find a line"): its popup has four
choices — **Updated**, **No need to update**, **Need to update**,
**Irrelevant** — and a comment box. The panel counts the lines per status,
the "any decision" filter shows one status (or the lines not decided yet), and
a decided line carries a mark beside its name on the map.

Changes are kept in the browser until **Save to GitHub** is pressed. Saving
commits `compare/mt_network_decisions.csv` to `main` through the GitHub API, so
everyone sees the same decisions and the file's history shows who changed what.
Before writing, the page reads the file again and keeps the decisions other
people saved in the meantime.

Saving needs a GitHub token, asked for on the first save and kept in that
browser only:

1. GitHub → **Settings → Developer settings → Personal access tokens →
   Fine-grained tokens → Generate new token**.
2. **Repository access**: "Only select repositories" → `HubsMap`.
3. **Permissions → Repository permissions → Contents**: "Read and write".

Anyone can open the map and read the decisions; only people with such a token
can save. Each save is a commit to `main`, so it also redeploys the site.
Because the page handles a token, it loads Leaflet from this site's own
`vendor/leaflet` instead of a CDN.

## Regenerating the data

`hubs-data.js` is generated from the pipeline's results sheet (named
`hub_prioritization_results`; the generator also falls back to the only sheet if
it's named differently). After dropping a new xlsx into `data/`, regenerate it:

```bash
pip install openpyxl
python3 scripts/generate_hubs_data.py \
    --xlsx data/hub_prioritization_results.xlsx \
    --out hubs-data.js
```

### Column mapping

The generator maps the spreadsheet's results sheet onto the fields `app.js`
expects:

| Hub field | xlsx column | Notes |
|-----------|-------------|-------|
| `name` | `HubNameHE` | |
| `lat`, `lng` | `y`, `x` | latitude / longitude |
| `type` | `HubTypeHE` | ארצי / מטרופוליני / עירוני / Not Hub |
| `metro` | `Metro` | metropolitan area |
| `ring` | `LocationForChart` | גלעין / טבעת / חוץ |
| `rank` | `Overall_Rank` | drives ranking + the rank slider |
| `demand` | `TotalDemand` | daily passengers |
| `logDemand` | `LogDemand` | marker radius scale |
| `numModes` | `Num_Modes` | |
| `modes` | `Modes_ForPlot` | comma-separated Hebrew mode names |
| `lines` | `Line_Names_forPlot` | comma-separated Hebrew line names (older exports: `LineNamesHE`) |
| `pop`, `emp` | `TotalPop_2050`, `TotalEmp_2050` | 1.5 km catchment, 2050 |
| `pop_0_500` … `emp_1000_1500` | matching columns | catchment by ring |

## Running locally

It's a static site — serve the folder and open it:

```bash
python3 -m http.server 8000
# then open http://localhost:8000/index.html
```

(A server is needed rather than opening the file directly, because `app.js`
fetches `hubs-data.js`, the shared layers, and remote map tiles.)

## Shared layers

Drop a GeoJSON file into `layers/` and register it in `layers/layers.json` to
make it a toggle that **every viewer** sees. This is the way to publish extra
layers (rail lines, planning boundaries, shapefiles converted to GeoJSON) — see
[`layers/README.md`](layers/README.md) for the conversion/reprojection steps.
(The in-app upload button is separate: those layers stay in one person's
browser via `localStorage` and are not shared.)

## Hosting (GitHub Pages)

The site is published with one shareable link via GitHub Pages:

1. In the repo: **Settings → Pages → Build and deployment → Source = "GitHub
   Actions"** (one-time).
2. Merge to `main`. The [`deploy-pages.yml`](.github/workflows/deploy-pages.yml)
   workflow builds and deploys automatically on every push to `main`.
3. Share the URL — `https://hubsmap.ohad.pro/`.

Every later push to `main` (new data, new layers) redeploys automatically.
Since this is a purely client-side site, **all hub data is downloadable by
anyone who can open the link** — a GitHub Pages site is public. Don't publish
data here that shouldn't be public.

### Custom domain

The site is served from `hubsmap.ohad.pro`. Two things make that work:

- The [`CNAME`](CNAME) file at the repo root. The deploy workflow uploads the
  whole repo (`path: '.'`), so this file ships with every deploy and the domain
  survives redeploys.
- A DNS `CNAME` record at the registrar (GoDaddy, on `ohad.pro`):
  `hubsmap` → `oh-da.github.io`.

After DNS propagates, set **Settings → Pages → Custom domain** to
`hubsmap.ohad.pro` and tick **Enforce HTTPS** once the certificate is issued.
To change the domain later, edit the `CNAME` file and the DNS record together —
changing only one of them takes the site offline.
