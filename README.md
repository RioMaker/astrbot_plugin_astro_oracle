# 星轨神谕 · Astro Oracle

`astrbot_plugin_astro_oracle` 的当前插件功能是：按时间与地点生成一张标题为「星图」的双半球图片，默认当前时刻、北京。图中包含真实恒星、七个行星目标、可选星座连线及地球遮挡的暗面。

**已实现独立本地计算原型 `0.1.0`**：八大行星、日/时/分/秒输入分辨率、时区、时间段采样、网页表单与结果表格、三维位置和速度、地心视坐标、JSON 导出与数据溯源。使用真实 JPL DE440s，资源准备后查询可离线执行。

现在支持出生地观测视角的双半球星图：本地城市/乡镇搜索与经纬度校正、上半球与地球遮挡下半球、真实恒星星表、行星视星等估计、可选星座连线、名称提示和双图 PNG/JSON 导出。

AstrBot 星图指令已接入同一计算核心，图片由本地 Pillow 生成，不依赖浏览器或远程文转图服务。当前版本为 `0.1.2`，包含核心依赖、首次返回和下载错误提示修复，并提供离线公共资源包；真实 AstrBot/OneBot 回图仍待联合验收。

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

## AstrBot 星图指令

| 指令 | 功能 |
| --- | --- |
| `/星图` | 当前时刻、默认北京 |
| `/星图 help` 或 `/星图 帮助` | 使用说明与当前配置 |
| `/星图 time 2026-10-10 20:30:00` | 指定时间，使用默认地点；子指令也可写 `时间` |
| `/星图 place 上海` | 指定地点，使用当前时刻；子指令也可写 `地点` |
| `/星图 at 2026-10-10 20:30:00 上海` | 指定时间和地点；子指令也可写 `时地` |

**四个前缀 `/星图`、`/xingtu`、`/xt`、`/star` 对所有子指令完全等效**，例如 `/xt help`、`/xingtu 时间 2026-10-10`、`/star at 2026-10-10 20:30 上海`。指令前缀与唤醒方式遵循 AstrBot 的实际配置。旧的说明骨架指令已移除，现阶段只提供这组星图指令，不注册全量监听或 LLM Tool。

AstrBot 指令每次返回一张同一时刻的双半球图。与本地网页的区间采样不同，插件按配置补齐缺少的时分秒，并在图片上写明实际采用的时刻及补齐说明：

| 输入时间 | 默认配置为 `12:00:00` 时 |
| --- | --- |
| 不提供时间（`/星图` 或 `place`） | 接收指令的当前时刻，不使用补齐值 |
| `2026-10-10` | `2026-10-10 12:00:00` |
| `2026-10-10 09` | `2026-10-10 09:00:00` |
| `2026-10-10 09:30` | `2026-10-10 09:30:00` |
| `2026-10-10 09:30:04` | 按完整输入，保留指定秒 |

地点使用本地 GeoNames 城市/乡镇库。时间按所选地点的时区解释；同名或模糊查询返回候选编号，用 `/star place #5128581` 明确选择纽约。也可使用 `/xt place 39.9075,116.39723` 校正经纬度，经纬度定位的默认时区可配置。在指令末尾加 `tz=UTC+08:00` 或 `tz=America/New_York` 可覆盖时区；夏令时歧义需用显式偏移确认。输入使用公历。

图片标记地平线以上和地球遮挡方向，北朝上，上图东在左、暗面东在右；底部列出行星高度和模型视星等。恒星名称会适量避让，行星名称始终标记。上下半球划分和实际肉眼可见性的区别见 [星图说明](docs/SKY_CHART.md)。用户查询与生成图片仅存在内存中，不自动保存。

## AstrBot 安装与配置

开发基线为 Python 3.10+、AstrBot 4.24.0+。将本目录作为独立插件放入 AstrBot 的 `data/plugins/astrbot_plugin_astro_oracle/`，然后从 WebUI 重载或重启 AstrBot。当前本地仓库尚无远程地址，`metadata.yaml:repo` 留空。

AstrBot 在其运行环境中提供 `astrbot` 模块，并按 `requirements.txt` 安装计算与图片依赖。插件随附独立的 OFL 中文字体，可在 Windows 或 Linux 上本地绘图；无需 Chrome、Playwright 或远程文转图服务。插件入口不作为独立 Python 程序运行。

Pillow 使用兼容范围 `>=11.3.0,<13`，可沿用 AstrBot 核心已有的 `12.3.0`。旧版 `0.1.0` 固定 `11.3.0`，会被 AstrBot `4.28.1` 的核心依赖保护拦截；遇到该冲突请更新到本版本后重载，不要降级 AstrBot 核心依赖。帮助、准备提示和图片均通过固定会话路由发送，入口用普通异步协程完成，避免停止事件后的 `yield` 截断首次计算。

WebUI 配置项：

| 字段 | 默认值 | 行为 |
| --- | --- | --- |
| `enabled` | `true` | 启用星图指令 |
| `default_place` | `北京` | 默认城市；也支持 `#编号` 或 `纬度,经度` |
| `default_time` | `12:00:00` | 补齐不完整时间中的缺失字段，不影响无参数的当前时刻 |
| `coordinate_timezone` | `Asia/Shanghai` | 直接输入经纬度时的默认时区；城市自动采用地点时区 |
| `magnitude_limit` | `6` | 显示恒星星等上限，范围 -2 至 8 |
| `show_constellation_lines` | `true` | 星座连线开关 |
| `show_star_names` | `true` | 知名恒星名称开关，行星名称始终显示 |
| `show_constellation_names` | `true` | 连线开启时的星座名称开关 |

