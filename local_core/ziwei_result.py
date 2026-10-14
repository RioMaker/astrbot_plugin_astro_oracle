"""紫微图片及同次计算的精简元数据；仅在内存中返回，不保存查询。"""

import json
from dataclasses import dataclass

TRADITIONAL_FIELDS = (
    "profile",
    "source",
    "lunar",
    "effective_month",
    "hour_branch",
    "year_stem_branch",
    "life_branch",
    "body_branch",
    "bureau",
    "calendar_contract",
)


@dataclass(frozen=True)
class ZiweiChartResult:
    png: bytes
    metadata: dict


def result_metadata(data, comparison, chart_profile):
    """保留实际采用的时间、地点与排盘依据，不把实体坐标塞入调用记录。"""
    metadata = {
        key: data[key] for key in ("epoch_utc", "timezone", "time_note", "site", "site_source")
    }
    if "epoch_local" in data:
        metadata["epoch_local"] = data["epoch_local"]
    metadata["chart_profile"] = chart_profile
    metadata["traditional"] = {key: comparison["traditional"][key] for key in TRADITIONAL_FIELDS}
    # 严格 JSON 往返保证调用方可以直接编码，并使嵌套字典与计算输入脱离。
    return json.loads(json.dumps(metadata, ensure_ascii=False, allow_nan=False))
