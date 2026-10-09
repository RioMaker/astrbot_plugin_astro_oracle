"""读取真实 JPL SPK，计算日心几何状态与地心视坐标。"""

import hashlib
import json
from importlib.metadata import version
from pathlib import Path

import numpy as np
from skyfield.api import load, load_file
from skyfield.errors import EphemerisRangeError
from skyfield.framelib import ecliptic_frame

from . import CORE_VERSION
from .resources import DATA_DIR, MODEL_FILENAME, sha256_file
from .time_input import parse_time_input

PLANETS = (
    ("mercury", "水星", 199, "body_center"),
    ("venus", "金星", 299, "body_center"),
    ("earth", "地球", 399, "body_center"),
    ("mars", "火星", 4, "system_barycenter"),
    ("jupiter", "木星", 5, "system_barycenter"),
    ("saturn", "土星", 6, "system_barycenter"),
    ("uranus", "天王星", 7, "system_barycenter"),
    ("neptune", "海王星", 8, "system_barycenter"),
)


class PlanetEngine:
    """可独立于消息平台使用；初始化后查询不访问网络。"""

    def __init__(self, data_dir: Path = DATA_DIR):
        self.path = data_dir / MODEL_FILENAME
        manifest_path = data_dir / "ephemeris.json"
        if not self.path.exists() or not manifest_path.exists():
            raise ValueError(
                "历表尚未准备，请运行 .venv/Scripts/python.exe -m local_core.resources。"
            )
        self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if self.manifest.get("sha256") != sha256_file(self.path):
            raise ValueError("历表 SHA-256 与来源记录不符，未执行计算。")
        self.kernel = load_file(str(self.path))
        try:
            self.targets = {key: self.kernel[identifier] for key, _, identifier, _ in PLANETS}
            self.sun = self.kernel[10]
            self.earth = self.kernel[399]
            self.ts = load.timescale(builtin=True)
            self.lower_jd = max(s.spk_segment.start_jd for s in self.kernel.segments)
            self.upper_jd = min(s.spk_segment.end_jd for s in self.kernel.segments)
            self.coverage = {
                "start_utc": self.ts.tdb_jd(self.lower_jd).utc_iso(),
                "end_utc": self.ts.tdb_jd(self.upper_jd).utc_iso(),
                "time_scale": "TDB",
                "start_jd": self.lower_jd,
                "end_jd": self.upper_jd,
            }
            code = b"\0".join(
                (Path(__file__).parent / name).read_bytes()
                for name in ("engine.py", "time_input.py", "resources.py")
            )
            self.provenance = {
                "core_version": CORE_VERSION,
                "algorithm_sha256": hashlib.sha256(code).hexdigest(),
                "ephemeris": self.manifest,
                "libraries": {
                    name: version(name) for name in ("skyfield", "jplephem", "numpy", "tzdata")
                },
                "time_model": "Skyfield packaged timescale data; builtin=True",
            }
        except Exception:
            self.kernel.close()
            raise

    def close(self) -> None:
        self.kernel.close()

    def info(self) -> dict:
        return {
            "app": "astro_oracle",
            "core_version": CORE_VERSION,
            "model": "JPL DE440s",
            "coverage": self.coverage,
            "planets": [
                {"key": key, "name": name, "naif_id": identifier, "target_kind": kind}
                for key, name, identifier, kind in PLANETS
            ],
            "definitions": {
                "heliocentric": "太阳中心，ICRF 固定轴，几何位置与速度；不做光行时修正。",
                "geocentric": "地球中心视位置，含光行时、光行差及引力偏折修正。",
                "ecliptic": "日期真黄道与真春分点；经纬度单位为度。",
                "equatorial": "日期真赤道与真春分点；赤经赤纬单位为度。",
                "target_kind": "火星及外行星使用其行星系统质心，明确区别于行星本体中心。",
            },
            "provenance": self.provenance,
        }

    def compute(self, value: str, timezone_name: str = "Asia/Shanghai", samples: int = 7) -> dict:
        window = parse_time_input(value, timezone_name)
        moments = window.samples(samples)
        times = self.ts.from_datetimes(moments)
        end = self.ts.from_datetime(window.start if window.is_instant else window.end)
        if float(times.tdb[0]) < self.lower_jd or float(end.tdb) >= self.upper_jd:
            raise ValueError(
                f"输入超出当前历表覆盖：{self.coverage['start_utc']} 至 "
                f"{self.coverage['end_utc']}。可换用更长历表，当前未外推。"
            )
        snapshots = [
            {
                "local_time": moment.astimezone(window.zone).isoformat(),
                "utc": moment.isoformat(),
                "tt_jd": float(times.tt[index]),
                "tdb_jd": float(times.tdb[index]),
                "planets": [],
            }
            for index, moment in enumerate(moments)
        ]
        try:
            observer = self.earth.at(times)
            for key, name, identifier, kind in PLANETS:
                target = self.targets[key]
                heliocentric = (target - self.sun).at(times)
                positions = heliocentric.position.au
                velocities = heliocentric.velocity.km_per_s
                distances = np.linalg.norm(positions, axis=0)
                speeds = np.linalg.norm(velocities, axis=0)
                if key != "earth":
                    apparent = observer.observe(target).apparent()
                    ra, dec, _ = apparent.radec(epoch="date")
                    lat, lon, distance = apparent.frame_latlon(ecliptic_frame)
                for index, snapshot in enumerate(snapshots):
                    snapshot["planets"].append(
                        {
                            "key": key,
                            "name": name,
                            "naif_id": identifier,
                            "target_kind": kind,
                            "heliocentric": {
                                "frame": "ICRF",
                                "position_au": positions[:, index].tolist(),
                                "velocity_km_s": velocities[:, index].tolist(),
                                "distance_au": float(distances[index]),
                                "speed_km_s": float(speeds[index]),
                            },
                            "geocentric_apparent": None
                            if key == "earth"
                            else {
                                "ecliptic_longitude_deg": float(lon.degrees[index]),
                                "ecliptic_latitude_deg": float(lat.degrees[index]),
                                "right_ascension_deg": float(ra.degrees[index]),
                                "declination_deg": float(dec.degrees[index]),
                                "distance_au": float(distance.au[index]),
                                "frame": "true_ecliptic/equator_and_equinox_of_date",
                            },
                        }
                    )
        except EphemerisRangeError as exc:
            raise ValueError("光行时修正触及历表边界，请选取覆盖区间内稍远离边界的日期。") from exc
        notes = [
            "输入分辨率与模型精度分别记录；本程序未给出历表物理误差的统一保证。",
            "离散采样展示时段变化，不构成连续变化的严格上下界。",
            "地球没有相对自身的地心视坐标，相关字段为 null。",
        ]
        if window.start.year < 1970:
            notes.append("历史民用时区与早期 UTC 换算依赖模型；请核对当地记录与显式 UTC 偏移。")
        return {
            "schema_version": 1,
            "window": window.as_dict(),
            "sample_count": len(snapshots),
            "snapshots": snapshots,
            "definitions": self.info()["definitions"],
            "provenance": self.provenance,
            "notes": notes,
        }
