"""Gamma dose rate (ODL) from the German federal radiation network (BfS ODL-Messnetz) for the mesh.

Source: the BfS open-data WFS, layer ``opendata:odlinfo_odl_1h_latest`` - the latest 1-hour mean of every station in
a bounding box (GeoJSON; properties ``name``, ``kenn``, ``plz``, ``value`` in µSv/h, ``end_measure`` UTC,
``site_status`` 1 = in operation). Normal values in the Saarland are about 0.07-0.13 µSv/h; rain washes radon
products out of the air and can double that for an hour or two, which is not a reason for concern.

The bounding box is set on the odl card (``lat_min,lon_min,lat_max,lon_max``; default the Saarland with the border
area). Ported from the SaarMesh bot's radiation watch (saarmesh.de). Nothing here talks to the network.
"""
from __future__ import annotations

import re
import statistics
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Any, Optional

WFS = ("https://www.imis.bfs.de/ogc/opendata/ows?service=WFS&version=1.1.0&request=GetFeature"
       "&outputFormat=application/json&typeName=opendata:odlinfo_odl_1h_latest"
       "&bbox={bbox},urn:ogc:def:crs:EPSG::4326")
DEFAULT_BBOX = "49.10,6.30,49.65,7.45"
STALE_H = 3


def parse_bbox(text: str) -> str:
    """'49.1, 6.3, 49.65, 7.45' -> '49.1,6.3,49.65,7.45'; anything else -> the default."""
    try:
        vals = [float(v) for v in re.split(r"[,;\s]+", (text or "").strip()) if v]
    except ValueError:
        return DEFAULT_BBOX
    if len(vals) != 4 or not (vals[0] < vals[2] and vals[1] < vals[3]):
        return DEFAULT_BBOX
    return ",".join(f"{v:g}" for v in vals)


def stations(data: Any, now: datetime, tz: Optional[tzinfo] = None) -> list:
    """[{name, plz, value, time}] of the stations in operation with a fresh value, highest first."""
    out = []
    feats = data.get("features") if isinstance(data, dict) else None
    for f in feats if isinstance(feats, list) else []:
        p = (f or {}).get("properties") or {}
        if p.get("site_status") not in (None, 1):
            continue
        try:
            value = float(p.get("value"))
            t = datetime.strptime(str(p.get("end_measure")), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue
        if now - t > timedelta(hours=STALE_H):
            continue
        out.append({"name": str(p.get("name") or p.get("kenn") or "?"), "plz": str(p.get("plz") or ""),
                    "value": value, "time": t.astimezone(tz or now.tzinfo or timezone.utc)})
    out.sort(key=lambda s: (-s["value"], s["name"]))
    return out


def find(stations_: list, query: str) -> list:
    """Stations whose name contains the query (case-insensitive) or whose postcode starts with it."""
    q = (query or "").strip().lower()
    if not q:
        return []
    return [s for s in stations_ if q in s["name"].lower() or (q.isdigit() and s["plz"].startswith(q))]


def summary(stations_: list) -> Optional[dict]:
    if not stations_:
        return None
    vals = [s["value"] for s in stations_]
    top = stations_[0]
    return {"count": len(vals), "median": statistics.median(vals), "max": top["value"], "max_name": top["name"],
            "time": max(s["time"] for s in stations_)}


def usv(v: float, decimal: str = ",") -> str:
    return f"{v:.3f}".replace(".", decimal)
