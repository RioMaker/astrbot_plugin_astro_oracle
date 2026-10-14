# 紫微调用记录与 LLM 工具

## 记录范围

`record_ziwei_queries` 默认开启。只记录已经通过日期语法校验、有显式公历时间参数的 QQ 群紫微调用；年、年月及完整日期沿用现有解析方式。指令 `/紫微星图`／`/紫薇星图` 和工具 `generate_ziwei_chart` 共用记录流程。当前时间、只指定地点、帮助、语法错误、禁用入口、普通星图、私聊及其他平台不会创建记录。

调用者身份在第一次异步等待前从 `AstrMessageEvent` 固定：平台类型、平台实例 ID、群 ID、发送者 ID 和消息 ID。平台实例参与隔离，模型不能传入群号或成员替换身份。QQ 官方适配器额外校验原始事件的 `group_openid`，排除 QQ 频道。记录归属是发起调用的成员，不推断所查日期是本人生日。每次调用追加独立 UUID，同一个人可查询多个日期。

数据库使用 Python 标准库 SQLite，路径为 AstrBot 数据目录下 `plugin_data/astrbot_plugin_astro_oracle/ziwei_calls.sqlite3`，第一次符合条件的调用时创建。数据库和图片均不进入 Git；每次连接在后台线程内使用并关闭，不新增运行依赖。关闭记录配置不删除已有历史，插件重载和重启后历史保留。

## 字段与状态

`ziwei_calls` 表保存：

- `record_id`、UTC 调用时间／结束时间、平台／群／成员／消息标识及来源 `command` 或 `llm`。
- `input_time_text`、`input_place_text`、`input_timezone_override` 和 `defaults_json`，保留输入精度与实际补齐依据。
- `result_json`：与图片同一次计算产生的 UTC／当地时刻、时区、时间补齐说明、地点、渲染版本及农历／命身宫／五行局摘要。
- `status` 与固定分类的 `error_code`。不保存异常正文、完整聊天、图片字节或图片路径。

状态从 `pending` 更新为 `sent`、`send_failed`、`failed` 或 `cancelled`。`sent` 表示图片发送接口正常完成，不代表远端用户已读或平台已确认收到。生成失败不写伪造的计算结果；发送失败仍保留已生成的结果元数据。进程被强制结束时未完成记录可能保留 `pending`，不得当作成功。

存储失败不会中断排盘，指令会提示记录失败，工具会在返回值中给出 `recorded: false` 和 `record_warning`。没有提供按 QQ 批量查询或向模型读取其他成员历史的入口。

## AI 调用

使用 AstrBot 官方 `@filter.llm_tool` 注册 `generate_ziwei_chart`，`Args:` 声明一个 `query(string)` 参数。例如：

```json
{"query": "200010100100"}
```

也可输入 `北京 2026-10-14 20:00:00` 或追加 `tz=UTC+08:00`。缺时分秒沿用配置，出厂为 08:00；仅用户请求当前图时明确传空字符串。遗漏参数或传入非字符串会返回参数错误，不会默认为当前时间。工具根据当前会话发送图片，返回 JSON 状态、精简计算摘要及是否记入历史，不返回图片字节。

工具与指令共用 `enabled`，工具另受 `enable_ziwei_llm_tool` 控制。工具执行不调用 `stop_event()`，让 AI 正常消费结果；指令维持现有停止事件与固定会话发送方式。未增加全量消息监听或后台主动发图。

需要运行端的模型支持工具调用，且 AstrBot 当前人格允许使用该工具。本地接口验收不等于真实模型已选中工具或 QQ 已收到图片。当前发送路径复用 `Context.send_message`，不改变既有 OneBot／aiocqhttp 与平台会话路由；是否正常投递仍须在实际适配器上验收。

接口依据：[官方 LLM 工具文档](https://docs.astrbot.app/dev/star/guides/ai.html)、[4.28.1 QQ 群与频道事件源码](https://github.com/AstrBotDevs/AstrBot/blob/v4.28.1/astrbot/core/platform/sources/qqofficial/qqofficial_platform_adapter.py#L197-L230)。本地验证方法与范围见[验证记录](VALIDATION.md)。
