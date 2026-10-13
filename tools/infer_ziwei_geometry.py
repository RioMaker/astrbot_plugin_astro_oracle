"""真实坐标到传统地支的有界模型实验；不修改天体、安星规则或正式输出。"""

import argparse
import hashlib
import json
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
from skyfield.api import Star, wgs84
from skyfield.framelib import ecliptic_frame

from local_core.engine import PlanetEngine
from local_core.resources import DATA_DIR, sha256_file
from local_core.sky_chart import SkyChartEngine
from local_core.ziwei_chart import CATALOG, MAJOR_ORDER, project_all_sky
from local_core.ziwei_correspondence import build_correspondence
from local_core.ziwei_palaces import BRANCHES, assign_palaces
from local_core.ziwei_photometry import luminary_photometry

ROOT = Path(__file__).resolve().parents[1]
PROFILE = "ziwei-angle-inference-v1"
FEATURES = ("ra_date_deg", "ecliptic_longitude_date_deg", "hour_angle_date_deg", "azimuth_deg")
TRAIN_UTC = (
    "1960-02-03T00:00:00Z",
    "1970-07-14T06:00:00Z",
    "1985-03-21T12:00:00Z",
    "1990-10-08T18:00:00Z",
    "2000-01-16T03:00:00Z",
    "2004-04-19T09:00:00Z",
    "2012-08-09T15:00:00Z",
    "2016-11-27T21:00:00Z",
    "2024-02-12T01:00:00Z",
    "2026-05-18T07:00:00Z",
    "2030-09-25T13:00:00Z",
    "2050-12-07T19:00:00Z",
)
HOLDOUT_UTC = (
    "1965-05-11T04:00:00Z",
    "1995-12-23T10:00:00Z",
    "2008-06-17T16:00:00Z",
    "2025-01-29T22:00:00Z",
    "2035-09-02T02:00:00Z",
    "2045-03-08T14:00:00Z",
)
SITES = (
    {
        "id": "beijing",
        "latitude": 39.9075,
        "longitude": 116.39723,
        "elevation_m": 0.0,
        "label": "北京",
        "timezone": "Asia/Shanghai",
    },
    {
        "id": "equator",
        "latitude": 0.0,
        "longitude": 0.0,
        "elevation_m": 0.0,
        "label": "赤道 0°/0°",
        "timezone": "UTC",
    },
    {
        "id": "sydney",
        "latitude": -33.8688,
        "longitude": 151.2093,
        "elevation_m": 0.0,
        "label": "悉尼",
        "timezone": "Australia/Sydney",
    },
)
PROBE_SITES = (
    {
        "id": "greenwich_probe",
        "latitude": 51.4769,
        "longitude": 0.0,
        "elevation_m": 0.0,
        "label": "格林尼治观测点",
        "timezone": "Europe/London",
    },
    {
        "id": "singapore_probe",
        "latitude": 1.3521,
        "longitude": 103.8198,
        "elevation_m": 0.0,
        "label": "新加坡观测点",
        "timezone": "Asia/Singapore",
    },
)


def _arrays(angles, labels):
    angles = np.asarray(angles, dtype=float)
    raw = np.asarray(labels)
    labels = np.asarray(labels, dtype=int)
    if angles.ndim != 1 or not len(angles) or angles.shape != labels.shape:
        raise ValueError("拟合需要等长且非空的一维角度与地支序列。")
    if not np.all(np.isfinite(angles)) or not np.all(raw == labels):
        raise ValueError("角度须有限，地支索引须为整数。")
    if not np.all((0 <= labels) & (labels < 12)):
        raise ValueError("地支索引须为 0–11。")
    return angles % 360, labels


def cyclic_errors(predictions, labels):
    difference = np.abs(np.asarray(predictions) - np.asarray(labels))
    return np.minimum(difference, 12 - difference)


def predict_equal(angles, phase_deg, direction):
    if direction not in (-1, 1):
        raise ValueError("方向须为 +1 或 −1。")
    return np.floor((direction * (np.asarray(angles) - phase_deg)) % 360 / 30).astype(int)


