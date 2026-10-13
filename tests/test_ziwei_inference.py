"""角度模型、拓扑上限与实际选定天体计算的反例验收。"""

from datetime import datetime, timezone

import numpy as np
import pytest

from local_core.bundled_resources import BUNDLE_DIR
from local_core.engine import PlanetEngine
from local_core.sky_chart import SkyChartEngine
from local_core.ziwei_chart import compute_ziwei
from local_core.ziwei_palaces import BRANCHES
from tools.infer_ziwei_geometry import (
    HOLDOUT_UTC,
    SITES,
    TRAIN_UTC,
    cyclic_errors,
    evaluate_family,
    fit_equal_phase,
    fit_ordered_ra_upper,
    predict_equal,
    selected_state,
)


def test_known_phase_direction_is_recovered_without_object_names():
    angles = (23 + np.arange(12) * 30) % 360
    labels = predict_equal(angles, 8, -1)
    fit = fit_equal_phase(angles, labels)
    assert fit["direction"] == -1 and fit["correct"] == 12
    assert np.array_equal(predict_equal(angles, fit["phase_deg"], fit["direction"]), labels)
    assert cyclic_errors([11, 0, 6], [0, 11, 0]).tolist() == [1, 1, 6]


def test_identical_angle_conflicting_labels_cannot_be_made_correct_by_any_phase():
    fit = fit_equal_phase([40, 40], [0, 4])
    assert fit["correct"] == 1
    upper = fit_ordered_ra_upper([40, 40], [0, 4])
    assert upper["correct"] == 1 and len(set(upper["predictions"])) == 1


def test_unequal_contiguous_ra_upper_exceeds_equal_sectors_but_is_not_unrestricted():
    angles = [1, 2, 3, 4]
    labels = [0, 1, 2, 3]
    equal = fit_equal_phase(angles, labels)
    upper = fit_ordered_ra_upper(angles, labels)
    assert equal["correct"] < 4 and upper["correct"] == 4
    assert fit_ordered_ra_upper([0, 90, 180, 270], [0, 1, 0, 1])["correct"] < 4
    bounds = np.array(upper["boundaries_unwrapped_deg"])
    assert np.all(np.diff(bounds) > 0)
    unwrapped = bounds[0] + (np.array(angles) - bounds[0]) % 360
    states = np.searchsorted(bounds, unwrapped, side="right") - 1
    assert [upper["sector_branch_order"][s] for s in states] == [BRANCHES[v] for v in labels]


def test_date_groups_are_disjoint_and_holdout_labels_do_not_affect_fit():
    assert len(TRAIN_UTC) == 12 and len(HOLDOUT_UTC) == 6
    assert not set(d[:10] for d in TRAIN_UTC) & set(d[:10] for d in HOLDOUT_UTC)
    rows = [
        {
            "ra_date_deg": float(15 + 30 * i),
            "branch_index": i,
            "name": "紫微",
            "mapping_class": "display_convention",
            "sample_id": str(i),
        }
        for i in range(12)
    ]
    charts = [{"split": "train", "samples": rows}, {"split": "holdout", "samples": rows}]
    first = evaluate_family(charts, "ra_date_deg")
    changed = [{**r, "branch_index": (r["branch_index"] + 5) % 12, "name": "太阳"} for r in rows]
    second = evaluate_family([charts[0], {"split": "holdout", "samples": changed}], "ra_date_deg")
    assert first["parameters"] == second["parameters"]
    assert first["metrics"]["holdout"]["accuracy"] != second["metrics"]["holdout"]["accuracy"]


def test_selected_real_targets_match_existing_compute_with_same_frames():
    core = PlanetEngine(BUNDLE_DIR)
    try:
        sky = SkyChartEngine(core)
        selected = selected_state(sky, "2026-10-12T12:00:00Z", SITES[0])
        existing = compute_ziwei(
            sky, "/紫微星图 北京 20261012200000", now=datetime(2026, 10, 12, tzinfo=timezone.utc)
        )
        original = {o["key"]: o for o in existing["single_chart"]["objects"]}
        assert len(selected["single_chart"]["objects"]) == len(original) == 17
        for obj in selected["single_chart"]["objects"]:
            source = original[obj["key"]]
            assert obj.get("hip") == source.get("hip")
            assert obj.get("naif_id") == source.get("naif_id")
            for field in ("ra_date_deg", "dec_date_deg", "altitude_deg", "azimuth_deg"):
                assert obj[field] == pytest.approx(source[field], abs=1e-10)
        assert selected["palace_layer"]["assignment"] == existing["palace_layer"]["assignment"]
    finally:
        core.close()


def test_object_names_and_identifiers_are_not_predictive_inputs():
    rows = [
        {
            "ra_date_deg": float(15 + 30 * i),
            "branch_index": i,
            "name": "紫微",
            "hip": 11767,
            "mapping_class": "display_convention",
            "sample_id": str(i),
        }
        for i in range(12)
    ]
    charts = [{"split": "train", "samples": rows}, {"split": "holdout", "samples": rows}]
    first = evaluate_family(charts, "ra_date_deg")
    renamed = [
        {**r, "name": "太阳", "hip": 10, "sample_id": "renamed-" + r["sample_id"]} for r in rows
    ]
    second = evaluate_family(
        [{"split": "train", "samples": renamed}, {"split": "holdout", "samples": rows}],
        "ra_date_deg",
    )
    assert first["parameters"] == second["parameters"]
    assert first["direction_fits"] == second["direction_fits"]
    assert first["predictions"][-12:] == second["predictions"][-12:]
