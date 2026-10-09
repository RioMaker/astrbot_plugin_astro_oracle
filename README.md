# 星轨神谕 · Astro Oracle

`astrbot_plugin_astro_oracle` 的当前目标是：输入日期或具体时刻，返回对应的真实行星状态，先通过本地联合调试，再考虑 AstrBot 接入。

**已实现独立本地计算原型 `0.1.0`**：八大行星、日/时/分/秒输入分辨率、时区、时间段采样、网页表单与结果表格、三维位置和速度、地心视坐标、JSON 导出与数据溯源。使用真实 JPL DE440s，资源准备后查询可离线执行。

现在支持出生地观测视角的双半球星图：本地城市/乡镇搜索与经纬度校正、上半球与地球遮挡下半球、真实恒星星表、行星视星等估计、可选星座连线、名称提示和双图 PNG/JSON 导出。

AstrBot 部分仍是 `0.1.0` 说明骨架，提供帮助/状态/开发路线查询；尚未把计算核心连接到插件指令。

## 启动本地联合调试

直接运行本目录的 `launch_local.py`，或在 Windows 已配置 Python 文件关联时双击它。使用系统 Python 启动会自动切换到本项目 `.venv`，检查历表，等待本地服务健康检查通过后打开浏览器，无需手动激活环境。

