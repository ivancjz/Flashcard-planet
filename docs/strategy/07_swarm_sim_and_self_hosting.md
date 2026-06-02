# Future Plan — 群体行为模拟 (Swarm Sim) + 自托管 (Self-Hosting)

> 状态：**未来计划，现在不执行。** 仅存文档为 spec。
> 概念来源：MiroFish（群体智能模型）。**只有概念，无实现框架。**
> 创建：本轮 Claude.ai 策略讨论产出。执行交由 Claude Code，给 Codex CLI review。

---

## 1. 触发条件（两个独立子计划，各有解锁条件）

### 子计划 A — Swarm Sim
全部满足才解锁：
- Pokémon Public Calls 软启动完成（post-June 14, 2026）
- 资金到位，可购入 Mac mini
- 笔记本 5090 (16GB) 到手

### 子计划 B — 生产自托管（已决定，现在执行）
- 决定：**生产服务跑在家用机器上，接受断电导致的不定 downtime。**
- 当前阶段判断：墨尔本更换升级断电约 1–2 次/年（2024-02、2024-09 为真实案例），
  可用性约 99.86%。pre-revenue / 早期用户阶段，此风险可接受。

---

## 2. 子计划 B（生产自托管）细节（因为已决定）

### 决定与原因
- 生产跑在家用机器，不续 Railway、不走乙方、换掉的代托费 + 预算转向 Mac mini。
- 这是一个**算近的赌**，不是默认、次数少（1–2/年）、伤害可控。

### 必须的零/低成本对冲（防止"资不抵债前意外垮掉"）：
- [ ] **Postgres 崩溃自动恢复**：硬断电后能自动完成 crash recovery，无需手动。
- [ ] **服务开机自启**：接电后机器自动重起全部生产服务（web / API / scheduler），
      无 Ivan 在场。**这是关键**——否则"几小时断电会害"断电来了服务没起"更麻烦"。
- [ ] （可选，未要求）UPS：只对**短时跳闸**有效（刹车级，更多断电频繁）；
      更换升级断电不在位，已接受该风险。买不买随缘。
- [ ] （可选）断电告警推送机：让 Ivan 至少**立即知道**（可决定是否手动处理）。

### 重新评估触发条件（别让"算就行了始"成为永久默认）：
满足**任一**则重新评估"生产是否该上 / 换有 SLA 的方案"：
- Pro 用户付费转化起来（与 TASK-301 Pro tier launch 挂钩）
- 出现**第一次** downtime 的真实走/流失了用户
- ARR ≥ 某个线（建议与现有 Max tier 的 ARR ≥ $5K 门槛对齐或自定）

### 两亿时的正解（届时参考，非现在执行）
- 若重新评估定完要上，**换成流云数据中心再说**，不是本机更硬件方案。
- 参考（2026 现状）：
  - **Render** — 最接近 Railway 工作流，有 Background Worker（跑 APScheduler 常驻进程）
    + cron + 托管 Postgres，**有月费除计费，无 usage-credit 耗尽即关机制**（解决 Railway 痛点），
    AWS 底座、帮不出层约 $21–52/月。迁移忙机成本最低。
  - **Fly.io** — 更酷、更可控（Firecracker microVM），但"更多控制 = 更多责任"。
    运维负担加倍，2026 起高快速计费、电信用卡、无新用户免费层。作为 B 计划。
- 迁移当忙来：托管 Postgres 是否支持 **PG 18**（托管 PG 大版本常滞后）。

---

## 3. 子计划 A（Swarm Sim）核心设计

### 3.1 概念（借鉴 MiroFish）与红线（MiroFish 的前车之鉴）
- **核**：市场即群体行为，模拟一组 agent 在 shock 下重新配置，浮现 dispersion /
  breakout / liquidity 位移。输出是 **scenario / mechanism**，不是"价格会到 $X"的 oracle。
- **与 Driver Attribution 关联**：模拟过程本身就是因果链 — 直接生成 attribution。
  不是新功能，是 Driver Attribution 的一个可信扩展。
- **红线（MiroFish 没做，我们必须做）**：
  - MiroFish **没有 validation**。它的 demo（红楼梦失传统屡、老爹推演陈）都**无法证伪**——
    答案不存在或者在滚的。它做的是"算 + 可交互感叹"，不是"预测力"。
  - 我们做的是"流向力"（TCG 投资者从 $30/月要能赚到钱的信号）。
    **validation 必须死在最前面**，否则信号"没趣但流不着"（第一个投资的 call 就秒
    founder-led 可信度，= 唯一护河）。

### 3.2 NO「主动推市场」——信息屏障（护城，前提，原头部）
模拟/信号产品天然有自我实现性，市场→信号→用户→市场。定位安全，否则总算 pump-and-dump 形状。
污染自己的 Driver Attribution。守护 legible 护城河：
1. **只推信息**：价格永远由用户自己决定。不替用户下单。不替用户定价。
2. **运营方/早期用户不在被 call 的牌子上买**（front-running / 利益冲突）。
3. **环境对称质量把关**（call 命中率 / 用户对称质量），**不问"我们对市场的影响"**。
   一旦优化那个，就会有意识地控量、选时、搅动、对"好的信号"。
4. **同步散布**：信息让整个 cohort **同时**拿到，无"早 5 分钟"分级。
   Public Calls = Pokemon-only locked cohort，天然帮做同步性。
- 市场影响是**要监控和避免的变量**，不是去设计的功能。
  最多**防御性**观测（监测自身信息是否产生市场足迹），不赌点。

### 3.3 Validation（我们有 MiroFish 没有的东西：可对账的历史真值）
- **Walk-forward backtest**：让 agent 群体看过"事件发生前的市场状态"，
  预测群体位移，跟事后**真实发的** dispersion/breakout/liquidity 对账，在 N 个历史事件目录中算。
