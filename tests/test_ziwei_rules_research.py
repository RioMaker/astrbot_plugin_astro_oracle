import json
from pathlib import Path

import pytest
from lunar_python.util import LunarUtil

from local_core.engine import PlanetEngine
from local_core.sky_chart import SkyChartEngine
from local_core.ziwei_chart import compute_ziwei
from local_core.ziwei_palaces import BRANCHES, assign_palaces
from tools.ziwei_rules_research import (
    compare_sky,
    five_elements,
    palace_stems,
    traditional_core,
    ziwei_start,
)

REFERENCE = json.loads(
    (Path(__file__).parent / "fixtures/ziwei_iztro_2_6_1.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize("bureau", range(2, 7))
def test_all_thirty_days_match_independent_installed_iztro_reference(bureau):
    assert [ziwei_start(day, bureau) for day in range(1, 31)] == REFERENCE["ziwei_starts"][
        str(bureau)
    ]


def test_five_elements_and_palace_stems_against_independent_nayin_calendar():
    for year_stem in range(10):
        stems = palace_stems(year_stem)
        for branch in BRANCHES:
            data = five_elements(stems[branch], branch)
            assert data["element"] == LunarUtil.NAYIN[data["stem_branch"]][-1]
    assert palace_stems(2)["寅"] == "庚"
    assert five_elements("庚", "子") == {
        "stem_branch": "庚子",
        "nayin": "壁上土",
        "element": "土",
        "number": 5,
    }


@pytest.mark.parametrize("reference", REFERENCE["charts"])
def test_twenty_five_static_positions_match_independent_sdk_charts(reference):
    data = traditional_core(
        assign_palaces(f"{reference['date']}T{reference['time'] * 2:02d}:00:00+08:00")
    )
    assert len(data["positions"]) == 25
    for name, position in data["positions"].items():
        assert position["branch"] == reference["stars"][name]


def test_classical_leap_rule_is_separate_from_current_preview_without_mutation():
    assignment = assign_palaces("2020-05-23T00:00:00+08:00")
    assert assignment["lunar"]["leap"] and assignment["effective_month"] == 4
    classic = traditional_core(assignment)
    split = traditional_core(assignment, "preview_split")
    assert classic["effective_month"] == 5 and classic["life_branch"] == "午"
    assert split["effective_month"] == 4 and split["life_branch"] == "巳"
    assert assignment["effective_month"] == 4
    assert traditional_core(assign_palaces("2022-10-12T20:00:00+08:00"))["four_hua"]["科"] == "天府"


def test_actual_sky_comparison_reports_conditional_disagreement_and_no_synthetic_coordinates():
    core = PlanetEngine()
    try:
        sky = SkyChartEngine(core)
        data = compute_ziwei(sky, "/xt 北京 20261012200000")
        result = compare_sky(data)
        assert result["traditional"]["ziwei_branch"] == "辰"
        assert result["traditional"]["tianfu_branch"] == "子"
        assert result["matching_names"] == ["禄存"]
        assert not any(r["same_branch"] for r in result["rows"] if r["major"])
        originals = {o["key"]: o for o in data["single_chart"]["objects"]}
        for row in result["rows"]:
            assert row["ra_date_deg"] == originals[row["key"]]["ra_date_deg"]
            assert row["altitude_deg"] == originals[row["key"]]["altitude_deg"]
        later = compare_sky(compute_ziwei(sky, "/xt 北京 20261013200000"))
        assert later["traditional"]["ziwei_branch"] == "丑"
        assert next(r for r in later["rows"] if r["name"] == "紫微")["real_research_branch"] == "戌"
    finally:
        core.close()