def fit_equal_phase(angles, labels, directions=(1, -1)):
    """枚举全部分段恒定的相位区间；同准确数时选循环误差较小者。"""
    angles, labels = _arrays(angles, labels)
    breaks = np.unique(angles % 30)
    right = np.r_[breaks[1:], breaks[0] + 30]
    midpoints = ((breaks + right) / 2) % 30
    phases = np.sort((midpoints[:, None] + np.arange(12) * 30).ravel())
    best = None
    for direction in directions:
        if direction not in (-1, 1):
            raise ValueError("方向须为 +1 或 −1。")
        for start in range(0, len(phases), 256):
            batch = phases[start : start + 256]
            predictions = predict_equal(angles[:, None], batch[None, :], direction)
            correct = (predictions == labels[:, None]).sum(axis=0)
            error = cyclic_errors(predictions, labels[:, None]).sum(axis=0)
            chosen = np.lexsort((batch, error, -correct))[0]
            rank = (-int(correct[chosen]), int(error[chosen]), float(batch[chosen]), -direction)
            if best is None or rank < best[0]:
                best = (rank, {"phase_deg": float(batch[chosen]), "direction": direction})
    result = best[1]
    prediction = predict_equal(angles, result["phase_deg"], result["direction"])
    result.update(
        correct=int((prediction == labels).sum()),
        count=len(labels),
        circular_step_error_sum=int(cyclic_errors(prediction, labels).sum()),
    )
    return result


def fit_ordered_ra_upper(angles, labels):
    """逐盘不等宽连续赤经区上限；循环有序 DP，同角对象必须同区。"""
    angles, labels = _arrays(angles, labels)
    order = np.argsort(angles, kind="stable")
    sorted_angles = angles[order]
    starts = np.r_[0, np.flatnonzero(np.diff(sorted_angles) != 0) + 1]
    groups = np.split(order, starts[1:])
    group_angles = sorted_angles[starts]
    weight = 6 * len(labels) + 1
    group_scores = np.array(
        [
            [(labels[g] == p).sum() * weight - cyclic_errors(p, labels[g]).sum() for p in range(12)]
            for g in groups
        ],
        dtype=int,
    )
    best = None
    for cut in range(len(groups)):
        sequence = np.r_[np.arange(cut, len(groups)), np.arange(cut)]
        scores = group_scores[sequence]
        for direction in (1, -1):
            for initial in range(12):
                sector_labels = (initial + direction * np.arange(12)) % 12
                previous = np.zeros(12, dtype=int)
                parents = np.zeros((len(groups), 12), dtype=int)
                for row, values in enumerate(scores):
                    best_index = 0
                    for column in range(12):
                        if previous[column] > previous[best_index]:
                            best_index = column
                        parents[row, column] = best_index
                    previous = np.maximum.accumulate(previous) + values[sector_labels]
                ending = int(np.argmax(previous))
                rank = (-int(previous[ending]), cut, -direction, initial, ending)
                if best is not None and rank >= best[0]:
                    continue
                states = np.empty(len(groups), dtype=int)
                for row in range(len(groups) - 1, -1, -1):
                    states[row] = ending
                    ending = parents[row, ending]
                prediction = np.empty(len(labels), dtype=int)
                for group, state in zip(sequence, states):
                    prediction[groups[group]] = sector_labels[state]
                best = (rank, prediction, cut, direction, initial, states, sequence)
    _, prediction, cut, direction, initial, states, sequence = best
    values = group_angles[sequence].copy()
    values[len(groups) - cut :] += 360
    left = group_angles[cut - 1] if cut else group_angles[-1] - 360
    first_boundary = (left + values[0]) / 2
    intervals = {}
    for boundary in range(1, 12):
        low = values[states < boundary][-1] if np.any(states < boundary) else first_boundary
        high = values[states >= boundary][0] if np.any(states >= boundary) else first_boundary + 360
        intervals.setdefault((float(low), float(high)), []).append(boundary)
    boundaries = np.empty(13)
    boundaries[0], boundaries[12] = first_boundary, first_boundary + 360
    for (low, high), indices in intervals.items():
        for index, boundary in enumerate(indices):
            boundaries[boundary] = low + (index + 1) / (len(indices) + 1) * (high - low)
    return {
        "family": "per_chart_unequal_cyclic_ordered_ra_upper_bound",
        "direction": direction,
        "initial_branch": BRANCHES[initial],
        "boundaries_unwrapped_deg": boundaries.tolist(),
        "sector_branch_order": [BRANCHES[(initial + direction * k) % 12] for k in range(12)],
        "predictions": prediction.tolist(),
        "correct": int((prediction == labels).sum()),
        "count": len(labels),
        "circular_step_error_sum": int(cyclic_errors(prediction, labels).sum()),
        "interpretation": "使用本盘目标标签拟合的拓扑上限，不能视为留出预测。",
    }


