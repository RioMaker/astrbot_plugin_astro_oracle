"""出生地站心全天图：同一时刻的上半球和地球遮挡下半球。"""

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from skyfield.api import Star, wgs84
from skyfield.errors import EphemerisRangeError
from skyfield.magnitudelib import planetary_magnitude

from .engine import PLANETS
from .geography import PlaceSearch
from .resources import sha256_file
from .sky_resources import SOURCES, load_dataset
from .time_input import parse_timezone


def project(altitude, azimuth, hemisphere):
    """等距方位投影；天顶/天底在中心，地平线为单位圆。"""
    side = 1 if hemisphere == "upper" else -1
    radius = (90 - side * altitude) / 90
    azimuth = math.radians(azimuth)
    east = -1 if hemisphere == "upper" else 1
    return [east * radius * math.sin(azimuth), -radius * math.cos(azimuth)]


def direction(altitude, azimuth):
    alt, az = math.radians(altitude), math.radians(azimuth)
    return np.array([math.cos(alt) * math.sin(az), math.cos(alt) * math.cos(az), math.sin(alt)])


def clipped_arc(first, second, hemisphere):
    """大圆段按真实地平线裁剪；避免圆外端点的直线穿越造成假连线。"""
    sign = 1 if hemisphere == "upper" else -1
    z1, z2 = sign * first[2], sign * second[2]
    if z1 < 0 and z2 < 0:
        return []
    if z1 < 0 or z2 < 0:
        fraction = z1 / (z1 - z2)
        boundary = first * (1 - fraction) + second * fraction
        boundary /= np.linalg.norm(boundary)
        if z1 < 0:
            first = boundary
        else:
            second = boundary
    result = []
    for fraction in np.linspace(0, 1, 9):
        vector = first * (1 - fraction) + second * fraction
        norm = float(np.linalg.norm(vector))
        if norm < 1e-10:
            return []
        vector /= norm
        alt = math.degrees(math.asin(float(np.clip(vector[2], -1, 1))))
        az = math.degrees(math.atan2(vector[0], vector[1])) % 360
        result.append(project(alt, az, hemisphere))
    return result


def validate_site(site):
    if not isinstance(site, dict):
        raise ValueError("请提供出生地经纬度。")
    values = {}
    for key, low, high, default in (
        ("latitude", -90, 90, None),
        ("longitude", -180, 180, None),
        ("elevation_m", -500, 9000, 0),
    ):
        value = site.get(key, default)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError("出生地坐标必须是有限数值。")
        if not low <= value <= high:
            raise ValueError(f"{key} 超出范围。")
        values[key] = float(value)
    label = site.get("label", "自定义出生地")
    if not isinstance(label, str) or len(label) > 120:
        raise ValueError("地点名称须为不超过 120 字的文本。")
    values["label"] = label.strip()
    return values


