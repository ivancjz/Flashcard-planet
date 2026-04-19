# Flashcard Planet — 全 TCG 扩张战略交付包

*完整 4 文档 + 使用指南*
*2026 年 4 月 · v1*

---

## 文档清单

| # | 文档 | 用途 | 交给谁 |
|---|---|---|---|
| 01 | [架构 Audit 与 Claude Code 可执行任务包](01_architecture_audit_tasks.md) | 把 "后端 game-agnostic 化" 拆成 17 个 Claude Code 可执行任务(TASK-000 到 TASK-016) | Claude Code / 工程师 |
| 02 | [跨 TCG 信号算法设计与 Schema](02_cross_tcg_signal_design.md) | 完整的算法 + SQL schema + 可直接 paste 的伪代码 | 工程师 / PM |
| 03 | [Pro Tier 定价页面文案](03_pricing_page_copy.md) | 中英双语、feature table、5 处 CTA 位置、FAQ、A/B 建议 | 前端 / 设计师 / PM |
| 04 | ["Why Multi-TCG Now" 对外定位文稿](04_multi_tcg_pitch.md) | 30 秒 / 2 分钟 / 一页纸 / 7 分钟 / 博客 五个版本 | 创始人 / 市场 |

---

## 使用路径

### 如果你现在就要动手写代码

直接跳到 `01_architecture_audit_tasks.md`,从 **TASK-000** 开始。
TASK-000 是一个"盘点任务"——让 Claude Code 扫描你的代码库,生成一份
audit report。这个报告会告诉你下面 16 个 task 哪些适用、哪些需要改路径。

执行方式:

```bash
# 伪示意 —— 实际看你的 Claude Code 工作流
# 把 TASK-000 的 prompt 粘贴进去,执行

# 拿到 audit_report.md 后,对照调整后续 task 的路径假设
# 然后一个接一个跑 TASK-001、TASK-002、...

# 每个 task 完成后,跑一次完整测试,确认 138 个测试继续全绿
```

### 如果你要做 Pro 上线准备

按顺序看:`03_pricing_page_copy.md` → 把文案交给前端。

同时:`04_multi_tcg_pitch.md` 的 v5 博客版本可以准备好,等 Pro 上线
或 Yu-Gi-Oh 上线那天发布。

### 如果你要融资 / 找合作

直接看 `04_multi_tcg_pitch.md`,v3 一页纸和 v4 7 分钟 deck 是两个
最可能直接用的版本。

### 如果你要设计 Cross-TCG Signal

`02_cross_tcg_signal_design.md` 是最详细的技术文档,里面的 SQL schema
可直接 migrate,Python 伪代码已经接近生产级别。

---

## 关键决策点(需要你确认)

在开始执行前,有几个地方需要你(或 product owner)明确拍板:

### 决策 1 — 接入顺序

推荐 Yu-Gi-Oh → MTG → OPTCG → Lorcana

但如果你的用户群主要是 MTG 玩家,或者你对 MTG 市场更熟,可以先做 MTG。
Scryfall 合规架构在 01 里有详细说明,不是阻塞 blocker。

**你的决定:** ________________

### 决策 2 — Pro 定价

推荐 $12/月 (¥88) — 介于 MTGStocks $5 和 Card Ladder $20 中间。

如果 beta 期希望激进获客,可以 $9;如果瞄准高阶用户,可以 $15。

**你的决定:** ________________

### 决策 3 — Trader 层是否上线

**强烈建议上线第一版时只做 Free + Pro**,有 100+ Pro 用户后再引入 Trader。
过早分三层会稀释决策。

**你的决定:** ________________

### 决策 4 — 品牌保留 Flashcard Planet 还是 rename

"Flashcard Planet" 这个名字在"Pokemon only"时问题不大,转到"多 TCG
市场智能"后听起来偏软(像学习工具)。

选项:
- A. 保留,加 tagline "Market intelligence for every TCG"
- B. Rename 为 CardPulse / TCGSignal / CardSignal 等更硬核名字
- C. 保留主品牌,产品内部新 feature 用子品牌(如 "Flashcard Planet Signals")

**你的决定:** ________________

### 决策 5 — Cross-TCG IP tag 白名单的范围

02 文档里给了一个初始 KNOWN_FRANCHISES 列表,约 30 个 franchise。

选项:
- A. 严格白名单(30 个)—— 减少 LLM 幻觉,但可能漏掉一些小众 IP
- B. 宽松白名单(100+)—— 更全,但需要更多审核
- C. 无白名单 + 事后人工审核 —— 最灵活,最贵

**你的决定:** ________________

---

## 交付这些文档给 Claude Code 的最佳实践

如果你要把任务 promp 一条条交给 Claude Code,建议这样组织:

**第一步 — 建立 project context**

