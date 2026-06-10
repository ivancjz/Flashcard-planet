# LOOP-GRADE-ARBITRATION — 用评级标准裁决价格

> **类型:** Claude Code 自主执行 loop
> **状态:** `blocked / needs_decision 已解决 → frozen` — 解冻 trigger = Pokémon Public Calls soft launch 完成
> **版本:** v2(2026-06-11)— Iteration-1 blocker 后修订:新增 Stage 0,Stage A 前置修正
> **建议落位:** `docs/loops/LOOP-GRADE-ARBITRATION.md`
> **背景:** 市场对 eBay sold 数据信任度下降(刷单 / best offer 掩盖 / 取消订单仍显示)。竞品(Collectr / Shiny / PriceCharting / TCGFish)全部转售 eBay 裸数据,无人做裁决层。本 loop 把"评级标准裁决价格"建成结构性差异:数据获取(治理门内)→ 档位内统计过滤 → cert 链真实性 → 跨档阶梯一致性 → pop report 稀缺性支撑。

---

## 0. Loop 运行规则(每轮 iteration 必读)

每轮 iteration 严格执行以下循环:

1. **读 state:** 本文件 §5 Progress 表 → `.claude/session-handoff-<latest>.md` → `git log --oneline -10`
2. **取任务:** §5 中最高优先级、`status: ready` 且 precondition 有**生产证据**满足的 stage。precondition 不确定时先跑 SQL / diag endpoint 验证,不允许假设满足
3. **执行:** 一个 stage 一个 branch 一个 PR(CLAUDE.md §3-4 流程,TDD + Codex review)
4. **生产验证:** 部署后跑本文件中该 stage 的验证 SQL,把输出贴进 PR。代码阅读不构成 PASS
5. **更新 state:** §5 表中该 stage 状态推进,附 PR 号 + 验证日期,单独 commit `chore(loop): grade-arbitration stage X done`
6. **检查 stop condition:** 命中任一全局 stop(§6)→ 停止并报告,不进入下一轮

**硬规则:**
- 本 loop 任何 stage 不得插队 Public Calls 相关任务
- 不得跳 stage 顺序;不得在无生产 SQL 输出的情况下标记 stage 完成
- 每轮 iteration 只推进一个 stage;stage 内可多 PR,但同时只有一个 in_progress
- eBay Browse API 数据(ask price)永不写入 `price_history`(CLAUDE.md §2 不变量,本 loop 全程适用)
- 评级数据必须经 shadow admission 治理门(Phase 0 影子准入 → 人工审核 → 启用决策),任何 stage 不得绕过

---

## 1. Stage 0 — 评级数据获取(经 shadow admission 治理门)【v2 新增】

**Status:** `frozen`(trigger: Public Calls soft launch 完成)
**Precondition:** `EBAY_WEB_SOLD_ENABLED` 监控期结论已出且无 P0 级问题

**背景(Iteration-1 发现):** 生产环境零评级成交数据——`price_history` 无 graded 行,`GradedObservationAudit` 影子表为空。ebay_web_sold 当前只覆盖 YGO 未评级。A–D 全部 stage 的数据前提不存在。数据源决策(2026-06-11):**扩展 ebay_web_sold 到 Pokémon 评级查询,走已有 shadow admission 流程**;eBay Marketplace Insights API 官方申请可并行提交(非阻塞);不采购 PriceCharting(转售数据,违背差异化逻辑)。

**Scope:**
- ebay_web_sold 查询扩展:Pokémon 信号卡(从 ~405 张中按 smart sort 取 top N,N 初值 50,预算内可调)增加评级查询变体(`"PSA 10"` / `"PSA 9"` 起步,BGS/CGC 后续)
- 所有评级 observation **只进影子准入路径**(GradedObservationAudit),不写 `price_history`——直到人工审核通过 + Ivan 明确启用决策(该决策为 `needs_decision`,本 loop 不得自行推进到启用)
- 标题解析复用现有 `market_segment` / `grade_company` / `grade_score` 逻辑,不重写
- 监控:每日影子准入行数、解析分布、价格离群比例进 diag endpoint

