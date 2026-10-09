# 星轨神谕 · Astro Oracle

`astrbot_plugin_astro_oracle` 是以真实天体状态为基础，逐步开展特征提取与可验证规律探索的 AstrBot 插件。

**当前版本：`0.1.0`，项目骨架。** 已提供标准插件入口、配置及帮助/状态/开发路线指令；天文计算引擎、星表、历表和研究分析尚未接入。

## 使用指令

| 指令 | 功能 |
| --- | --- |
| `/星轨神谕` 或 `/星轨神谕 帮助` | 查看说明与当前能力 |
| `/星轨神谕 状态` | 查看版本及开发状态 |
| `/星轨神谕 路线` | 查看分阶段开发计划 |
| `/astro_oracle help`、`status`、`roadmap` | 对应功能的英文入口 |

指令前缀与唤醒方式遵循 AstrBot 的实际配置。当前指令只返回文本说明，不接收或保存出生资料。

## 安装与配置

开发基线为 Python 3.10+、AstrBot 4.24.0+。将本目录作为独立插件放入 AstrBot 的 `data/plugins/astrbot_plugin_astro_oracle/`，然后从 WebUI 重载或重启 AstrBot。当前本地仓库尚无远程地址，`metadata.yaml:repo` 留空。

当前没有额外第三方运行依赖；AstrBot 在其运行环境中提供 `astrbot` 模块。插件入口不作为独立 Python 程序运行。

WebUI 配置项：

| 字段 | 默认值 | 行为 |
| --- | --- | --- |
| `enabled` | `true` | 启用说明指令；设为 `false` 后仅提示插件已关闭 |

运行配置由 AstrBot 管理。后续的历表、星表和计算缓存应存储于 `data/plugin_data/astrbot_plugin_astro_oracle/`，当前版本不创建这些数据。

## 项目结构

```text
astrbot_plugin_astro_oracle/
├── main.py                 AstrBot 指令入口
├── metadata.yaml           插件元数据
├── _conf_schema.json       WebUI 配置定义
├── requirements.txt        运行依赖声明
├── pyproject.toml          Ruff 检查与格式配置
├── AGENTS.md               插件专属开发约定
├── README.md               使用与当前能力
└── docs/ROADMAP.md          阶段任务、接口规划和验收要求
```

计算核心、特征提取和研究评估在后续阶段按实际需要建立，详细说明见 [开发路线](docs/ROADMAP.md)。

## 本地验证

使用独立开发环境或现有开发工具执行：

```powershell
uvx ruff check .
uvx ruff format --check .
python -m py_compile main.py
```

语法和模拟接口冒烟只能验证骨架行为。真实 AstrBot 加载、消息平台集成与天文计算精度分别验收；当前尚未完成真实运行环境加载验证。

## 方案与开发依据

- 用户提供的 [方案讨论：获取星星位置](https://chatgpt.com/share/6ac87d35-4590-83e8-977c-329d44d16ea4)，作为功能方向与分期设计参考。
- AstrBot 官方 [新插件指南](https://docs.astrbot.app/dev/star/plugin-new.html)、[最小实例](https://docs.astrbot.app/dev/star/guides/simple.html)、[消息事件](https://docs.astrbot.app/dev/star/guides/listen-message-event.html)、[插件配置](https://docs.astrbot.app/dev/star/guides/plugin-config.html)，接口核对日期：2026-10-09。

## 版本记录

- `0.1.0`：创建独立插件仓库、规范骨架、基础说明指令和阶段规划。
