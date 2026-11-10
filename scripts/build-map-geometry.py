# /// script
# requires-python = ">=3.12"
# dependencies = ["pyshp==3.1.8", "shapely==2.2.0", "pyproj==3.8.0"]
# ///
"""Build offline SVG geometry from pinned Natural Earth 5.1.1 archives.

Run with `uv run scripts/build-map-geometry.py --cache /path/to/cache`.
No statistical values are stored here. Ukraine is shown within its internationally
recognized borders. Crimea and Sevastopol are reassigned from Natural Earth's
Russia geometry to Ukraine; already-Ukrainian regions are retained. The Moscow city/oblast ISO
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
from shapely.geometry import MultiPolygon, Point, Polygon, shape
from shapely.ops import transform, unary_union

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

# Natural Earth 5.1.1 already places the latter four regions in Ukraine.
UKRAINE_REGION_IDS = {"UA-43", "UA-40", "UA-14", "UA-09", "UA-23", "UA-65"}
UKRAINE_CHECK_POINTS = {
    "Crimea (Simferopol)": (34.10, 44.95),
    "Sevastopol": (33.54, 44.60),
    "Donetsk": (37.80, 48.02),
    "Luhansk": (39.31, 48.57),
    "Kherson": (32.62, 46.64),
    "Zaporizhzhia": (35.14, 47.84),
}
RUSSIA_CHECK_POINTS = {"Moscow": (37.617, 55.755), "Saint Petersburg": (30.335, 59.934)}


def source_features(kind: str, cache: Path) -> list[tuple[dict, Polygon | MultiPolygon]]:
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
            if kind == "russia" and properties["adm0_a3"] not in {"RUS", "UKR"}:
                continue
            result.append((properties, shape(feature.shape.__geo_interface__)))
        return result


def features(kind: str, cache: Path) -> list[tuple[dict, Polygon | MultiPolygon]]:
    """Apply the requested boundary presentation before projection/simplification."""
    subdivisions = source_features("russia", cache)
    if kind == "russia":
        return [(p, g) for p, g in subdivisions
                if p["adm0_a3"] == "RUS" and p["iso_3166_2"] not in UKRAINE_REGION_IDS]

    countries = source_features("world", cache)
    source_russia = next(g for p, g in countries if p["ADM0_A3"] == "RUS")
    source_ukraine = next(g for p, g in countries if p["ADM0_A3"] == "UKR")
    # Use actual admin-1 boundaries to identify the detached Crimea polygon in
    # the 50m layer. Transfer that complete 50m polygon, not a clipped 10m coast:
    # mixing coastline resolutions would leave narrow Russian coastal slivers.
    correction_mask = unary_union([
        g for p, g in subdivisions
        if p["iso_3166_2"] in UKRAINE_REGION_IDS and p["adm0_a3"] == "RUS"
    ])
    transferred = [polygon for polygon in source_russia.geoms
                   if polygon.intersection(correction_mask).area / polygon.area > .90]
    if len(transferred) != 1:
        raise ValueError("Pinned source no longer contains one detached Crimea polygon")
    transfer = unary_union(transferred)
    if not transfer.covers(Point(UKRAINE_CHECK_POINTS["Crimea (Simferopol)"])):
        raise ValueError("Crimea transfer failed its geographic control point")
    russia = source_russia.difference(transfer)
    ukraine = source_ukraine.union(transfer)
    if not russia.is_valid or not ukraine.is_valid or russia.intersection(ukraine).area > 1e-10:
        raise ValueError("Invalid or overlapping Russia/Ukraine geometries")
    result = [(p, russia if p["ADM0_A3"] == "RUS" else
               ukraine if p["ADM0_A3"] == "UKR" else g) for p, g in countries]
    for name, coordinates in UKRAINE_CHECK_POINTS.items():
        if not ukraine.covers(Point(coordinates)) or russia.covers(Point(coordinates)):
            raise ValueError(f"Wrong country for {name}")
    for name, coordinates in RUSSIA_CHECK_POINTS.items():
        if not russia.covers(Point(coordinates)) or ukraine.covers(Point(coordinates)):
            raise ValueError(f"Wrong country for {name}")
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
        "boundaryNote": "Украина показана в международно признанных границах, "
                        "включая Крым и Севастополь.",
        "boundaryPolicy": {
            "ukraineRegionIds": sorted(UKRAINE_REGION_IDS),
            "transferredFromSourceRussia": ["UA-43", "UA-40"],
            "alreadyInSourceUkraine": ["UA-14", "UA-09", "UA-23", "UA-65"],
        },
        "processing": "Projection, topology-preserving simplification, Antarctica omitted. "
                      "Moscow city/oblast internal IDs normalized by source feature name; "
                      "original IDs remain in sourceId. Crimea/Sevastopol excluded from the "
                      "Russia regional layer. The corresponding 50m Crimea polygon is identified "
                      "using 10m admin-1 geometry and transferred intact from Russia to Ukraine, "
                      "preserving the world layer's coastline. Other country geometries unchanged.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"{args.output}: {args.output.stat().st_size:,} bytes")
    print({kind: len(result[kind]["regions"]) for kind in SOURCES})


if __name__ == "__main__":
    main()