- **这过路是考验资格才过去的场景，有过一些暗算了的历史不管来好多亮，砸。**
- **Point-in-time 数据纪律，防 look-ahead 泄漏 ——backtest 第一要义**：
  - 给每个模拟的信息：**严格只含"预测时间点之前"存在的数据**。
  - 事件之后的真实位移**只用于对账**，绝不进入模拟输入。
  - 数据层就要能"回到某时间点"只放那么前的状态——
    `price_history` + `captured_at` 天然支持该时间轴，好消息。
  - ⚠️ 注意：MiroFish 的 demo 设定天然无时间轴，所以它**从没处理过数据泄漏**。
    我们上 TCG 历史处理就立即面对它，比 MiroFish 严，但也因此更可信。

### 3.4 两段式架构（解决 16GB 物理限制 vs validation 需求的冲突）
**Tier 1 — 快速可校对层（validation 的通道）**
- agent 类型：flipper / 长期 / 奸细 / meta 追随者，用**确定性行为规则**（参数化反应函数），
  **不是每 tick 一次 LLM 调用**。
- 跑一次历史处 **极快** — 能做到 walk-forward backtest、调参、目录中算。
- LLM 只做一件事：给已算出的群体位移生成**解释文本**（与 Driver Attribution），少量调用。

**Tier 2 — 全-LLM-agent 可模拟层（未来用，受 Tier 1 约束）**
- MiroFish 那种"无限记忆 agent 自由交互"的版本。**完整保留，无点没用。**
- 继承 Tier 1 已校对的参数作为行为先验，但用于复盘 Tier 1 覆盖不到的**无标历史单例**场景。
- **不单独进生产路径**：输出必须在同等场景下对齐于 Tier 1（等量场景，Tier 1 已被历史验证），
  对不上 = Tier 2 在草稿。**Tier 1 是 Tier 2 的 validation 锚点。**

> 另外，全-agent simulation 在 Tier 2 完整保留，但 validation 不依赖那个获取快、流不着的
> Tier 2，而是跑在快速的 Tier 1 上，再用 Tier 1 约束 Tier 2。物理现实与验证需求互别求制。
> "全-agent 这边可以限制"的正解 = 不是数量，而是限制它只在哪一层承担验证责任。

### 3.5 硬件配置（Mac mini 的角色，仓库，不是引擎）
- **笔记本 5090 (16GB GDDR7, CUDA)**：跑 Tier 1（极快）+ Tier 2 当前活跃批次的 LLM 推理。
  - 16GB 物理账：模型需量（7-8B 4-bit → 5-6GB）+ 约 10GB 给 KV-cache。
  - "全 agent 同时"**卡上卡** — 必须**分批轮转**，每次约 64 个 agent 活跃持进换放内存，
    跑定状态能跑到 Mac mini，换下一批。一轮 = 批数 × 每批时间（Tier 2 现实为多级）。
- **Mac mini**：**agent 状态仓库**（存储活跃 agent 记忆）+ 常驻前端 / API / 调度 / 结果存储。
  - ⛔ **不作推理引擎**：Mac (Metal/MLX, 无 CUDA) LLM 吞吐远低于 5090，
    让 Tier 2 在 Mac 上跑 = 从来都该让那两台作业。Mac 的优势是**内存容量/常驻**，不是速度。
  - 两台机器：5090 出**速度**，Mac mini 出**容量 + 常驻性**。网络通信（本地局域网）。
    （注：无法跨机/跨时统一并放内存——永远是两台独立机器。）

### 3.6 Anti-tasks（与 DATAGEN / LangChain 全级别禁止）
- ❌ **抄本 MiroFish 全栈**（GraphRAG + Zep Cloud，外部记忆库，踩 external-SaaS 红线）
  + CAMEL-AI/OASIS 全-LLM-agent 框架。原因：external SaaS、无 validation、token 预算是
  被投资者问的升级，MiroFish 官方都建议"别跑 <40 轮"（大时耗太大）。
- ❌ **Tier 2 独立进生产**（未经 Tier 1 约束验证）。
- ❌ **跳过 Layer 0 / point-in-time 直接含未来数据**（look-ahead 泄漏 = 赢 validation，比没 validation 更危险）。
- ❌ **生产与模拟跑在同一台机器**（模拟跑满 5090 时不生产挤内存/散热 = 数个特定时段）。
  ✅ 模拟在本地机器，生产是 §2 的独立部署。

### 3.7 给 Claude Code 的暂停条件
- Layer 0（历史校对数据集；事件–cohort–实际位移对账表，point-in-time）未完成 — 不进 Tier 1。
- Tier 1 walk-forward backtest 未越过开放 — 不向来接近 Driver Attribution 生产路径。
- Tier 2 未对齐 Tier 1（同等场景）— 不向输出走任何 user-facing 路径。
- 不引入外部 ABM/agent 框架或外部记忆库；限在现有 Python 无框架手写 agent loop。
- 设硬性 LLM token / 计算预算上限 + kill switch。

---

## 4. 一句话总结
> 借 MiroFish 的**概念**（群体模拟生成 scenario + driver），补上它**没有的** validation
> （walk-forward 历史处理 + point-in-time 数据纪律），两段式（Tier 1 可校对快验证 /
> Tier 2 全-agent 复杂由约束）解决 16GB 物理限制（5090 出速度、Mac mini 出容量与常驻），
> 生产自托管在家、接受其断断电、设自动恢复、设重评触发条件。
> **全部 Phase 9+ / Public Calls 软启动后执行，现在只存 spec。**
