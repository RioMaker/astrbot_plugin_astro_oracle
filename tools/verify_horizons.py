"""将真实本地计算与 JPL Horizons 逐目标、逐时刻核对，保存完整响应。"""

import argparse
import asyncio
import csv
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np

from local_core.engine import PlanetEngine

API = "https://ssd.jpl.nasa.gov/api/horizons.api"
OUTPUT = Path(__file__).resolve().parents[1] / "data" / "horizons-validation"
EPOCHS = ("2000-01-01 12:00:00", "2026-10-09 12:34:56")


async def query(client, parameters, filename, refresh):
    path = OUTPUT / filename
    if path.exists() and not refresh:
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["parameters"] == parameters:
            return record
    response = await client.get(API, params=parameters)
    response.raise_for_status()
    payload = response.json()
    if "error" in payload or "$$SOE" not in payload.get("result", ""):
        raise ValueError(f"Horizons 未返回预期状态：{payload}")
    record = {
        "url": API,
        "parameters": parameters,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "response": payload,
    }
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    await asyncio.sleep(0.25)
    return record


def data_row(record):
    result = record["response"]["result"]
    body = result.split("$$SOE", 1)[1].split("$$EOE", 1)[0].strip()
    rows = list(csv.reader(io.StringIO(body)))
    if len(rows) != 1:
        raise ValueError("预期单一时刻，Horizons 返回了不同数量的记录。")
    return [value.strip() for value in rows[0]]


async def verify(refresh=False):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    engine = PlanetEngine()
    checks = []
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            for epoch_index, epoch in enumerate(EPOCHS):
                snapshot = engine.compute(epoch, "UTC")["snapshots"][0]
                for body in snapshot["planets"]:
                    common = {
                        "format": "json",
                        "COMMAND": f"'{body['naif_id']}'",
                        "OBJ_DATA": "'NO'",
                        "MAKE_EPHEM": "'YES'",
                        "REF_SYSTEM": "'ICRF'",
                        "CSV_FORMAT": "'YES'",
                        "TLIST_TYPE": "'JD'",
                        "EXTRA_PREC": "'YES'",
                    }
                    parameters = dict(
                        common,
                        EPHEM_TYPE="'VECTORS'",
                        CENTER="'500@10'",
                        TIME_TYPE="'TDB'",
                        TLIST=f"'{snapshot['tdb_jd']:.15f}'",
                        REF_PLANE="'FRAME'",
                        OUT_UNITS="'KM-S'",
                        VEC_CORR="'NONE'",
                        VEC_TABLE="'2'",
                    )
                    record = await query(
                        client, parameters, f"vectors-{epoch_index}-{body['naif_id']}.json", refresh
                    )
                    row = data_row(record)
                    assert abs(float(row[0]) - snapshot["tdb_jd"]) < 1e-7
                    reference = np.array([float(value) for value in row[2:8]])
                    local = np.array(body["heliocentric"]["position_au"]) * 149597870.7
                    velocity = np.array(body["heliocentric"]["velocity_km_s"])
                    position_error = float(np.max(np.abs(local - reference[:3])))
                    velocity_error = float(np.max(np.abs(velocity - reference[3:])))
                    assert position_error < 1.0, (body["key"], position_error)
                    assert velocity_error < 1e-5, (body["key"], velocity_error)
                    models = sorted(
                        set(re.findall(r"source: (DE\d+)", record["response"]["result"]))
                    )
                    checks.append(
                        {
                            "kind": "vectors",
                            "epoch_utc": epoch,
                            "planet": body["key"],
                            "naif_id": body["naif_id"],
                            "reference_models": models,
                            "max_position_component_error_km": position_error,
                            "max_velocity_component_error_km_s": velocity_error,
                            "retrieved_at_utc": record["retrieved_at_utc"],
                        }
                    )
                    print(f"PASS vector {epoch} {body['key']}: {position_error:.6g} km", flush=True)
                    if body["key"] not in {"mercury", "mars"}:
                        continue
                    parameters = dict(
                        common,
                        EPHEM_TYPE="'OBSERVER'",
                        CENTER="'500@399'",
                        TIME_TYPE="'TT'",
                        TLIST=f"'{snapshot['tt_jd']:.15f}'",
                        QUANTITIES="'2,20,31'",
                        ANG_FORMAT="'DEG'",
                        APPARENT="'AIRLESS'",
                        CAL_FORMAT="'JD'",
                        TIME_DIGITS="'FRACSEC'",
                    )
                    record = await query(
                        client,
                        parameters,
                        f"observer-{epoch_index}-{body['naif_id']}.json",
                        refresh,
                    )
                    row = data_row(record)
                    assert abs(float(row[0]) - snapshot["tt_jd"]) < 1e-7
                    geo = body["geocentric_apparent"]
                    local_angles = np.array(
                        [
                            geo["right_ascension_deg"],
                            geo["declination_deg"],
                            geo["ecliptic_longitude_deg"],
                            geo["ecliptic_latitude_deg"],
                        ]
                    )
                    reference_angles = np.array([float(row[index]) for index in (3, 4, 7, 8)])
                    angle_error = float(
                        np.max(np.abs((local_angles - reference_angles + 180) % 360 - 180)) * 3600
                    )
                    distance_error = abs(geo["distance_au"] - float(row[5])) * 149597870.7
                    assert angle_error < 0.5, (body["key"], angle_error)
                    assert distance_error < 1.0, (body["key"], distance_error)
                    checks.append(
                        {
                            "kind": "observer",
                            "epoch_utc": epoch,
                            "planet": body["key"],
                            "max_angle_error_arcsec": angle_error,
                            "distance_error_km": distance_error,
                            "retrieved_at_utc": record["retrieved_at_utc"],
                        }
                    )
                    print(f"PASS apparent {body['key']}: {angle_error:.6g} arcsec", flush=True)
        report = {
            "verified_at_utc": datetime.now(timezone.utc).isoformat(),
            "local_provenance": engine.provenance,
            "cases": checks,
            "thresholds": {
                "vector_component_km": 1.0,
                "velocity_component_km_s": 1e-5,
                "apparent_angle_arcsec": 0.5,
                "apparent_distance_km": 1.0,
            },
            "limits": [
                "Two epochs, not a precision certificate for the whole ephemeris range.",
                "Local DE440s and Horizons DE441 share JPL lineage.",
                "Apparent frame algorithms differ (IAU model conventions); "
                "tolerances are comparison gates.",
            ],
        }
        (OUTPUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"PASS: {len(checks)} live/cached JPL reference cases; report saved.", flush=True)
    finally:
        engine.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JPL Horizons 交叉核对")
    parser.add_argument("--refresh", action="store_true", help="重新获取已缓存的官方响应")
    asyncio.run(verify(parser.parse_args().refresh))