在项目根目录创建 `CLAUDE.md`,内容:

```markdown
# Flashcard Planet — Project Context for Claude Code

## Mission
We are migrating Flashcard Planet from a Pokemon-only TCG signal platform 
to a multi-TCG market intelligence platform. Target games (in order):
Pokemon (already live) → Yu-Gi-Oh → MTG → One Piece TCG → Lorcana.

## Architecture principles
1. Every new feature must be game-agnostic. If the design only works for
   Pokemon, that's a bug.
2. We respect third-party API terms, especially Scryfall's no-paywall clause.
3. Existing 138 tests must pass after every task. Never break them.
4. Pokemon user experience must not degrade during the migration.

## Where to find design docs
- Architecture tasks: docs/strategy/01_architecture_audit_tasks.md
- Cross-TCG design: docs/strategy/02_cross_tcg_signal_design.md
- Pricing copy: docs/strategy/03_pricing_page_copy.md

## Key data models
- Asset: the canonical card entity (will soon have `game` field)
- Observation: a raw eBay/TCGplayer sale record
- PricePoint: an aggregated daily price
- Signal: a BREAKOUT/MOVE/WATCH/IDLE flag on an asset
- User.access_tier: "free" | "pro" | "trader"
```

**第二步 — 按顺序运行 task**

不要一口气把 16 个 task 全扔给 Claude Code。一次一个,跑完 + 测试 +
commit + 回归,再下一个。

**第三步 — 在每个 task 里引用前一个 task 的产出**

TASK-001 的产出(`game` 字段)是 TASK-002 的输入。在 TASK-002 的 prompt
里明确告诉 Claude Code:"基于 TASK-001 已经建好的 Game enum 和 GAME_CONFIG"。

**第四步 — 不要跳过 TASK-000**

那个 audit report 会告诉你很多"我们不知道的已知问题"—— 可能你的代码里
有一个写死的 Pokemon set 列表,或者某个测试 fixture 假设所有卡都是
Pokemon。一次性发现,比后面一个 task 一个 task 撞墙好得多。

---

## 总时间预估

| 阶段 | 任务 | 预计工期(FTE) |
|---|---|---|
| Phase 0 | TASK-000 audit | 1 天 |
| Phase 1 | TASK-001-003 数据模型 + client 抽象 | 5-8 天 |
| Phase 2 | TASK-004-005 signal 引擎 game-aware | 3-5 天 |
| Phase 3 | TASK-006 eBay pipeline | 2-3 天 |
| Phase 4 | TASK-007-008 Web UI game selector | 5-7 天 |
| Phase 5 | TASK-009-011 Yu-Gi-Oh 上线 | 8-12 天 |
| Phase 6 | TASK-012-014 MTG 上线 | 10-15 天 |
| Phase 7 | TASK-015-016 IP tagging + Cross-TCG | 7-10 天 |
| **总计** | | **41-61 天** |

这是 **1 位熟练工程师全职** 的时间估算,符合 12 周(60 工作日)路线图。

如果你是兼职投入或团队有 2 人,对应拉长或缩短。

---

## 三个月后的回顾 checklist

12 周后(约 2026 年 7 月中),对照这个 checklist 做自我评估:

- [ ] Pokemon 仍然正常运行,138 个测试全绿
- [ ] Yu-Gi-Oh 完整上线,Web UI 可用,Discord bot 支持
- [ ] MTG 完整上线,Scryfall 合规性无投诉
- [ ] Cross-TCG Movers 功能已上线,至少产出过 5 条真实 signal
- [ ] Pro tier 已上线(mock / manual 或真正 Stripe),至少 10 个付费用户
- [ ] KPI 面板上线,每日核心指标可监控
- [ ] 对外已发布 "Why Multi-TCG" 博客,Reddit 有讨论
- [ ] 至少 1 个 TCG Discord 社群的 partnership
- [ ] 如在 fundraising,至少完成 10 次投资人会议

如果 7/9 勾选,说明 12 周计划成功。5/9 以下需要回看是否方向出错,不只是执行慢。

---

## 最后的话

这套文档的核心假设是:**战略方向正确比执行速度重要**。

过去 9 个月你把技术栈做到了工程级别,这是护城河的第一块。接下来 3 个月,
决定 Flashcard Planet 会是 "又一个 Pokemon 工具" 还是 "TCG 市场智能的
唯一跨游戏玩家" 的,不是代码量,是**定位的锐利度**。

- 不做体育卡(不跨越到 Card Ladder 的地盘)
- 不做 Funko/漫画(不稀释成 Collectr 那样的泛收藏)
- **做好 TCG 这一块,做到市面上没有第二家可以说"我们也做这个"**

祝执行顺利。任何 task 落地时发现假设和你的实际代码不符、或者需要我帮你
改写某个具体 task 的 prompt,直接说。