class SkyChartEngine:
    def __init__(self, core):
        self.core = core
        directory = core.path.parent / "sky"
        self.manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        culture_path = directory / SOURCES["constellations"][0]
        if sha256_file(culture_path) != self.manifest["sources"]["constellations"]["sha256"]:
            raise ValueError("星座数据校验值不符。")
        self.culture = json.loads(culture_path.read_text(encoding="utf-8"))
        data = load_dataset(directory, self.manifest, "stars")
        self.rows = data["rows"]
        array = np.array([row[:7] for row in self.rows], dtype=float)
        self.ids = array[:, 0].astype(int)
        self.magnitudes = array[:, 1]
        self.stars = Star(
            ra_hours=array[:, 2],
            dec_degrees=array[:, 3],
            parallax_mas=array[:, 4],
            ra_mas_per_year=array[:, 5],
            dec_mas_per_year=array[:, 6],
            epoch=core.ts.J(data["epoch_year"]),
        )
        self.indices = {int(hip): index for index, hip in enumerate(self.ids)}
        self.places = PlaceSearch(directory, self.manifest)
        self.code_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

    def info(self):
        examples = self.places.search("上海")
        return {
            "star_count": len(self.rows),
            "city_count": len(self.places.rows),
            "constellation_count": len(self.culture["constellations"]),
            "example_site": examples[0] if examples else None,
            "credits": self.manifest["credits"],
        }

    def compute(self, epoch, site, timezone_name="Asia/Shanghai", magnitude_limit=6):
        site = validate_site(site)
        if isinstance(magnitude_limit, bool) or not isinstance(magnitude_limit, (int, float)):
            raise ValueError("星等上限必须是数值。")
        if not math.isfinite(magnitude_limit) or not -2 <= magnitude_limit <= 8:
            raise ValueError("星等上限范围为 -2 至 8。")
        if not isinstance(epoch, str) or len(epoch) > 40:
            raise ValueError("请提供带时区的采样时间。")
        try:
            moment = datetime.fromisoformat(epoch.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("采样时间格式不正确。") from exc
        if moment.tzinfo is None:
            raise ValueError("采样时间须包含 UTC 偏移。")
        moment = moment.astimezone(timezone.utc)
        zone = parse_timezone(timezone_name)
        t = self.core.ts.from_datetime(moment)
        if not self.core.lower_jd <= float(t.tdb) < self.core.upper_jd:
            raise ValueError("采样时刻超出当前历表范围。")
        observer = self.core.earth + wgs84.latlon(
            site["latitude"], site["longitude"], elevation_m=site["elevation_m"]
        )
        here = observer.at(t)
        scenes = {
            key: {"stars": [], "planets": [], "constellations": [], "references": []}
            for key in ("upper", "lower")
        }
        try:
            alt, az, _ = here.observe(self.stars).apparent().altaz()
            altitudes, azimuths = alt.degrees, az.degrees
            if not np.isfinite(altitudes).all() or not np.isfinite(azimuths).all():
                raise ValueError("恒星投影产生非有限坐标。")
            for index, row in enumerate(self.rows):
                if row[1] > magnitude_limit:
                    continue
                a, z = float(altitudes[index]), float(azimuths[index])
                hemisphere = "upper" if a >= 0 else "lower"
                scenes[hemisphere]["stars"].append(
                    {
                        "hip": row[0],
                        "magnitude": row[1],
                        "name": row[7],
                        "altitude_deg": a,
                        "azimuth_deg": z,
                        "xy": project(a, z, hemisphere),
                    }
                )
            missing_edges = 0
            for item in self.culture["constellations"]:
                grouped = {"upper": [], "lower": []}
                for line in item["lines"]:
                    for hip1, hip2 in zip(line, line[1:]):
                        if hip1 not in self.indices or hip2 not in self.indices:
                            missing_edges += 1
                            continue
                        i, j = self.indices[hip1], self.indices[hip2]
                        first, second = (
                            direction(altitudes[i], azimuths[i]),
                            direction(altitudes[j], azimuths[j]),
                        )
                        for hemisphere in scenes:
                            arc = clipped_arc(first, second, hemisphere)
                            if arc:
                                grouped[hemisphere].append(arc)
                for hemisphere, lines in grouped.items():
                    if lines:
                        scenes[hemisphere]["constellations"].append(
                            {
                                "abbr": item["id"][-3:],
                                "name": item["common_name"]["native"],
                                "lines": lines,
                            }
                        )
            for key, name, identifier, kind in PLANETS:
                if key == "earth":
                    continue
                astrometric = here.observe(self.core.kernel[identifier])
                alt, az, _ = astrometric.apparent().altaz()
                a, z = float(alt.degrees), float(az.degrees)
                hemisphere = "upper" if a >= 0 else "lower"
                magnitude = float(planetary_magnitude(astrometric))
                magnitude = magnitude if math.isfinite(magnitude) else None
                scenes[hemisphere]["planets"].append(
                    {
                        "key": key,
                        "name": name,
                        "naif_id": identifier,
                        "target_kind": kind,
                        "magnitude": magnitude,
                        "altitude_deg": a,
                        "azimuth_deg": z,
                        "xy": project(a, z, hemisphere),
                    }
                )
            solar_alt, solar_az, _ = here.observe(self.core.sun).apparent().altaz()
            solar_altitude, solar_azimuth = float(solar_alt.degrees), float(solar_az.degrees)
            hemisphere = "upper" if solar_altitude >= 0 else "lower"
            scenes[hemisphere]["references"].append(
                {
                    "key": "sun",
                    "name": "太阳方位",
                    "altitude_deg": solar_altitude,
                    "azimuth_deg": solar_azimuth,
                    "xy": project(solar_altitude, solar_azimuth, hemisphere),
                }
            )
        except EphemerisRangeError as exc:
            raise ValueError("站心光行时计算触及历表边界，请选择稍远离边界的日期。") from exc
        return {
            "epoch_utc": moment.isoformat(),
            "epoch_local": moment.astimezone(zone).isoformat(),
            "site": site,
            "magnitude_limit": magnitude_limit,
            "hemispheres": scenes,
            "sun_altitude_deg": solar_altitude,
            "sky_condition": "day"
            if solar_altitude >= 0
            else "twilight"
            if solar_altitude >= -18
            else "night",
            "projection": {
                "type": "azimuthal_equidistant",
                "upper_center": "zenith",
                "lower_center": "nadir",
                "horizon_altitude_deg": 0,
                "north": "up",
                "upper_east": "left",
                "lower_east": "right",
            },
            "notes": [
                "上下半球按理想水平地平线划分，使用无大气折射的站心视高度。",
                "几何可见方向的肉眼可见性还受日光、地形、建筑、天气与仪器影响。",
                "恒星亮度为星表 Johnson V 星等；可变星当天亮度未重建。",
                "行星亮度为 Skyfield/Mallama-Hilton 2018 模型估计；不适用时为 null。",
                "恒星使用 Hipparcos 自行与视差传播，未提供的径向速度按零处理。",
                "星座线采用 Sky & Telescope 图形，是连接真实恒星方向的辅助示意。",
            ],
            "missing_constellation_edges": missing_edges,
            "provenance": {
                "ephemeris": self.core.manifest,
                "sky_resources": self.manifest,
                "sky_algorithm_sha256": self.code_hash,
                "libraries": self.core.provenance["libraries"],
            },
        }
