# 星轨神谕 · 星图

`astrbot_plugin_astro_oracle` 根据时间与地点生成一张标题为「星图」的双半球图片：上半球展示地平线以上，暗面展示被地球遮挡的方向。图中标注行星与知名恒星，点大小和亮度按视星等映射，星座连线可在配置中开关。

## 当前进度

- 当前版本 `0.1.4`，专注星图生成，支持七个行星目标与恒星；太阳为方位参考。
- 真实历表、原始及编译星表、星座与地点库已随插件保存在本地 Git，依赖安装后可离线计算。
- 本地真实数据与指令回归已完成；实际 AstrBot／QQ 回图继续联合验收。历表覆盖约 1849–2150 年，越界输入会明确报错。
- 新增[紫微星名真实天球本地预览](docs/ZIWEI_SKY_PREVIEW.md)：真实方位盘与十二宫说明卡片并排、十四主星、六煞符号与视星等；宫界为古籍研究示意，尚未接入指令或上线。

- 新增[传统安星与真实天体的研究对照](docs/ZIWEI_RULE_COMPARISON.md)：按《全书》静态安星核心核对，同一时刻逐项比较，现有预览规则不变。

## 使用说明

完整同步本插件仓库，在 AstrBot 中安装并重载。四个前缀 `/星图`、`/xingtu`、`/xt`、`/star` 完全等效。

| 指令示例 | 采用的时间与地点 |
| --- | --- |
| `/星图` | 当前时刻，默认北京 |
| `/星图 help` 或 `/星图 帮助` | 查看帮助 |
| `/星图 200010100100` | 北京，2000-10-10 01:00:00 |
| `/星图 20010101` | 北京，2001-01-01 08:00:00 |
| `/星图 2025` | 北京，2025-01-01 08:00:00 |
| `/星图 202503` | 北京，2025-03-01 08:00:00 |
| `/星图 北京` | 当前北京 |
| `/星图 北京 20250102` | 北京，2025-01-02 08:00:00 |
| `/星图 20250102 北京` | 同上，时间与地点顺序可交换 |
| `/星图 30.25°N 120.5°E` | 当前时刻，指定经纬度 |
| `/星图 30.25°N 120.5°E 20250102` | 指定经纬度，2025-01-02 08:00:00 |
| `/星图 30.25,120.5` | 同样支持「纬度,经度」或两个小数 |

时间使用公历，紧凑格式支持 `YYYY`、`YYYYMM`、`YYYYMMDD`、`YYYYMMDDHH`、`YYYYMMDDHHMM`、`YYYYMMDDHHMMSS`。至少提供四位年份；缺月补 1 月、缺日补 1 号，缺时分秒默认按 `08:00:00` 补齐。也支持 `2025-01-02 09:30:00` 等带分隔符格式。没有时间参数时使用当前时刻。

地点可以是中文或英文城市／乡镇名。同名地点会给出候选，用 `#编号` 明确选择，例如 `/star #5128581 20250102`。N/S 表示北纬／南纬，E/W 表示东经／西经；方向坐标可交换顺序，南纬与西经也可用负数表示。

城市时间按地点时区解释；经纬度默认使用 `Asia/Shanghai`。需要覆盖时区时放在末尾，例如 `/xt 北京 20250102 tz=UTC+08:00`。夏令时重复或不存在的时刻需用明确 UTC 偏移确认。旧入口 `time/时间`、`place/地点`、`at/时地` 仍兼容。

AstrBot 配置可设置默认地点、默认补齐时间、坐标时区、恒星星等上限、星座连线和名称开关。旧版出厂默认的 `12:00:00` 会一次性迁移为 `08:00:00`，其他自定义时间值保留。图片会注明最终采用的时间与补齐说明。

上下半球按理想水平地平线、无大气折射计算；实际肉眼可见性受日光、天气和地形影响。恒星使用星表 V 星等，行星亮度为模型估计。查询资料与图片不自动保存。

## 数据来源

- 行星位置：[NASA/JPL DE440s 历表](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440s.bsp)，背景说明见 [JPL 行星历表](https://ssd.jpl.nasa.gov/planets/eph_export.html)。
- 恒星位置、运动与 V 星等：[ESA Hipparcos 1997 / CDS I/239](https://cdsarc.cds.unistra.fr/viz-bin/cat/I/239)。
- 星座连线与通用星名：[Stellarium Modern — Sky & Telescope](https://github.com/Stellarium/stellarium/tree/master/skycultures/modern_st)，CC BY-SA 2.0；作者 Paul Krizak、Jonathan E. Piskor、G. Zotti。
- 城市、别名、经纬度与时区：[GeoNames cities1000](https://www.geonames.org/export/)，CC BY 4.0。
- 行星亮度模型：Skyfield 使用 Mallama & Hilton 2018，[Computing Apparent Planetary Magnitudes for The Astronomical Almanac](https://arxiv.org/abs/1808.01973)。

实际来源日期与 SHA-256 见 `assets/astronomy/ephemeris.json` 和 `assets/astronomy/sky/manifest.json`；许可与归属详见 [第三方资料说明](THIRD_PARTY_NOTICES.md)。
