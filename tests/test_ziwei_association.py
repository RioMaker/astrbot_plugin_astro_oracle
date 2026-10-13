"""球面关联分区的几何、并列、接缝和标签合并检查。"""

import math

import numpy as np
import pytest

from local_core.ziwei_association import (
    AMBIGUOUS,
    OUTSIDE,
    boundary_mask,
    classify_direction,
    region_map,
    unit_vector,
)
from local_core.ziwei_palaces import BRANCHES


def seed(altitude, azimuth, branch):
    return {"altitude_deg": altitude, "azimuth_deg": azimuth, "traditional_branch": branch}


def angles(vector):
    north, east, up = vector
    return math.degrees(math.atan2(up, math.hypot(north, east))), math.degrees(
        math.atan2(east, north)
    )


def test_unit_vectors_preserve_cardinal_directions_and_poles():
    for altitude, azimuth, expected in (
        (0, 0, (1, 0, 0)),
        (0, 90, (0, 1, 0)),
        (0, 180, (-1, 0, 0)),
        (0, 270, (0, -1, 0)),
        (90, 137, (0, 0, 1)),
        (-90, 299, (0, 0, -1)),
    ):
        actual = unit_vector(altitude, azimuth)
        assert actual == pytest.approx(expected, abs=1e-15)
        assert np.linalg.norm(actual) == pytest.approx(1)


def test_antipodal_seeds_have_the_expected_hemispheres_and_exact_tie():
    rows = [seed(0, 0, "子"), seed(0, 180, "午")]
    assert classify_direction(rows, 25, 0) == BRANCHES.index("子")
    assert classify_direction(rows, -25, 180) == BRANCHES.index("午")
    assert classify_direction(rows, 0, 90) == AMBIGUOUS
    assert classify_direction(rows, 0, 270) == AMBIGUOUS


def test_third_seed_removes_an_inactive_pair_bisector():
    rows = [seed(0, 0, "子"), seed(0, 180, "午"), seed(0, 90, "卯")]
    # 北/南的等距大圆经过东西方向；东侧被第三种子占据，不是前两支的边界。
    assert classify_direction(rows, 0, 90) == BRANCHES.index("卯")
    assert classify_direction(rows, 0, 270) == AMBIGUOUS


def test_seed_directions_remain_in_their_own_branches_without_mutating_rows():
    rows = [seed(39.9, 0.8, "辰"), seed(19.2, 326.8, "子"), seed(14.4, 207.8, "子")]
    before = [dict(row) for row in rows]
    for row in rows:
        assert classify_direction(rows, row["altitude_deg"], row["azimuth_deg"]) == BRANCHES.index(
            row["traditional_branch"]
        )
    assert rows == before


def test_same_branch_regions_merge_and_coincident_different_branches_are_ambiguous():
    same = [seed(0, 0, "子"), seed(0, 180, "子")]
    regions = region_map(same, size=41, center=20, radius=18)
    assert set(np.unique(regions)) == {OUTSIDE, BRANCHES.index("子")}
    assert not boundary_mask(regions).any()
    assert classify_direction([seed(25, 13, "子"), seed(25, 373, "子")], 25, 13) == 0
    conflicting = [seed(25, 13, "子"), seed(25, 373, "午")]
    assert classify_direction(conflicting, 25, 13) == AMBIGUOUS


def test_azimuth_seam_and_poles_do_not_depend_on_coordinate_alias():
    rows = [seed(60, 0, "子"), seed(60, 180, "午")]
    assert classify_direction(rows, 15, -1) == classify_direction(rows, 15, 359)
    for altitude in (-90, 90):
        assert {classify_direction(rows, altitude, az) for az in (0, 40, 180, 359)} == {AMBIGUOUS}


def test_region_map_preserves_observer_orientation_horizon_and_nadir_limit():
    rows = [seed(0, 0, "子"), seed(0, 180, "午")]
    regions = region_map(rows, size=9, center=4, radius=4)
    assert regions.shape == (9, 9) and regions.dtype == np.int16
    assert regions[2, 4] == BRANCHES.index("子")  # 北方地平线
    assert regions[6, 4] == BRANCHES.index("午")  # 南方地平线
    assert regions[4, 2] == regions[4, 6] == AMBIGUOUS  # 东、西
    assert regions[4, 4] == AMBIGUOUS  # 天顶
    assert {regions[y, x] for y, x in ((0, 4), (4, 0), (8, 4), (4, 8))} == {AMBIGUOUS}
    assert regions[0, 0] == regions[8, 8] == OUTSIDE


def test_branch_classification_is_invariant_under_common_frame_rotation_and_seed_order():
    rows = [seed(31, 17, "子"), seed(-21, 146, "午"), seed(47, 281, "卯")]
    a = math.radians(37)
    rotation = np.array(((1, 0, 0), (0, math.cos(a), -math.sin(a)), (0, math.sin(a), math.cos(a))))
    rotated = []
    for row in rows:
        h, az = angles(rotation @ unit_vector(row["altitude_deg"], row["azimuth_deg"]))
        rotated.append(seed(h, az, row["traditional_branch"]))
    for altitude, azimuth in ((13, 42), (-37, 92), (63, 187), (-9, 314)):
        expected = classify_direction(rows, altitude, azimuth)
        h, az = angles(rotation @ unit_vector(altitude, azimuth))
        assert classify_direction(rotated, h, az) == expected
        assert classify_direction(rows[::-1], altitude, azimuth) == expected
    assert np.array_equal(
        region_map(rows, size=41, center=20, radius=18),
        region_map(rows[::-1], size=41, center=20, radius=18),
    )


def test_boundary_mask_only_marks_adjacent_different_valid_branches():
    regions = np.array(((0, 1, OUTSIDE), (0, AMBIGUOUS, 1)), dtype=np.int16)
    assert np.array_equal(boundary_mask(regions), ((True, True, False), (False, False, False)))
    assert boundary_mask(np.array(((0, 0), (1, 1)), dtype=np.int16)).all()


@pytest.mark.parametrize("altitude,azimuth", [(91, 0), (-91, 0), (math.nan, 0), (0, math.inf)])
def test_invalid_directions_fail_without_producing_a_region(altitude, azimuth):
    with pytest.raises(ValueError):
        unit_vector(altitude, azimuth)


def test_empty_or_unknown_seeds_and_invalid_map_geometry_fail():
    with pytest.raises(ValueError):
        region_map([])
    for branch in ("未知", "", "子丑", None):
        with pytest.raises(ValueError):
            classify_direction([seed(0, 0, branch)], 0, 0)
    for kwargs in ({"size": 0}, {"radius": 0}, {"radius": math.inf}, {"center": math.nan}):
        with pytest.raises(ValueError):
            region_map([seed(0, 0, "子")], **kwargs)
