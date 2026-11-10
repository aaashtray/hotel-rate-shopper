"""Check the exact static artifacts before deploying them. Uses Python stdlib only."""
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

site = Path(__file__).resolve().parents[1] / "site"
report = json.loads((site / "report.json").read_text())
assert report["publication"]["scope"] in {"public_only", "all_collected_prices"}
assert report["metrics"]["extracted_offers"] == len(report["offers"])
assert all(o["access_type"] in {"public", "personal", "corporate", "bank", "mobile", "member"}
           for o in report["offers"])
public_ids = {o["id"] for o in report["offers"] if o["access_type"] == "public"
              and o["authorization_required"] is False and o["public_total"] is not None}
for row in report["statistics"]["rows"] + report["statistics"]["verified_rows"]:
    assert all(row[k] is None or row[k] in public_ids
               for k in ("reference_offer_id", "competitor_offer_id"))
if report["publication"]["public_only"]:
    assert len(public_ids) == len(report["offers"])
for name in ("index.html", "hotel-interface-otello.html", "hotel-statistics-otello.html"):
    html = (site / name).read_text()
    match = re.search(r'<script type="application/json" id="data">(.*?)</script>', html, re.S)
    assert match and json.loads(match[1]) == report, f"Stale data: {name}"
    assert "/Users/" not in html and "evidence/" not in html
    for href in re.findall(r'(?:href|src)=[\'"]([^\'"]+)', html.split('<script')[0]):
        if href.startswith(("data:", "https:", "http:", "#")):
            continue
        assert (site / href).is_file(), f"Broken local resource: {name} -> {href}"
allowed = {"assets", "index.html", "hotel-interface-otello.html", "hotel-statistics-otello.html",
           "парсер цен.html", "hotel-rates.xlsx", "report.json", ".nojekyll"}
assert not (set(p.name for p in site.iterdir()) - allowed), "Unexpected publish artifact"
with zipfile.ZipFile(site / "hotel-rates.xlsx") as z:
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    cell = sheet.find('.//x:c[@r="B7"]/x:v', ns)
    assert cell is not None and int(float(cell.text)) == len(report["offers"]), "Stale Excel"
    for name in z.namelist():
        if name.startswith("xl/worksheets/") and name.endswith(".xml"):
            assert not ET.fromstring(z.read(name)).findall('.//x:c[@t="e"]', ns)
print(f"Static release valid: {len(report['offers'])} offers; HTML and Excel agree")