默认地址：[http://127.0.0.1:8768](http://127.0.0.1:8768)。在启动窗口按 `Ctrl+C` 可结束本次服务。更换端口或禁用自动打开浏览器：

```powershell
python launch_local.py
python launch_local.py --port 8778
python launch_local.py --no-browser
```

当前工作区已准备好 `.venv`、历表和星图资源。新克隆的机器需在本插件目录执行一次：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -X utf8 -m local_core.resources
python launch_local.py
```

历表从 [NASA/JPL 官方地址](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440s.bsp) 下载，约 32 MB。`data/ephemeris.json` 记录实际来源、大小、覆盖范围和 SHA-256；查询时不隐式下载数据，也不自动保存输入资料。

首次资源准备还会下载 Hipparcos 原始星表（约 53 MB）、Stellarium 连线/星名数据和 GeoNames 城市库（压缩约 11 MB）。启动器等待资源校验和服务就绪后打开浏览器。原始及编译数据留在被忽略的 `data/sky/`，来源与 SHA-256 见其 `manifest.json`。

## 出生地双半球星图

1. 搜索城市/乡镇，例如「上海」「杭州」或 `New York`，选择结果。
2. 校正经纬度、观测点高度和出生时间所用时区。搜索结果为地点中心，适用更精确地点时可直接修改坐标。
3. 输入日期或时刻，点击「生成星图与状态」。日/时/分输入继续保留采样范围，切换采样时刻会更新两张星图。
4. 上图以天顶为中心，展示地平线以上；下图以天底为中心，展示按理想地平线模型划分的地球遮挡方向。两图同一时刻、北朝上，上图东在左，下图东在右。
5. 星座连线、知名恒星名称和星座名称可以开关。调整恒星星等上限可改变星点数量，点亮度与大小按视星等映射。行星名称保持显示；指向或点击星点可看角度与星等。

图中计算从地球观测的七个行星目标，地球本身作为观测参考；太阳符号标示方位。行星位置来自 JPL，恒星来自 Hipparcos 1997，连线来自 Stellarium Sky & Telescope 图形。默认显示星等 ≤6 的恒星，编译库包含星等 ≤8 或连线所需的 41,394 条适用恒星记录；地点库实际包含 171,174 条记录。

星图表示无折射的站心视方向，按理想水平地平线划分上下半球。肉眼可见性受日光、地形、建筑、天气与仪器影响。恒星使用星表 V 星等，行星使用光度模型估计；可变星当天亮度没有重建，显示需要曝光映射。定义、适用范围与接口见 [星图说明](docs/SKY_CHART.md)。

星座图形数据及其改编采用 CC BY-SA 2.0，导出图保留来源说明；详见 [第三方资料说明](THIRD_PARTY_NOTICES.md)。

## 日期与时间分辨率

| 输入示例 | 解释与输出 |
| --- | --- |
| `2026-10-09` | 当地全天范围，默认 7 个采样时刻 |
| `2026-10-09 12` | 从该本地小时起的一个实际小时，默认 7 个采样 |
| `2026-10-09 12:34` | 指定分钟的时间段，默认 7 个采样 |
| `2026-10-09 12:34:56` | 指定秒的单一时刻，输入分辨率为 1 秒 |

默认时区为 `Asia/Shanghai`，也支持 IANA 时区、`UTC` 和 `UTC+08:00` 等显式偏移。跨夏令时的全天可能是 23 或 25 小时；重复或不存在的本地时刻须通过显式偏移消除歧义。

时间段使用左闭右开区间，默认展示起点、多个中间时刻和结束前最后一秒；采样数可设为 2–25。离散采样不构成连续变化的严格上下界。秒级输入分辨率、界面小数位数与天文模型精度分别记录。

当前 DE440s 文件覆盖 TDB JD `2396752.5` 至 `2506352.5`，约 1849–2150 年；页面显示换算到 UTC 的实际边界，超出范围会明确报错。历史民用时间与早期 UTC 采用模型换算，使用时需核对记录。当前不解析公元前纪年、非公历和闰秒 `60`。

更多字段与坐标定义见 [本地核心说明](docs/LOCAL_CORE.md)。

## 使用指令

| 指令 | 功能 |
| --- | --- |
| `/星轨神谕` 或 `/星轨神谕 帮助` | 查看说明与当前能力 |
| `/星轨神谕 状态` | 查看版本及开发状态 |
| `/星轨神谕 路线` | 查看分阶段开发计划 |
| `/astro_oracle help`、`status`、`roadmap` | 对应功能的英文入口 |

指令前缀与唤醒方式遵循 AstrBot 的实际配置。当前指令只返回文本说明，不接收或保存出生资料。

## AstrBot 骨架安装与配置

开发基线为 Python 3.10+、AstrBot 4.24.0+。将本目录作为独立插件放入 AstrBot 的 `data/plugins/astrbot_plugin_astro_oracle/`，然后从 WebUI 重载或重启 AstrBot。当前本地仓库尚无远程地址，`metadata.yaml:repo` 留空。

AstrBot 在其运行环境中提供 `astrbot` 模块。`main.py` 的说明指令没有额外依赖，`requirements.txt` 声明的是独立本地计算核心的依赖；插件入口不作为独立 Python 程序运行。

WebUI 配置项：

| 字段 | 默认值 | 行为 |
| --- | --- | --- |
| `enabled` | `true` | 启用说明指令；设为 `false` 后仅提示插件已关闭 |

运行配置由 AstrBot 管理。未来集成后，历表、星表和计算缓存使用框架的 `data/plugin_data/astrbot_plugin_astro_oracle/`，不依赖本地调试目录。

## 项目结构

```text
astrbot_plugin_astro_oracle/
├── main.py                 AstrBot 指令入口
├── metadata.yaml           插件元数据
├── _conf_schema.json       WebUI 配置定义
├── local_core/             时间、站心计算、离线地点与真实资源管理
├── web/                    浏览器表单、结果表格与双半球绘图
├── launch_local.py         自动切换 .venv，等待就绪后打开浏览器的 Python 入口
├── start_local.cmd         可选 Windows 快捷入口
├── requirements.txt        本地核心运行依赖
├── requirements-dev.txt    测试和浏览器验证依赖
├── pyproject.toml          Ruff 检查与格式配置
├── AGENTS.md               插件专属开发约定
├── README.md               使用与当前能力
├── tests/                  时间、计算、API 和启动器验证
├── tools/                  浏览器与 JPL Horizons 核对工具
└── docs/                   核心说明、验证记录和阶段规划
```

恒星星图已接入本地原型。特征提取、研究评估与 AstrBot 接入在联合调试后按实际需要开展，见 [开发路线](docs/ROADMAP.md)。

## 本地验证

准备真实历表后，使用本项目环境执行：

```powershell
uvx ruff check .
uvx ruff format --check .
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -X utf8 -m pytest -q
.\.venv\Scripts\python.exe -X utf8 -m tools.verify_browser
.\.venv\Scripts\python.exe -X utf8 -m tools.verify_sky_ui
.\.venv\Scripts\python.exe -X utf8 -m tools.verify_horizons
.\.venv\Scripts\python.exe -X utf8 -m tools.verify_topocentric
```

浏览器验证工具使用独立无头 Chrome 和任务自有随机端口，结束后关闭浏览器与服务。Horizons 工具逐条查询官方接口并保存响应，再次执行优先使用匹配的真实响应缓存；`--refresh` 可重新获取。原始报告与截图保存在被忽略的 `data/`。

已完成的本地检查、官方参考差异及其限度见 [验证记录](docs/VALIDATION.md)。真实 AstrBot/OneBot 加载与用户联合验收尚未进行。

## 方案与开发依据

- 用户提供的 [方案讨论：获取星星位置](https://chatgpt.com/share/6ac87d35-4590-83e8-977c-329d44d16ea4)，作为功能方向与分期设计参考。
- AstrBot 官方 [新插件指南](https://docs.astrbot.app/dev/star/plugin-new.html)、[最小实例](https://docs.astrbot.app/dev/star/guides/simple.html)、[消息事件](https://docs.astrbot.app/dev/star/guides/listen-message-event.html)、[插件配置](https://docs.astrbot.app/dev/star/guides/plugin-config.html)，接口核对日期：2026-10-09。
- Skyfield [历表](https://rhodesmill.org/skyfield/planets.html)、[坐标](https://rhodesmill.org/skyfield/coordinates.html)与[时间系统](https://rhodesmill.org/skyfield/time.html)，JPL [Horizons API](https://ssd-api.jpl.nasa.gov/doc/horizons.html)与[坐标输出定义](https://ssd.jpl.nasa.gov/horizons/manual.html)，核对日期：2026-10-09。

## 版本记录

- `0.1.0`：创建独立插件与规范骨架；加入独立本地行星计算、时间分辨率、浏览器调试入口与真实数据验证。计算能力尚未接入 AstrBot 指令。
