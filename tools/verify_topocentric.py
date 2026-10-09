"""用 JPL Horizons AIRLESS 站心方位/高度核对出生地视角。"""

import asyncio
import csv
import io
import json
from datetime import datetime
from pathlib import Path

import httpx

from local_core.engine import PlanetEngine
from local_core.sky_chart import SkyChartEngine

OUTPUT = Path(__file__).resolve().parents[1] / "data" / "sky-validation"
CASES = [
    ("2026-10-08T16:00:00+00:00", 31.22222, 121.45806, 199),
    ("2026-10-08T16:00:00+00:00", 31.22222, 121.45806, 6),
    ("2000-01-01T12:00:00+00:00", 40.7128, -74.006, 199),
]


async def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    core = PlanetEngine()
    sky = SkyChartEngine(core)
    reports = []
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(90, connect=20)) as client:
            for index, (epoch, latitude, longitude, target) in enumerate(CASES):
                scene = sky.compute(epoch, {"latitude": latitude, "longitude": longitude})
                planet = next(
                    p
                    for half in scene["hemispheres"].values()
                    for p in half["planets"]
                    if p["naif_id"] == target
                )
                t = core.ts.from_datetime(datetime.fromisoformat(epoch))
                parameters = {
                    "format": "json",
                    "COMMAND": f"'{target}'",
                    "OBJ_DATA": "'NO'",
                    "MAKE_EPHEM": "'YES'",
                    "EPHEM_TYPE": "'OBSERVER'",
                    "CENTER": "'coord@399'",
                    "COORD_TYPE": "'GEODETIC'",
                    "SITE_COORD": f"'{longitude},{latitude},0'",
                    "TIME_TYPE": "'TT'",
                    "TLIST_TYPE": "'JD'",
                    "TLIST": f"'{float(t.tt):.15f}'",
                    "QUANTITIES": "'4'",
                    "ANG_FORMAT": "'DEG'",
                    "APPARENT": "'AIRLESS'",
                    "CAL_FORMAT": "'JD'",
                    "CSV_FORMAT": "'YES'",
                    "EXTRA_PREC": "'YES'",
                    "REF_SYSTEM": "'ICRF'",
                }
                path = OUTPUT / f"topocentric-{index}.json"
                cached = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
                if cached and cached["parameters"] == parameters:
                    data = cached["response"]
                else:
                    for attempt in range(3):
                        try:
                            response = await client.get(
                                "https://ssd.jpl.nasa.gov/api/horizons.api", params=parameters
                            )
                            break
                        except (httpx.ConnectTimeout, httpx.ReadTimeout):
                            if attempt == 2:
                                raise
                            print("JPL 连接超时，稍后重试。", flush=True)
                            await asyncio.sleep(2)
                    response.raise_for_status()
                    data = response.json()
                    path.write_text(
                        json.dumps({"parameters": parameters, "response": data}, indent=2),
                        encoding="utf-8",
                    )
                text = data.get("result", "")
                if "$$SOE" not in text:
                    raise ValueError(str(data))
                body = text.split("$$SOE", 1)[1].split("$$EOE", 1)[0].strip()
                row = next(csv.reader(io.StringIO(body)))
                azimuth, altitude = float(row[3]), float(row[4])
                az_error = abs((planet["azimuth_deg"] - azimuth + 180) % 360 - 180) * 3600
                alt_error = abs(planet["altitude_deg"] - altitude) * 3600
                assert max(az_error, alt_error) < 5, (index, az_error, alt_error)
                reports.append(
                    {
                        "epoch_utc": epoch,
                        "latitude": latitude,
                        "longitude": longitude,
                        "naif_id": target,
                        "azimuth_error_arcsec": az_error,
                        "altitude_error_arcsec": alt_error,
                    }
                )
                print(
                    f"PASS site {latitude},{longitude} target {target}: "
                    f"{az_error:.5g}/{alt_error:.5g} arcsec",
                    flush=True,
                )
                await asyncio.sleep(0.25)
        (OUTPUT / "topocentric-report.json").write_text(
            json.dumps(
                {"cases": reports, "threshold_arcsec": 5, "provenance": scene["provenance"]},
                indent=2,
            ),
            encoding="utf-8",
        )
    finally:
        core.close()


if __name__ == "__main__":
    asyncio.run(main())
