# 本地行星计算接口

当前范围是给定日期或具体时刻，返回八大行星的状态。入口独立于 AstrBot，先在本地与用户联合调试。

## 时间输入

`parse_time_input(text, timezone_name)` 保留日、时、分、秒四种分辨率。日、时、分表示尚未确定低阶时间字段的区间；秒表示指定时刻，分辨率为 1 秒。默认时区 `Asia/Shanghai`，公历输入格式为 `YYYY-MM-DD[ HH[:MM[:SS]]]`，也可使用 `T` 分隔日期和时间。

全天以当地午夜与次日午夜为边界；小时/分钟从指定时刻起按实际经过秒数计算。因此夏令时日期可有 23/25 小时，时钟跳变前一小时的结束标签可能跳到下一个合法本地小时。时区规则导致的重复或不存在时刻会明确拒绝，用户可提供显式 UTC 偏移。

API 中 `window.mode` 分别为 `interval` 或 `instant`；`input_resolution_seconds` 是名义分辨率，`elapsed_seconds` 是实际经过时间。秒输入的 `end_utc_exclusive` 仅记录分辨率单元，实际只计算起点这一指定时刻。

区间采样包含起点和终点前最后一秒，默认 7 个采样，数量可设为 2–25。采样统计不代表真实连续运动的严格极值，也不是测量误差的概率区间。

## 计算调用

在项目根目录、使用 `.venv`：

```python
from local_core.engine import PlanetEngine

engine = PlanetEngine()
try:
    result = engine.compute("2026-10-09 12:34", "Asia/Shanghai", samples=7)
finally:
    engine.close()
```

浏览器服务仅绑定 `127.0.0.1`，`POST /api/state` 请求格式：

```json
{"time": "2026-10-09 12:34", "timezone": "Asia/Shanghai", "samples": 7}
```

`GET /api/info` 返回历表边界、天体标识、坐标定义和来源；`GET /health` 表示真实引擎已初始化，可供启动器核对进程与就绪状态。输入错误、时区歧义和历表越界返回 HTTP 400 及说明。

## 输出对象

| 字段 | 内容 |
| --- | --- |
| `schema_version` | 当前为 `1` |
| `window` | 原始输入、时区、分辨率、区间/单点模式、本地和 UTC 边界、经过时间 |
| `snapshots` | 每个采样时刻的 UTC/本地标签、TT/TDB 儒略日与八大行星结果 |
| `planets[].naif_id` / `target_kind` | 明确对应天体中心或行星系统质心 |
| `heliocentric.position_au` | 太阳中心、ICRF 固定轴的几何 XYZ，单位 AU |
| `heliocentric.velocity_km_s` | 同一中心和参考轴的 VX/VY/VZ，单位 km/s |
| `heliocentric.distance_au` / `speed_km_s` | 上述向量的模 |
| `geocentric_apparent` | 地球中心视黄经/黄纬、视赤经/赤纬及距离；地球自身为 `null` |
| `definitions` / `notes` | 坐标定义、采样和模型适用说明 |
| `provenance` | 历表 URL/校验值/覆盖、代码校验值、实际库版本与时间模型 |

## 坐标定义

日心状态是同一 TDB 时刻的太阳中心相对几何状态，不施加光行时或光行差修正。ICRF 是固定参考轴；此处并未把日心向量误标成黄道轴。

地心视状态从地球本体中心观测目标，施加光行时、光行差和引力偏折修正。黄经/黄纬使用 Skyfield 的日期真黄道与真春分点框架；赤经/赤纬使用日期真赤道与真春分点，均以度输出。距离为视位置对应的距离。当前没有地理观测点，未计算站心高度、方位或可见性。

水星、金星、地球的 NAIF 标识为 `199`、`299`、`399`，对应本体中心。DE440s 中本实现对火星、木星、土星、天王星、海王星分别使用 `4`–`8`，对应行星系统质心；界面与 JSON 都标明这一差别。若后续需要这些行星的本体中心，应接入合适的额外 SPK，而不是静默修改标识。

## 数据与复现

JPL DE440s 位于被忽略的 `data/de440s.bsp`，SHA-256 为 `c1c7feeab882263fc493a9d5a5b2ddd71b54826cdf65d8d17a76126b260a49f2`。资源准备成功后才生成来源记录；计算时核对校验值，并使用本地文件与 Skyfield 打包的时间数据，不隐式联网。

文件中共同覆盖范围为 TDB JD `2396752.5`–`2506352.5`，近似 1849–2150 年。光行时在边界附近可能访问更早的模型时刻，程序会单独提示。未来/历史 UTC 换算、时区记录与历表本身的精度分别受模型限制，秒级输入不表示物理位置已达到某个统一精度。

当前核心依赖版本见 `requirements.txt`，包含 Skyfield `1.55`、jplephem `2.24`、NumPy `2.2.6`、tzdata `2026.5`。批量与单点角度在浮点末位可能有舍入差异，验收按记录的数值容差比较。
