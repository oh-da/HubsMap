# Shared map layers

GeoJSON files in this folder are **shared, built-in layers** — every viewer of
the dashboard sees them as toggles under *שכבות רקע* (Layers) in the side rail.
This is different from the in-app "טען שכבת GeoJSON" upload, which stays in one
person's browser only.

## Add a layer (3 steps)

1. **Convert your data to GeoJSON in WGS84 (EPSG:4326).** Leaflet needs lon/lat.
   Israeli shapefiles are usually in ITM (EPSG:2039), so reproject:

   ```bash
   # Shapefile (.shp) -> GeoJSON, reprojected to WGS84
   ogr2ogr -f GeoJSON -t_srs EPSG:4326 layers/my_layer.geojson path/to/my_layer.shp

   # Optional: shrink big files (keeps ~15% of vertices)
   npx mapshaper layers/my_layer.geojson -simplify 15% keep-shapes \
       -o force layers/my_layer.geojson
   ```

   No CLI? Use <https://mapshaper.org> — drag in all the shapefile parts
   (`.shp`, `.dbf`, `.shx`, `.prj`), then Export → GeoJSON.

2. **Drop the `.geojson` file in this folder.**

3. **Register it** by adding an entry to [`layers.json`](./layers.json):

   ```json
   {
     "id": "rail_2050",
     "name": "קווי רכבת 2050",
     "file": "rail_2050.geojson",
     "color": "#B0432B",
     "visible": false
   }
   ```

   | field | meaning |
   |-------|---------|
   | `id` | unique short id (any string) |
   | `name` | label shown in the rail (Hebrew is fine) |
   | `file` | the file name in this folder |
   | `color` | line/point color and polygon fill tint (hex) |
   | `visible` | `true` = on by default, `false` = off until toggled |

Commit and push — GitHub Pages redeploys automatically.

## Notes

- Lines and points render in the chosen color; polygons get a light fill of the
  same color. Reproject to **EPSG:4326** or features land in the wrong place.
- Keep files reasonably small (simplify large geometries) so the map stays fast.