运行配置由 AstrBot 管理。首次星图查询会提示资源准备，在工作线程中下载并校验公共数据；后续查询可离线执行。历表、星表和公共来源记录保存在框架提供的 `data/plugin_data/astrbot_plugin_astro_oracle/`，不依赖插件内的本地调试 `data/`。重载或卸载会等待已提交的计算结束后关闭历表与工作线程。

若希望首次聊天前预先准备，在 AstrBot 的 Python 环境中运行本插件资源入口，并用 `--data-dir` 指向上述框架数据目录。数据地址、大小及许可见前文；公开数据下载不会上传用户时间和地点。现有本地调试数据与 AstrBot 数据目录分别管理，代码不自动跨目录复制。

### 下载站点连接超时：导入离线资源

如果运行日志在下载 JPL `DE440s` 时出现 `httpx.ConnectTimeout`，程序尚未进入星图计算。下载错误会在群内显示具体资源和原因；未就绪时提示“检查并准备、复用完整文件”，每次重试不会被误称为首次下载。

将 `astro_oracle_resources.zip` 上传到运行端，**解压到框架的 `data/plugin_data/astrbot_plugin_astro_oracle/`**。默认 Docker 布局下是 `/AstrBot/data/plugin_data/astrbot_plugin_astro_oracle/`；不要解压到代码目录 `data/plugins/`。解压后目录直接包含 `de440s.bsp`、`ephemeris.json` 和 `sky/manifest.json` 等文件，不再套一层压缩包名称文件夹。使用宿主机挂载目录时，以容器内实际数据目录为准。

重载插件后发送 `/星图`。离线包包含完整原始/编译星表、星座与地点库，每项按来源记录的 SHA-256 校验后复用，可绕过运行端无法连接外部下载站点的问题。资源包与代码分开更新，数据也可供 `0.1.1` 使用。来源与许可保留在包内。

在已准备好真实公共数据的开发环境可重建并验证离线包：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m tools.package_offline_resources
.\.venv\Scripts\python.exe -X utf8 -m tools.verify_offline_resources
```

后者从包内解压到临时目录，禁止所有 HTTP 请求，再用与插件相同的服务生成真实北京 PNG；验证报告在 `data/offline-validation/`。

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
├── assets/fonts/           独立 AstroSans 字体、许可及来源校验记录
├── requirements.txt        计算与星图图片运行依赖
├── requirements-dev.txt    测试和浏览器验证依赖
├── pyproject.toml          Ruff 检查与格式配置
├── AGENTS.md               插件专属开发约定
├── README.md               使用与当前能力
├── tests/                  时间、计算、API 和启动器验证
├── tools/                  浏览器与 JPL Horizons 核对工具
└── docs/                   核心说明、验证记录和阶段规划
```

恒星星图已接入本地原型与 AstrBot 专用指令。特征提取、研究评估等后续功能仍按确认需求开展，见 [开发路线](docs/ROADMAP.md)。

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
.\.venv\Scripts\python.exe -X utf8 -m tools.verify_astrbot_contract
.\.venv\Scripts\python.exe -X utf8 -m tools.verify_astrbot_pipeline
.\.venv\Scripts\python.exe -X utf8 -m tools.preview_bot_chart
```

浏览器验证工具使用独立无头 Chrome 和任务自有随机端口，结束后关闭浏览器与服务。Horizons 工具逐条查询官方接口并保存响应，再次执行优先使用匹配的真实响应缓存；`--refresh` 可重新获取。原始报告与截图保存在被忽略的 `data/`。

`preview_bot_chart` 使用与插件相同的服务输出真实北京 PNG；可用 `--input "time 2026-10-10" --default-time 20:30:11` 检查默认补齐。`verify_astrbot_contract` 使用带 SHA-256 记录的官方 `CommandFilter` 核对四个入口的空参数和完整参数，不启动消息平台。已完成的检查、官方参考差异及其限度见 [验证记录](docs/VALIDATION.md)。真实 AstrBot/OneBot 加载与用户联合验收尚未进行。

## 方案与开发依据

- 用户提供的 [方案讨论：获取星星位置](https://chatgpt.com/share/6ac87d35-4590-83e8-977c-329d44d16ea4)，作为功能方向与分期设计参考。
- AstrBot 官方 [新插件指南](https://docs.astrbot.app/dev/star/plugin-new.html)、[最小实例](https://docs.astrbot.app/dev/star/guides/simple.html)、[消息事件](https://docs.astrbot.app/dev/star/guides/listen-message-event.html)、[插件配置](https://docs.astrbot.app/dev/star/guides/plugin-config.html)，接口核对日期：2026-10-09。
- Skyfield [历表](https://rhodesmill.org/skyfield/planets.html)、[坐标](https://rhodesmill.org/skyfield/coordinates.html)与[时间系统](https://rhodesmill.org/skyfield/time.html)，JPL [Horizons API](https://ssd-api.jpl.nasa.gov/doc/horizons.html)与[坐标输出定义](https://ssd.jpl.nasa.gov/horizons/manual.html)，核对日期：2026-10-09。

## 版本记录

- `0.1.2`：下载失败显示具体资源和原因；去除重复“首次下载”提示；提供可校验的离线公共资源包与禁网实测工具。
- `0.1.1`：兼容 AstrBot 核心 Pillow 12.x；修复停止事件后 `yield` 准备提示导致首次生成未进入计算的问题；增加官方 `4.28.1` 调度代码回归。
- `0.1.0`：独立插件、本地行星计算、时间分辨率、浏览器调试入口与真实数据验证；新增 AstrBot 双半球星图入口。本地实现已获用户确认并授权提交，真实消息平台验收仍待进行。