**Stop condition(stage 内):** 影子数据连续 7 天日增 <10 行 → 停止并报告(查询策略问题,不是堆 query 数量能解决的)

**验收(生产验证):**
```sql
-- 影子表积累:≥14 天数据后,信号卡中至少 20 张有 psa_10 影子观测 n≥5
SELECT COUNT(DISTINCT asset_id)
FROM graded_observation_audit
WHERE market_segment = 'psa_10'
GROUP BY asset_id HAVING COUNT(*) >= 5;
```
- 解析正确性人工抽检 20 条,正确率 ≥90%(核验记录贴 PR)

**Stage 0 完成 ≠ 评级数据启用。** 完成定义 = 影子数据达标 + 审核样本就绪,启用是 Ivan 的独立决策。

---

## 2. Stage A — 呈现层:把清洗变成前台信任资产

**Status:** `frozen`(v2 修正:depends Stage 0 完成 + 评级数据启用决策通过。v1 的"可并入 frontend repositioning 提前做"作废——Iteration-1 证实无数据可呈现)
**Precondition:** methodology page P0 黑屏已修复并验证;评级数据已获启用并进入 `price_history`

**Scope:**
- Card inspector 评级卡 segment 价格不再显示单一数字,改为:过滤后中位数 + 样本量 n + 本期 IQR 剔除数 + 数据源标注
- n < 5 显示低可信标记(复用 smart sort 的 data_quality 因子,不新算)
- 有 CardMarket / TCGplayer 可比 segment 时显示交叉验证状态(一致 / 偏离 / 无可比)
- 全部用 program grammar:card inspector 的一个 panel,不是新页面

**Stop condition(stage 内):** 不新增任何后端计算;signal_service 现有输出不够呈现时,记录缺口到 §7,不扩 scope

**验收(生产验证):**
- 任取 3 张有 psa_10 数据的卡,inspector 显示的中位数与以下 SQL 一致:
```sql
SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY price)
FROM price_history
WHERE asset_id = :id AND market_segment = 'psa_10'
  AND source = 'ebay_sold'
  AND captured_at >= NOW() - INTERVAL '30 days';
```
- 任一已知 n<5 卡显示低可信标记的截图

---

## 3. Stage B — Cert 解析与回填:刷单的直接证据

**Status:** `frozen`(depends: Stage A 完成)
**Precondition:** 影子表 + `observation_match_logs` 评级行的 raw_title NULL census 已跑

**Scope:**
- 相关表加 `cert_number` (nullable text) + `cert_company` 字段,migration 含日期
- 标题解析 PSA/BGS/CGC cert 号(PSA 8 位数字、BGS/CGC 各自格式),独立函数独立测试
- **回填 loop(批处理脚本,参照 backfill_market_segment.py 模式):** 每批 1000 行,支持 --dry-run,先 dry-run 报告解析率再实跑
- 同 cert 重复成交检测:同一 cert_number 在 N 天内 ≥2 笔 sold → 标记 `repeat_cert_sale`(只标记不剔除,数据先积累)
- PSA cert verification API 对接**不在本 stage**,记入 §7

**验收(生产验证):**
```sql
-- 解析率(评级行预期 >40%,低于 20% 报告而非强推)
SELECT market_segment,
       COUNT(*) AS total,
       COUNT(cert_number) AS with_cert,
       ROUND(100.0 * COUNT(cert_number) / COUNT(*), 1) AS pct
FROM observation_match_logs
WHERE market_segment NOT IN ('raw', 'unknown')
GROUP BY market_segment;

-- 重复 cert 检测产出
SELECT cert_number, COUNT(*) AS sale_count
FROM observation_match_logs
WHERE cert_number IS NOT NULL
GROUP BY cert_number HAVING COUNT(*) >= 2
ORDER BY sale_count DESC LIMIT 10;
```

