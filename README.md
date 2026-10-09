# 星轨神谕 · Astro Oracle

`astrbot_plugin_astro_oracle` 的当前目标是：输入日期或具体时刻，返回对应的真实行星状态，先通过本地联合调试，再考虑 AstrBot 接入。

**已实现独立本地计算原型 `0.1.0`**：八大行星、日/时/分/秒输入分辨率、时区、时间段采样、网页表单与结果表格、三维位置和速度、地心视坐标、JSON 导出与数据溯源。使用真实 JPL DE440s，资源准备后查询可离线执行。

AstrBot 部分仍是 `0.1.0` 说明骨架，提供帮助/状态/开发路线查询；尚未把计算核心连接到插件指令。

## 启动本地联合调试

直接运行本目录的 `launch_local.py`，或在 Windows 已配置 Python 文件关联时双击它。使用系统 Python 启动会自动切换到本项目 `.venv`，检查历表，等待本地服务健康检查通过后打开浏览器，无需手动激活环境。

默认地址：[http://127.0.0.1:8768](http://127.0.0.1:8768)。在启动窗口按 `Ctrl+C` 可结束本次服务。更换端口或禁用自动打开浏览器：

```powershell
python launch_local.py
python launch_local.py --port 8778
python launch_local.py --no-browser
```

当前工作区已准备好 `.venv` 和历表。新克隆的机器需在本插件目录执行一次：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -X utf8 -m local_core.resources
python launch_local.py
```

历表从 [NASA/JPL 官方地址](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440s.bsp) 下载，约 32 MB。`data/ephemeris.json` 记录实际来源、大小、覆盖范围和 SHA-256；查询时不隐式下载数据，也不自动保存输入资料。

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
├── local_core/             时间解析、真实历表计算与本地 HTTP 服务
├── web/                    本地浏览器表单与结果表格
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

恒星、特征提取、研究评估与 AstrBot 接入在联合调试后按实际需要开展，见 [开发路线](docs/ROADMAP.md)。

## 本地验证

准备真实历表后，使用本项目环境执行：

```powershell
uvx ruff check .
uvx ruff format --check .
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -X utf8 -m pytest -q
.\.venv\Scripts\python.exe -X utf8 -m tools.verify_browser
.\.venv\Scripts\python.exe -X utf8 -m tools.verify_horizons
```

浏览器验证工具使用独立无头 Chrome 和任务自有随机端口，结束后关闭浏览器与服务。Horizons 工具逐条查询官方接口并保存响应，再次执行优先使用匹配的真实响应缓存；`--refresh` 可重新获取。原始报告与截图保存在被忽略的 `data/`。

已完成的本地检查、官方参考差异及其限度见 [验证记录](docs/VALIDATION.md)。真实 AstrBot/OneBot 加载与用户联合验收尚未进行。

## 方案与开发依据

- 用户提供的 [方案讨论：获取星星位置](https://chatgpt.com/share/6ac87d35-4590-83e8-977c-329d44d16ea4)，作为功能方向与分期设计参考。
- AstrBot 官方 [新插件指南](https://docs.astrbot.app/dev/star/plugin-new.html)、[最小实例](https://docs.astrbot.app/dev/star/guides/simple.html)、[消息事件](https://docs.astrbot.app/dev/star/guides/listen-message-event.html)、[插件配置](https://docs.astrbot.app/dev/star/guides/plugin-config.html)，接口核对日期：2026-10-09。
- Skyfield [历表](https://rhodesmill.org/skyfield/planets.html)、[坐标](https://rhodesmill.org/skyfield/coordinates.html)与[时间系统](https://rhodesmill.org/skyfield/time.html)，JPL [Horizons API](https://ssd-api.jpl.nasa.gov/doc/horizons.html)与[坐标输出定义](https://ssd.jpl.nasa.gov/horizons/manual.html)，核对日期：2026-10-09。

## 版本记录

- `0.1.0`：创建独立插件与规范骨架；加入独立本地行星计算、时间分辨率、浏览器调试入口与真实数据验证。计算能力尚未接入 AstrBot 指令。