def selected_state(sky, epoch_utc, site):
    """只观测现有 15 个 HIP 和日月；省去全部背景星计算，不使用虚构坐标。"""
    moment = datetime.fromisoformat(epoch_utc.replace("Z", "+00:00"))
    local = moment.astimezone(ZoneInfo(site["timezone"]))
    t = sky.core.ts.from_datetime(moment)
    observer = sky.core.earth + wgs84.latlon(
        site["latitude"], site["longitude"], elevation_m=site["elevation_m"]
    )
    here = observer.at(t)
    objects = []
    targets = []
    for name, hip, astronomical_name, major, group, mapping in CATALOG:
        row = sky.rows[sky.indices[hip]]
        target = Star(
            ra_hours=row[2],
            dec_degrees=row[3],
            parallax_mas=row[4],
            ra_mas_per_year=row[5],
            dec_mas_per_year=row[6],
            epoch=sky.core.ts.J(1991.25),
        )
        targets.append(
            (
                target,
                {
                    "name": name,
                    "hip": hip,
                    "key": f"hip:{hip}",
                    "kind": "star",
                    "major": major,
                    "group": group,
                    "mapping": mapping,
                    "astronomical_name": astronomical_name,
                    "magnitude": float(row[1]),
                },
            )
        )
    for name, key, naif in (("太阳", "sun", 10), ("太阴", "moon", 301)):
        targets.append(
            (
                sky.core.kernel[naif],
                {
                    "name": name,
                    "key": key,
                    "kind": key,
                    "naif_id": naif,
                    "major": True,
                    "mapping": "日月名称",
                },
            )
        )
    for target, obj in targets:
        astrometric = here.observe(target)
        apparent = astrometric.apparent()
        ra, dec, _ = apparent.radec(epoch="date")
        altitude, azimuth, _ = apparent.altaz()
        _, longitude, _ = apparent.frame_latlon(ecliptic_frame)
        ra_deg = float(ra.hours) * 15
        alt, az = float(altitude.degrees), float(azimuth.degrees)
        obj.update(
            ra_date_deg=ra_deg,
            dec_date_deg=float(dec.degrees),
            ecliptic_longitude_date_deg=float(longitude.degrees),
            hour_angle_date_deg=(float(t.gast) * 15 + site["longitude"] - ra_deg) % 360,
            altitude_deg=alt,
            azimuth_deg=az,
            single_xy=project_all_sky(alt, az),
        )
        if obj["kind"] != "star":
            obj.update(luminary_photometry(astrometric, sky.core.sun, obj["kind"]))
        objects.append(obj)
    return {
        "epoch_utc": moment.isoformat(),
        "epoch_local": local.isoformat(),
        "site": site,
        "palace_layer": {"assignment": assign_palaces(local.isoformat())},
        "single_chart": {"objects": objects},
    }


def collect_chart(sky, epoch_utc, site, split):
    state = selected_state(sky, epoch_utc, site)
    comparison = build_correspondence(state)
    physical = {obj["key"]: obj for obj in state["single_chart"]["objects"]}
    chart_id = f"{epoch_utc}_{site['id']}"
    rows = []
    for row in comparison["rows"]:
        obj = physical[row["key"]]
        rows.append(
            {
                **row,
                "chart_id": chart_id,
                "split": split,
                "sample_id": f"{chart_id}_{row['key']}",
                "mapping_class": row["mapping"]["class"],
                "branch_index": BRANCHES.index(row["traditional_branch"]),
                **{feature: obj[feature] for feature in FEATURES},
            }
        )
    return {
        "id": chart_id,
        "date_group": epoch_utc[:10],
        "split": split,
        "input": {"epoch_utc": epoch_utc, "site": site},
        "epoch_local": state["epoch_local"],
        "traditional": comparison["traditional"],
        "samples": rows,
    }


