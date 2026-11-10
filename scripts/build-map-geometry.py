# /// script
# requires-python = ">=3.12"
# dependencies = ["pyshp==3.1.8", "shapely==2.2.0", "pyproj==3.8.0"]
# ///
"""Build offline SVG geometry from pinned Natural Earth 5.1.1 archives.

Run with `uv run scripts/build-map-geometry.py --cache /path/to/cache`.
No statistical values are stored here. Natural Earth's source borders are retained;
projection and simplification only serve rendering. The Moscow city/oblast ISO
codes are interchanged in this source release, so internal IDs are corrected by
feature name while sourceId preserves the source value.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile

import shapefile
from pyproj import Transformer
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.ops import transform

SOURCES = {
    "world": {
        "stem": "ne_50m_admin_0_countries",
        "url": "https://naturalearth.s3.amazonaws.com/50m_cultural/ne_50m_admin_0_countries.zip",
        "sha256": "5fed433373581fa648920435f937d95f2d3c0200e067409c6478dcdf1b853139",
        "page": "https://www.naturalearthdata.com/downloads/50m-cultural-vectors/50m-admin-0-countries-2/",
    },
    "russia": {
        "stem": "ne_10m_admin_1_states_provinces",
        "url": "https://naturalearth.s3.amazonaws.com/10m_cultural/ne_10m_admin_1_states_provinces.zip",
        "sha256": "efc59726337323058f9446210adc96673179cd344e053666ee3d28cb58ba2b05",
        "page": "https://www.naturalearthdata.com/downloads/10m-cultural-vectors/10m-admin-1-states-provinces/",
    },
}


def features(kind: str, cache: Path) -> list[tuple[dict, Polygon | MultiPolygon]]:
    source = SOURCES[kind]
    archive = cache / (source["stem"] + ".zip")
    if not archive.exists():
        with urlopen(source["url"], timeout=90) as response:
            archive.write_bytes(response.read())
    data = archive.read_bytes()
    if hashlib.sha256(data).hexdigest() != source["sha256"]:
        raise ValueError(f"Unexpected archive revision: {source['url']}")
    with ZipFile(io.BytesIO(data)) as zip_file:
        stem = source["stem"]
        reader = shapefile.Reader(
            shp=io.BytesIO(zip_file.read(stem + ".shp")),
            shx=io.BytesIO(zip_file.read(stem + ".shx")),
            dbf=io.BytesIO(zip_file.read(stem + ".dbf")),
            encoding="utf-8",
        )
        result = []
        for feature in reader.iterShapeRecords():
            properties = feature.record.as_dict()
            if kind == "world" and properties["ADM0_A3"] == "ATA":
                continue
            if kind == "russia" and properties["adm0_a3"] != "RUS":
                continue
            result.append((properties, shape(feature.shape.__geo_interface__)))
        return result


def build_map(kind: str, cache: Path) -> dict:
    projection = (
        "+proj=eqearth +lon_0=0 +datum=WGS84 +units=m"
        if kind == "world" else
        "+proj=aea +lat_1=50 +lat_2=70 +lat_0=60 +lon_0=100 +datum=WGS84 +units=m"
    )
    projector = Transformer.from_crs("EPSG:4326", projection, always_xy=True)
    tolerance = 12000 if kind == "world" else 5000
    projected = [
        (properties, transform(projector.transform, geometry).simplify(
            tolerance, preserve_topology=True
        ))
        for properties, geometry in features(kind, cache)
    ]
    minx = min(geometry.bounds[0] for _, geometry in projected)
    miny = min(geometry.bounds[1] for _, geometry in projected)
    maxx = max(geometry.bounds[2] for _, geometry in projected)
    maxy = max(geometry.bounds[3] for _, geometry in projected)
    width, height, padding = 1000, 560, 24
    scale = min((width - 2 * padding) / (maxx - minx),
                (height - 2 * padding) / (maxy - miny))
    offset_x = (width - (maxx - minx) * scale) / 2
    offset_y = (height - (maxy - miny) * scale) / 2

    def point(x: float, y: float) -> list[float]:
        return [round(offset_x + (x - minx) * scale, 1),
                round(offset_y + (maxy - y) * scale, 1)]

    def path_data(geometry: Polygon | MultiPolygon) -> str:
        polygons = [geometry] if isinstance(geometry, Polygon) else geometry.geoms
        chunks = []
        for polygon in polygons:
            for ring in (polygon.exterior, *polygon.interiors):
                points = [point(x, y) for x, y in ring.coords]
                chunks.append("M" + "L".join(
                    f"{x:g},{y:g}" for x, y in points[:-1]
                ) + "Z")
        return "".join(chunks)

    regions = []
    for properties, geometry in projected:
        if kind == "world":
            source_id = properties["ISO_A3"]
            region_id = source_id if source_id != "-99" else properties["ADM0_A3"]
            name = properties["NAME_RU"] or properties["NAME_LONG"]
        else:
            source_id = properties["iso_3166_2"]
            region_id = source_id
            if properties["name"] == "Moskva":
                region_id = "RU-MOW"
            elif properties["name"] == "Moskovskaya":
                region_id = "RU-MOS"
            name = properties["name_ru"] or properties["name_local"] or properties["name"]
            # The source has one unnamed Arctic island feature. Keep its geometry
            # and source identifier without pretending it is a named subdivision.
            name = name or "Территория без названия в Natural Earth"
            if region_id == "RU-ALT":
                name = "Алтайский край"  # Source name_ru repeats the republic.
        anchor = geometry.representative_point()
        item = {
            "id": region_id,
            "sourceId": source_id,
            "name": name,
            "path": path_data(geometry),
            "anchor": point(anchor.x, anchor.y),
            "tiny": region_id in {"MDV", "RU-MOW", "RU-SPE"},
        }
        if region_id in {"MDV", "RU-MOW", "RU-SPE"}:
            item["labelOffset"] = {
                "MDV": [28, 22], "RU-MOW": [-90, 35], "RU-SPE": [-75, -25],
            }[region_id]
        regions.append(item)
    regions.sort(key=lambda item: item["id"])
    if len({item["id"] for item in regions}) != len(regions):
        raise ValueError(f"Duplicate IDs in {kind}")
    return {
        "viewBox": f"0 0 {width} {height}",
        "projection": "Equal Earth" if kind == "world" else "Albers equal-area, 100°E",
        "fillRule": "evenodd",
        "regions": regions,
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=root / ".map-cache")
    parser.add_argument("--output", type=Path,
                        default=root / "src/rate_shopper/reporting/map-geometry.json")
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    result = {kind: build_map(kind, args.cache) for kind in SOURCES}
    result["attribution"] = {
        "name": "Natural Earth",
        "version": "5.1.1",
        "license": "Public domain",
        "licenseUrl": "https://www.naturalearthdata.com/about/terms-of-use/",
        "url": "https://www.naturalearthdata.com/",
        "sources": SOURCES,
        "boundaryNote": "Границы Natural Earth 5.1.1; картографическая подложка источника.",
        "processing": "Projection, topology-preserving simplification, Antarctica omitted. "
                      "Moscow city/oblast internal IDs normalized by source feature name; "
                      "original IDs remain in sourceId. Source boundaries are not reassigned.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"{args.output}: {args.output.stat().st_size:,} bytes")
    print({kind: len(result[kind]["regions"]) for kind in SOURCES})


if __name__ == "__main__":
    main()
