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

## Project layout

| File | Purpose |
|------|---------|
| `index.html` | Dashboard shell, styles and layout |
| `app.js` | Map, filtering, ranking and detail-drawer logic |
| `hubs-data.js` | **Auto-generated** `window.HUBS` array consumed by `app.js` |
| `data/hub_prioritization_results.xlsx` | Source output of the prioritization pipeline |
| `scripts/generate_hubs_data.py` | Builds `hubs-data.js` from the xlsx |
| `layers/` | Shared GeoJSON layers shown to every viewer ([layers/README.md](layers/README.md)) |
| `.github/workflows/deploy-pages.yml` | Auto-deploys the site to GitHub Pages on push to `main` |

## Regenerating the data

`hubs-data.js` is generated from the pipeline's `Results` sheet. After dropping a
new xlsx into `data/`, regenerate it:

```bash
pip install openpyxl
python3 scripts/generate_hubs_data.py \
    --xlsx data/hub_prioritization_results.xlsx \
    --out hubs-data.js
```

### Column mapping

The generator maps the spreadsheet's `Results` sheet onto the fields `app.js`
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
| `lines` | `LineNamesHE` | |
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
3. Share the resulting URL — `https://oh-da.github.io/HubsMap/`.

Every later push to `main` (new data, new layers) redeploys automatically.
Since this is a purely client-side site, **all hub data is downloadable by
anyone who can open the link** — a GitHub Pages site is public. Don't publish
data here that shouldn't be public.