def metrics(rows, predictions):
    predictions = np.asarray(predictions, dtype=int)
    labels = np.array([r["branch_index"] for r in rows], dtype=int)
    error = cyclic_errors(predictions, labels)

    def summary(indices):
        return {
            "count": len(indices),
            "correct": int((predictions[indices] == labels[indices]).sum()),
            "accuracy": float((predictions[indices] == labels[indices]).mean()),
            "mean_circular_step_error": float(error[indices].mean()),
        }

    result = summary(np.arange(len(rows)))
    result["by_mapping_class"] = {
        kind: summary(np.array([i for i, row in enumerate(rows) if row["mapping_class"] == kind]))
        for kind in sorted({row["mapping_class"] for row in rows})
    }
    result["by_object"] = {
        name: summary(np.array([i for i, row in enumerate(rows) if row["name"] == name]))
        for name in (*MAJOR_ORDER, "禄存", "文曲", "左辅")
        if any(r["name"] == name for r in rows)
    }
    return result


def evaluate_family(charts, feature):
    training = [row for chart in charts if chart["split"] == "train" for row in chart["samples"]]
    fit = fit_equal_phase([r[feature] for r in training], [r["branch_index"] for r in training])
    result = {
        "family": "fixed_rotated_equal_12_sectors",
        "feature": feature,
        "parameters": fit,
        "direction_fits": {
            str(direction): fit_equal_phase(
                [r[feature] for r in training],
                [r["branch_index"] for r in training],
                directions=(direction,),
            )
            for direction in (1, -1)
        },
        "rule": "floor((direction * (angle - phase_deg) mod 360) / 30); 子=0 至亥=11",
        "fit_objective": "最多正确地支，其次最小循环格误差，再用相位/方向固定打破平局",
        "metrics": {},
        "predictions": [],
    }
    for split in ("train", "holdout", "unseen_site_probe"):
        rows = [row for chart in charts if chart["split"] == split for row in chart["samples"]]
        if not rows:
            continue
        predictions = predict_equal([r[feature] for r in rows], fit["phase_deg"], fit["direction"])
        result["metrics"][split] = metrics(rows, predictions)
        result["predictions"].extend(
            {
                "sample_id": r["sample_id"],
                "predicted_branch": BRANCHES[p],
                "circular_step_error": int(e),
            }
            for r, p, e in zip(
                rows, predictions, cyclic_errors(predictions, [r["branch_index"] for r in rows])
            )
        )
    return result


def oracle_results(charts):
    equal, topology = [], []
    for chart in charts:
        rows, local_fits = chart["samples"], {}
        labels = [r["branch_index"] for r in rows]
        for feature in FEATURES:
            fit = fit_equal_phase([r[feature] for r in rows], labels)
            local_fits[feature] = fit
        upper = fit_ordered_ra_upper([r["ra_date_deg"] for r in rows], labels)
        equal.append({"chart_id": chart["id"], "split": chart["split"], "fits": local_fits})
        topology.append({"chart_id": chart["id"], "split": chart["split"], **upper})
    aggregated = {"equal_by_feature": {}, "unequal_ra_topology": {}}
    for split in ("train", "holdout", "unseen_site_probe"):
        chosen = [c for c in charts if c["split"] == split]
        if not chosen:
            continue
        rows = [r for c in chosen for r in c["samples"]]
        for feature in FEATURES:
            prediction = []
            for chart in chosen:
                fit = next(r["fits"][feature] for r in equal if r["chart_id"] == chart["id"])
                prediction.extend(
                    predict_equal(
                        [r[feature] for r in chart["samples"]], fit["phase_deg"], fit["direction"]
                    )
                )
            aggregated["equal_by_feature"].setdefault(feature, {})[split] = metrics(
                rows, prediction
            )
        predictions = [
            p
            for chart in chosen
            for record in topology
            if record["chart_id"] == chart["id"]
            for p in record["predictions"]
        ]
        aggregated["unequal_ra_topology"][split] = metrics(rows, predictions)
    return {
        "interpretation": "逐盘使用目标标签的拟合上限；所有留出标签已被用于这些上限，非预测。",
        "equal_per_chart": equal,
        "unequal_ra_per_chart": topology,
        "metrics": aggregated,
    }


