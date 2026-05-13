# 三角洲行动战绩抓取（df_stats）

> POC 阶段：先做单用户 CLI，验证社区 API 能跑通后再接进 mc-chat-bot。

## 一、抓 cookie（仅需做一次）

社区 API 是逆向出来的，腾讯不提供登录接口，**access_token 得自己抓**。

1. 浏览器打开 <https://df.qq.com/cp/record202410ver/>，扫码登录（微信或 QQ）。
2. F12 打开 DevTools → **Network** 面板，勾上 "Preserve log" 防止跳转后丢请求。
3. 在战绩页里切换 "烽火行动 / 全面战场" tab，或翻页，触发一次战绩请求。
4. 在 Network 里找返回了 `jData.data: [...]` 数组的那条请求（一般路径里带 `ide` 或 `fcg`，host 多半是 `comm.ams.game.qq.com`）。
5. 右键 → **Copy** → **Copy as cURL (bash)**。
6. 把整段贴到 `credentials/raw_curl.sh`。

**重要**：access_token 是有有效期的（通常几小时到几天），过期了重抓一次就行。

## 二、验证

```bash
cd /home/ubuntu/mc-chat-bot/scripts/df_stats

# 基础
python cli.py probe                       # 检查 curl 解析（不发请求）
python cli.py recent                      # 最近一页战绩
python cli.py summary --pages 10          # 10 页汇总
python cli.py raw --page 1                # 原始 JSON

# 深度分析（Phase 1.5）
python cli.py breakdown --pages 10         # 地图/干员/时段全部拆分
python cli.py breakdown --dim hour         # 只看时段（几点状态最好）
python cli.py breakdown --dim map          # 只看地图
python cli.py highlights --top 5           # 最赚 / 最亏的 5 局
python cli.py teammates --pages 10         # 单排 vs 开黑 + 长期搭档识别

# 单局战报 + 建议生成
python cli.py match --count 5              # 最近 5 局完整战报（自己+全部队友）
python cli.py advice --pages 10            # 基于历史数据生成战术建议

# 生涯 / 赛季（需要额外抓两个 curl，见下）
python cli.py profile                       # 角色名 + 头像 + 生涯总数据
python cli.py seasons                       # 所有赛季横向对比表
```

## 多接口 curl 文件

不同接口走不同的 iChartId，需要分别抓包：

| 文件 | iChartId | 域名 | 用途 |
|---|---|---|---|
| `credentials/raw_curl.sh` | 319386 | dfm.ams.game.qq.com | 战绩列表（type=4/5、分页） |
| `credentials/raw_curl_profile.sh` | 316964 | dfm.ams.game.qq.com | 角色绑定信息（昵称、UID） |
| `credentials/raw_curl_season.sh` | 317814 | dfm.ams.game.qq.com | 赛季生涯数据（seasonid=0~9） |
| `credentials/raw_curl_secret.sh` | 316969 | **comm.ams.game.qq.com** | **今日 5 张图密码**（小程序专属） |

前 3 个是**网页版**（df.qq.com）抓的，acctype=qc；最后一个是**微信小程序**（servicewechat.com）抓的，acctype=qqmini —— **两套独立的认证**，互相不能复用。

抓包时在 DevTools Network 里按 iChartId 过滤就能定位到对应请求。

## Phase 2：mc-chat-bot 集成

`mcbot/df_stats_bridge.py` 把 `secret` 命令接进了 bot：

- ⏰ **每日 06:00 自动播报**今日地图密码到 QQ 群
- 🔍 **关键词触发**：群里发"今日密码 / 三角洲密码 / 地图密码 / df密码 / df secret"→ 立即返回当日密码
- ❌ cookie 过期自动通知群里

在 `config.yml` 加：
```yaml
df_stats:
  enabled: true
  secret_curl: "scripts/df_stats/credentials/raw_curl_secret.sh"
  broadcast_hour: 6
```

然后 `sudo systemctl restart mc-chatbot.service`。

## 数据深度说明

接口暴露的字段（每场记录 + 每个队友）：
- 英雄（ArmedForceId）、撤离结果（成功/被击杀/失败）
- 击杀数（K）、AI 击杀数、救助次数（Rescue）
- 带出价值（FinalPrice）、净收益（flowCalGainedPrice）
- 存活时长（DurationS）、地图、时间

**接口不暴露**的（这是腾讯官方接口的限制，不是工具问题）：
- 伤害数值、命中率、爆头数、武器使用记录
- 助攻数、真实玩家 ID（nickName 总是空，只用 ArmedForceId 区分）
- 物品携入/带出明细（只有总值）

社区还有"战绩 v2"接口存在，但规格被加密了——目前拿不到。

## 三、目录结构

```
df_stats/
├── README.md                   # 本文件
├── cli.py                      # 命令行入口
├── credentials/
│   ├── raw_curl.sh.example     # 抓包示例（提交到 git）
│   └── raw_curl.sh             # 你的真实抓包（gitignored）
└── df_stats/
    ├── __init__.py
    ├── curl_parser.py          # 'Copy as cURL' → 结构化字段
    ├── client.py               # HTTP 客户端，复用 cookie 调多个接口
    ├── endpoints.py            # 战绩接口封装（type=4/5、翻页）
    ├── parsers.py              # raw JSON → 人话格式化 + 聚合统计
    └── maps.py                 # MapId / 干员 ID → 中文（不完整，欢迎补）
```

## 四、已知接口（来自 [Apifox 社区文档](https://df-api.apifox.cn/)）

| type | 含义 | 状态 |
|------|------|------|
| 1 | 登录设备 | 未实现 |
| 2 | 道具流水 | 未实现 |
| 3 | 货币 | 未实现 |
| **4** | **烽火行动战绩** | **已实现** |
| **5** | **全面战场战绩** | **已实现** |

接口基于同一个 AMS 入口，只换 `type`、`iChartId`、`sIdeToken` 三个 query 参数，
所以扩展新接口只要在 `endpoints.py` 加个函数，传不同的参数模板。

## 五、Roadmap

- [x] Phase 1：单用户 CLI 跑通战绩拉取
- [ ] Phase 2：补 MapId / 干员 ID 映射（需要多次抓包对照）
- [ ] Phase 3：接入 mc-chat-bot — 让 QQ 群里 @bot 就能查战绩
  - 多用户 cookie 存储（每个 QQ 号一份）
  - cookie 过期检测 + 友好提示
  - 加入 AI 工具调用循环（abilities）
- [ ] Phase 4：周报功能（每周战绩自动播报到群）

## 六、注意事项

- 这是逆向 API，严格说违反腾讯 TOS，**仅供个人/小群使用**，别公开服务。
- access_token 视同账号密码，**绝对不要 commit 到 git**（已加 `.gitignore`）。
- 接口字段可能随版本变化，遇到 KeyError 看 `raw` 命令输出对照。