---

## 4. Stage C — 跨档阶梯校验(cross-grade ladder check)

**Status:** `frozen`(depends: Stage B 完成)
**Precondition:** PSA 内部至少 2 个档位 n≥5 的卡数量 ≥50(先跑 census,不满足则延后并记录数字)

**Scope:**
- 对每张卡构建同公司档位中位数阶梯(初版只做 PSA 内部,**不做** BGS↔PSA 跨公司映射)
- 新成交违反阶梯单调性(如 PSA 10 价 < 同卡 PSA 9 中位数)→ 标记 `ladder_violation`,降权进 data_quality,不直接剔除
- 卡级样本不足时 fallback 到 set 级 / 稀有度级先验比值(先验比值表为本 stage 产物)
- 与 IQR 正交叠加:IQR 管档位内,阶梯管跨档
- **已知依赖:** 1st Ed / Unlimited 混档污染阶梯 → 本 stage 启动时重新评估 TASK-802 是否前置

**验收(生产验证):** ladder_violation 标记 SQL 抽样 10 条,人工核验至少 7 条确为可疑(核验记录贴 PR)

---

## 5. Progress(Claude Code 每轮更新此表)

| Stage | 内容 | Status | Trigger / Depends | PR | 验证日期 |
|---|---|---|---|---|---|
| — | **Iteration 1(2026-06-10):STOP。** 生产零评级数据(price_history graded_rows=0,影子表空),v1 全 loop 前提不成立。决议:新增 Stage 0,数据源 = ebay_web_sold 扩展 + shadow admission 治理门 | `resolved` | — | — | 2026-06-11 |
| 0 | 评级数据获取(影子准入) | `frozen` | Public Calls soft launch | — | — |
| A | 呈现层信任资产 | `frozen` | Stage 0 + 评级启用决策(needs_decision)+ methodology P0 修复确认 | — | — |
| B | cert 解析 + 回填 + 重复 cert 检测 | `frozen` | Stage A | — | — |
| C | PSA 内部跨档阶梯校验 | `frozen` | Stage B + census ≥50 | — | — |
| D | pop report 接入 + 阶梯先验量化 | `frozen` | Stage C + pop 数据源选型(needs_decision) | — | — |

两个 `needs_decision` 留给 Ivan:(1) 评级数据从影子到启用的放行;(2) Stage D pop report 数据源选型。Claude Code 不得自行推进。

## 6. 全局 stop conditions

命中任一,停止 loop 并报告:
- 任何改动威胁 P0 不变量(Pokemon 日常 ingest / scheduler_run_log / Discord alerts)
- 评级数据绕过影子准入直接进入 `price_history` 的任何路径出现
- 回填脚本单批错误率 >5%
- 阶梯校验导致 BREAKOUT/MOVE 信号分布漂移 >20%(改动前后各跑分布 SQL 对比)
- 发现需要新外部数据源或新付费 API → 停,转 needs_decision

## 7. 缺口登记(执行中发现的新任务,只登记不执行)

- eBay Marketplace Insights API 官方申请(可并行提交,审批周期不可控,非阻塞)
- PSA cert verification API 对接(Stage B 之后评估)
- BGS/CGC 跨公司档位映射(远期,等 PSA 内部阶梯验证有效后)
- methodology page 增补"裁决层"章节(Stage C 完成后)

## 8. 教训记录

- **v1 失败原因:** spec 假设 `psa_10` 数据存在,未先跑数据 census——违反 NULL census 原则与 "claimed vs shipped"。规则化:**任何 loop spec 的 §1 第一个 stage 前,必须先列出数据前提及其生产证据;无证据的前提一律变成 Stage 0。**

---

*与 CLAUDE.md 冲突时以 CLAUDE.md 为准;本文件不得修改 CLAUDE.md §2 不变量。*
