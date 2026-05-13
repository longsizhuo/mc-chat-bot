# gamebot/games/df · 三角洲行动 QQ bot

把 [`scripts/df_stats/`](../../../scripts/df_stats/) CLI 工具包装成 QQ 群 bot。

## 功能

| 触发 | 行为 |
|---|---|
| **每天 06:00 自动** | 把 5 张图当日密码推到 DF 群 |
| 群里发 "今日密码 / 三角洲密码 / 地图密码" | 关键词命中 → 立即返回密码（不走 AI 省 token） |
| 群里发 "我玩牧羊人" / "骇爪是我" / "alias 老张 威龙" | 干员别名注册（支持打错容错） |
| `@MCBot <任意问题>` | AI 接管，自动调 `[CMD:df_*]` 工具拉真实数据 |

## 文件

| 文件 | 职责 |
|---|---|
| `bridge.py` | `DFStatsBridge` —— 路由群消息、定时广播、关键词识别、AI converse 循环。`reply()` 接收 `at_qq_list` 处理 @ 引用 |
| `abilities.py` | `DFAbilities` —— LLM 工具集（包括 `df_set_alias` / `df_note` / `df_lookup` 等），`build_system_prompt()` 从 `prompt.md` 读模板 |
| `aliases.py` | `DFAliases` —— 群友昵称 ↔ 干员 ID 映射，含模糊匹配 + "@XX 为 YY" 句式解析 |
| **`prompt.md`** | **system prompt 模板**（教练人设、工具调用纪律、各种语义识别规则）。改 prompt 文案直接编辑这个 `.md` 文件，下一条群消息就生效，**不用动代码** |

## AI 工具列表

| 工具 | 用途 |
|---|---|
| `df_secret` | 今日 5 张图密码 |
| `df_recent N` | 最近 N 局战绩列表 |
| `df_summary P` | P 页汇总（撤离率/收益/常用图/常用干员）|
| `df_advice` | 全部历史驱动的战术建议 |
| `df_match N` | 单局战报（含队友+别名）|
| `df_aliases` | 当前别名表 |
| `df_profile` | 角色卡 + 生涯总数据 |
| `df_help` | 帮助指南 |
| `df_lookup <ID或名>` | 查干员对照（本地→ luoy-oss 远程社区表）。**关键**：bot 遇到不认识的干员时主动调用 |
| `df_register_op <ID> <名>` | 把新干员写入本地（持久化到 `data/df_extra_ops.json`，下次启动自动加载）|

## 配置（`config.yml`）

```yaml
df_stats:
  enabled: true
  group_id: 257381453                                            # 三角洲群号，严格隔离
  secret_curl: "scripts/df_stats/credentials/raw_curl_secret.sh"
  record_curl: "scripts/df_stats/credentials/raw_curl.sh"
  profile_curl: "scripts/df_stats/credentials/raw_curl_profile.sh"
  season_curl: "scripts/df_stats/credentials/raw_curl_season.sh"
  aliases_path: "data/df_aliases.json"
  broadcast_hour: 6
  enable_ai: true                                                # 关键词/别名不命中时是否走 AI
```

## 数据流

```
QQ 群消息 ─→ ChatBot._on_qq_message ─→ if group_id == df_stats.group_id:
                                          └─→ df.bridge.reply(group_id, nickname, message)
                                                ├─ 1. aliases.try_parse  (regex 识别"我玩XX")
                                                ├─ 2. handle_keyword     (关键词 → fetch_daily_secret)
                                                └─ 3. converse           (AI tool 循环 → DFAbilities.execute)
                                                          │
                                                          └─→ scripts/df_stats/df_stats/*.py  (实际 HTTP 调用)
```

## 关键约束

- **腾讯接口不暴露队友真名**（`nickName` 永远为空字符串）。靠 `aliases.py` 的本地映射识别"老王=牧羊人 30008"。
- **同一干员只能挂一个人**（DF 游戏规则：同队禁同干员）。注册时自动覆盖旧绑定。
- **cookie 几小时到几天就过期**，需要重新抓包。`broadcast_hour` 时段失败会把错误推到群里提醒。
- **acctype 区分两套账号体系**：网页版（`acctype=qc`）和微信小程序版（`acctype=qqmini`）的 cookie 互相不通用。`secret_curl` 走小程序，其他三个走网页版。

## 抓包教程

完整流程在 [`scripts/df_stats/README.md`](../../../scripts/df_stats/README.md)。

## 已知 ID 表

干员名 → ArmedForceId 映射维护在 [`scripts/df_stats/df_stats/maps.py`](../../../scripts/df_stats/df_stats/maps.py)。新赛季干员要手动补 ID（数据库 luoy-oss/deltaforce_id 通常滞后 1-2 个版本）。

## 已知问题 / TODO

- 战绩 v2 接口（`iChartId=450526`）效率比 v1 快 6 倍但没 teammateArr，目前用 v1，未来可混合
- 单局成就卡片（`iChartId=468605`）已识别但还没接入 `df_match` 输出
- 多用户 RoomId 跨账号匹配（精确认人）需要群友各抓 cookie，复杂度高，暂搁置