def run_experiment(data_dir, output, site_probes=True):
    if set(t[:10] for t in TRAIN_UTC) & set(t[:10] for t in HOLDOUT_UTC):
        raise ValueError("训练与留出必须按整 UTC 日期组完全分离。")
    core = PlanetEngine(data_dir)
    try:
        sky = SkyChartEngine(core)
        charts = []
        for split, epochs, sites in (
            ("train", TRAIN_UTC, SITES),
            ("holdout", HOLDOUT_UTC, SITES),
            ("unseen_site_probe", HOLDOUT_UTC if site_probes else (), PROBE_SITES),
        ):
            for epoch in epochs:
                charts.extend(collect_chart(sky, epoch, site, split) for site in sites)
            print(f"完成真实观测 {split}: {len(epochs) * len(sites)} 盘", flush=True)
        models = [evaluate_family(charts, feature) for feature in FEATURES]
        print("完成训练/留出固定等分模型，计算逐盘上限。", flush=True)
        oracles = oracle_results(charts)
        sources = (
            "tools/infer_ziwei_geometry.py",
            "local_core/ziwei_chart.py",
            "local_core/ziwei_correspondence.py",
            "local_core/ziwei_traditional.py",
            "local_core/ziwei_palaces.py",
            "local_core/ziwei_photometry.py",
        )
        payload = {
            "profile": PROFILE,
            "split_policy": "完整 UTC 日期组分离；地点探针不参与训练",
            "train_utc": TRAIN_UTC,
            "holdout_utc": HOLDOUT_UTC,
            "sites": SITES,
            "unseen_probe_sites": PROBE_SITES if site_probes else [],
            "coordinate_contract": {
                "origin": "WGS84 站心",
                "equatorial": "日期真赤道/真春分点，视坐标",
                "ecliptic": "日期真黄道/真春分点，视坐标",
                "hour_angle": "GAST×15 + 东经 − 日期真赤经，模360",
                "horizontal": "北起顺时针方位，无大气折射",
                "targets": "现有目录 15 个 HIP 恒星与 NAIF 10/301 日月，未修改或重选实体",
                "calendar": "每个观测点的记录民用时区；传统核心版本保持原样",
            },
            "provenance": {
                "core": core.provenance,
                "sky_chart_algorithm_sha256": sky.code_hash,
                "ephemeris": core.manifest,
                "sky_manifest": sky.manifest,
                "ephemeris_actual_sha256": sha256_file(core.path),
                "code_sha256": {p: sha256_file(ROOT / p) for p in sources},
                "libraries": {
                    p: version(p)
                    for p in ("skyfield", "jplephem", "numpy", "lunar-python", "tzdata")
                },
            },
            "charts": charts,
            "models": models,
            "oracles": oracles,
            "interpretation": {
                "evaluated_families": [
                    "固定相位/方向的等分赤经、黄经、时角、方位12区",
                    "逐盘等分相位上限",
                    "逐盘不等宽循环连续赤经12区拓扑上限",
                ],
                "not_tested": (
                    "任意非线性、多维、非连续、依历法参数变化的映射；不排除所有可能映射。"
                ),
                "limits": "该固定设计用于模型诊断，不是统计独立认证、个人预测或新天文精度验收。",
                "chance_uniform_accuracy": 1 / 12,
                "leakage_boundary": (
                    "正式候选仅使用一个角度、全局相位/方向；不使用名称/HIP作为特征。"
                ),
                "error_unit": "循环地支格数；不是物理角度误差。",
            },
        }
        payload["sample_sha256"] = hashlib.sha256(
            json.dumps(charts, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        payload["run_id"] = hashlib.sha256(
            json.dumps(
                {
                    "profile": PROFILE,
                    "sample_sha256": payload["sample_sha256"],
                    "provenance": payload["provenance"],
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        print(output.resolve())
        for model in models:
            score = model["metrics"]["holdout"]
            print(
                f"{model['feature']}: holdout {score['correct']}/{score['count']} "
                f"({score['accuracy']:.3%}), 循环格误差 {score['mean_circular_step_error']:.3f}"
            )
        return payload
    finally:
        core.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument(
        "--output", type=Path, default=DATA_DIR / "ziwei-validation/inference/geometry-fit.json"
    )
    parser.add_argument("--no-site-probes", action="store_true")
    args = parser.parse_args()
    run_experiment(args.data_dir, args.output, not args.no_site_probes)


if __name__ == "__main__":
    main()
