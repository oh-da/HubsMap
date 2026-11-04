# Hub prioritization run report

Started: 2026-11-04T14:06:03+00:00

## Inputs

| Key | File | Details |
|---|---|---|
| `run` | `/content/drive/MyDrive/Hubs_Oct_26/Output` | version=2026-11-04 |
| `hub_groups_all` | `/content/drive/MyDrive/Hubs_Oct_26/Output/hub_groups_all.csv` | file=hub_groups_all.csv, sha256=5322e827c59c80b9484c9332bf13ced46e18bd93d6a1f920c22be4b945f73616, rows=1042 |
| `network_nodes` | `/content/drive/MyDrive/Hubs_Oct_26/Output/network_nodes.csv` | file=network_nodes.csv, sha256=8b1b702e07cecdc43e243bed94c7f14022686f7f66ed2dab48b35e35882de875, rows=4185 |
| `agency_gpkg` | `/content/drive/MyDrive/Hubs_Oct_26/data/Minhal/MT_Network.gpkg` | file=MT_Network.gpkg, sha256=3cc2f16549c81ee0e3dde92e5c34f2f3dd0b75663e4d7c6dc75cc90c94ff8b62, routes=158, stops=3741, hubs=426 |
| `agency_meta` | `/content/drive/MyDrive/Hubs_Oct_26/data/Minhal/MT_Network_MetaData.xlsx` | file=MT_Network_MetaData.xlsx, sha256=7674328399f421a6d5db9d1f6380f4849eaf3cccc6b1745f137771dac0166d30, labels=2 |

## Metrics

- **offset_pairs**: 974
- **offset_estimated**: True
- **offset_global_dx_m**: -56.012
- **offset_global_dy_m**: -36.898
- **offset_max_shift_m**: 136.264
- **routes_matched**: 25
- **routes_split_merge**: 49
- **routes_partial**: 4
- **routes_ours_within_agency**: 15
- **routes_agency_within_ours**: 7
- **routes_weak**: 22
- **routes_mode_differs**: 15
- **routes_ours_only**: 10
- **routes_agency_only**: 92
- **routes_covered**: 14
- **routes_ours**: 147
- **routes_agency**: 158
- **route_pairs**: 391
- **routes_short**: 1
- **hubs_1:1**: 161
- **hubs_agency_splits**: 78
- **hubs_ours_merges**: 35
- **hubs_many_to_many**: 257
- **hubs_agency_only**: 68
- **hubs_ours_only**: 649
- **hubs_ours_only_eligible**: 67
- **hubs_agency**: 426
- **hubs_ours**: 1042

## Findings (0 errors, 1 warnings)

### agency

- · 158 routes (11 without stations), 3741 stops, 426 hubs

### offset

- · global shift (-56.0, -36.9) m from 1321 nodes and 3741 agency stops; local shifts up to 136.3 m `{"nodes_left_out": 0}`

### routes

- · 147 routes of ours vs 158 agency routes (391 candidate pairs): 25 matched, 49 split_merge, 4 partial, 15 ours_within_agency, 7 agency_within_ours, 22 weak, 15 mode_differs, 10 ours_only, 92 agency_only, 14 covered `{"short_routes": 1}`

### hubs

- · 426 agency hubs vs 1042 groups of ours: 161 1:1, 78 agency_splits, 35 ours_merges, 257 many_to_many, 68 agency_only, 649 ours_only rows (67 of the ours_only groups are scored hubs)

### compare

- ⚠ mode(s) without an agency counterpart: Cable Line
