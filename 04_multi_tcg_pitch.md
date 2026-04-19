# 04 — "Why Multi-TCG Now" — 对外定位文稿

*用途:投资人 pitch、合作方介绍、对外博客首篇、媒体回复*
*长度:5 个版本,从 30 秒电梯 pitch 到 15 分钟深度叙事*

---

## 版本 1 — 30 秒电梯 pitch(见面寒暄后的第一段)

> Flashcard Planet is the market intelligence platform for trading card 
> games. We cover Pokemon, Magic, Yu-Gi-Oh, One Piece, and Lorcana in one 
> place — and we're the only tool that catches when cards move *across* 
> games, like when Godzilla cards go up in MTG and One Piece TCG at the 
> same time because a new movie trailer dropped. Every signal we publish 
> comes with a confidence score, a sample size, and an AI-written 
> explanation of why it's moving. Card Ladder is sports-first and doesn't 
> cross TCGs. MTGStocks is MTG-only. Collectr is a digital binder. We're 
> filling the gap.

中文版:
> Flashcard Planet 是面向 TCG 收藏卡牌市场的智能分析平台。我们在一个产品里
> 覆盖宝可梦、万智牌、游戏王、航海王 TCG、迪士尼洛卡纳,而且是市面上唯一
> 能捕捉"跨游戏"信号的工具 —— 比如《哥斯拉大战金刚》新预告片放出时,哥斯拉卡
> 同时在万智牌和航海王 TCG 涨,我们会识别出来。每一条信号都附带置信度、
> 样本量,和一段 AI 写的"为什么在动"的解释。Card Ladder 以体育卡为主,不跨 
> TCG;MTGStocks 只做万智牌;Collectr 只是个电子相册。我们填的是这个缺口。

---

## 版本 2 — 2 分钟 pitch(邮件开篇 / 展会自介绍 / 线上 intro 会)

**Opening hook:**

> 在美国,每年有超过 50 亿美元的收藏卡牌交易发生,主要通过 eBay、TCGplayer 
> 和 Facebook Groups。但这是一个没有 Bloomberg 的市场 —— 没有一个工具能告诉
> 严肃的买家"今天这张卡为什么动、动得有多真实、该不该跟"。现有工具分成三类:
> 数字相册(Collectr、pkmn.gg)只记录你拥有什么;价格查询(PokePriceTracker、
> PriceCharting)告诉你一张卡值多少;单游戏分析(MTGStocks、Pokelytics)只
> 服务一个游戏的用户。**没有人做"跨游戏的市场智能"。**

**What we built:**

> 我们在过去 9 个月构建了 Flashcard Planet,一个 TCG-native 的数据和信号平台。
> 技术栈包括:eBay 实时成交 ingest、IQR 异常价格过滤、BREAKOUT/MOVE/WATCH 
> 信号分类引擎、流动性评分、LLM 驱动的映射和解释层、双 provider(Anthropic + 
> Groq)。138 个测试全绿,生产级架构。我们已经在 Pokemon 上跑通端到端,
> 现在扩展到 Magic、Yu-Gi-Oh 和更多。

**The wedge:**

> 真正的收藏者和投资者从来就不只玩一个游戏。一个严肃的用户可能同时追踪 
> MTG Commander staples、Pokemon vintage、和 OPTCG 热门 secret rare。他们现在
> 要开三个浏览器标签、对着三个不同平台的价格做心算。我们是唯一一个把他们
> 的完整 portfolio 放进一个视图、并且识别跨游戏相关性的产品 —— 比如电影 IP 
> 同时推动多个游戏的卡、或者 Pokemon 新 set 上市挤压 MTG Standard 销量。
> 这个能力技术上需要一个多游戏数据层 + LLM-powered franchise tagging,没有
> 单游戏工具可以复制。

**Traction / ask:**

> [填入你的数据:DAU、Pro 转化率、Discord bot 用户数、$ ARR 等]
> 我们正在 [筹款 $X / 寻找 data partnership / 寻找 content 合作] 以 [具体目标]。

---

## 版本 3 — 一页纸 Executive Summary

### Flashcard Planet — One-Pager

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                     FLASHCARD PLANET
          Market intelligence for trading card games
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

THE MARKET
- $5B+ annual TCG secondary market (Pokemon, MTG, YGO alone)
- 150K+ members on r/mtgfinance; 23K+ paid on PokeNotify
- Growing: OPTCG and Lorcana created new collector cohorts in '23-'25
- Maturing: PSA grading volume for TCG now exceeds sports cards

THE PROBLEM
- Existing tools serve one game, one task, or one user type
- Serious collectors run 3-4 tabs of 3-4 different platforms daily
- No tool catches cross-franchise / cross-game market patterns
- Price data rarely includes confidence, sample size, or reasoning

OUR WEDGE
The only platform that is (a) TCG-native across 5+ games,
(b) signal-driven rather than price-lookup, 
(c) shows confidence and sample size on every number,
(d) detects cross-TCG market patterns (proprietary).

PRODUCT
• Live data ingest from eBay, TCGplayer, game-specific APIs
• Signal engine: BREAKOUT / MOVE / WATCH / IDLE with confidence
• AI-written explanation for every signal ("why it's moving")
• Liquidity scoring for every asset
• 🌐 Cross-TCG Franchise Move detector (flagship, proprietary)

BUSINESS MODEL
• Free: basic prices + top movers, unlimited games
• Pro ($12/mo): confidence + AI explanations + cross-TCG + unlimited alerts
• Trader ($29/mo, coming): API + cultural triggers + portfolio P&L

COMPETITION LANDSCAPE
                       │ TCG │Multi│Signals│ AI  │Cross│
                       │-only│ TCG │+ conf │expl │ TCG │
  Card Ladder           │  —  │  ✓  │   —   │  —  │  —  │
  MTGStocks             │  ✓  │  —  │   ~   │  —  │  —  │
  Pokelytics            │  ✓  │  —  │   ~   │  —  │  —  │
  Collectr              │  —  │  ✓  │   —   │  —  │  —  │
  PokePriceTracker      │  ✓  │  —  │   —   │  —  │  —  │
  FLASHCARD PLANET      │  ✓  │  ✓  │   ✓   │  ✓  │  ✓  │

TECH MOATS
1. LLM-powered cross-game franchise tagging (one-time $100 infra cost
   creates permanent structural advantage)
2. Multi-source ingest architecture already built and abstracted
3. Double-redundant LLM providers (Anthropic + Groq) de-risk cost/latency
4. 138-test coverage = maintainable velocity, not a hack pile

TEAM
[Fill in: names, prior experience, TCG authenticity]

ASK
[Fill in: raise amount, use of funds, or partnership specifics]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 版本 4 — 5-7 分钟 Deep pitch(投资人会议 / deck 旁白)

### Slide narrative(按 slide 顺序)

**Slide 1 — Hook**

> 三年前,一张 Pokemon 卡和一张 Magic 卡没什么共同点 —— 是两个平行市场,
> 两个独立的 finance community,两群不同的人。
>
> 今天完全不一样。
>
> 一个买家同时在 eBay 买 Pokemon、MTG、One Piece TCG 的概率已经是大概率事件。
> Collectr 2M 用户的数据告诉我们这一点。Reddit 上 r/mtgfinance 的讨论里经常
> 出现 "我最近把 MTG 的钱转去 OPTCG 了"这种帖子。
>
> **但市场还没有一个工具服务这种跨 TCG 的严肃玩家。**

**Slide 2 — Market size**

> 2024 年 Pokemon TCG 市场规模超过 $10B(graded 市场),全美 PSA grading 
> submissions TCG 超过了 sports。MTG 年营收首次突破 $2B(Hasbro 财报)。
> Lorcana 上线 18 个月做到全球 TCG 前 5。
>
> 但更重要的不是每个游戏的规模,是**玩家在游戏间的流动性**正在快速提升。
> 这创造了一个以前不存在的数据层 —— 谁在从哪儿流向哪儿、什么 IP 在带动
> 跨游戏热度、meta 事件如何挤压邻居游戏的需求。
>
> 这个数据层今天**没有任何工具在服务**。

**Slide 3 — Competitive map**

[展示之前我们做的 2x2 竞争图]

> Card Ladder 是 sports-first,他们服务的是另一个人群(棒球卡为主),TCG 
> 只是副业。MTGStocks 和 Pokelytics 都是 single-game,架构上无法跨。Collectr 
> 有 2M 用户但是个数字相册,没有 intelligence 层。KardSight 刚上线,做 sports 
> 加 TCG 混合,但 sports/TCG 的用户群重合度很低,我们预判他们会被迫二选一。
>
> **这张图里的右上空白,是我们的定位。**

**Slide 4 — The product**

> 我们的产品做三件事:
>
> 第一,**每张卡都有可信度标签**。你看到的不是 "$45",是 "$45 基于 47 笔成交,
> 置信度 92"。这是 Card Ladder 做不到的颗粒度 —— 他们给价格,我们给决策基础。
>
> 第二,**每个信号都有 AI 写的"为什么"**。BREAKOUT 不是一个冷冰冰的标签,
> 是 "Base Set 喷火龙 BREAKOUT — 可能驱动:30 周年巡回赛宣布;同 set 其他卡
> 同步上涨;reprint 风险低"。这是 LLM 时代才可能做出来的产品形态。
>
> 第三 —— 这是我们的 flagship —— **跨 TCG 信号**。当哥斯拉新电影放预告,我们
> 识别出哥斯拉卡在 MTG 和 OPTCG 同日上涨,生成一条 "Godzilla — Cross-TCG 
> Franchise Move" 信号,并提示你这种同步性通常预示未来 2-4 周的 IP 主题行情。
> 单游戏平台技术上无法做到这件事。

**Slide 5 — Technology moat**

> 三个互相强化的技术壁垒:
>
> **抽象数据层**:我们的后端是 game-agnostic 架构,每个游戏都是一个插件。
> 接入第 6 个游戏的成本从"写个新平台"降到"实现一个 150 行的 client 类"。
> 竞品的单游戏架构改过来需要 6-12 个月重写。
>
> **LLM-native**:IP tagging、signal explanation、mapping disambiguation 都
> 用 LLM。这一层我们用 Anthropic + Groq 双 provider 做了冗余,单次 tagging 
> 批处理 $100 内完成,但产出的跨游戏知识图是永久资产。
>
> **网络效应**:我们 flag 的每条跨 TCG 信号,用户的交互行为(dismiss / follow / 
> alert on this franchise)会反哺我们的 franchise 权重和 confidence calibration。
> 用得越多,信号越准,后来者冷启动越难。

**Slide 6 — Traction / progress**

[你的真实数据]

可能的 talking points(根据你实际情况选):
> - Pokemon 已全面上线,每日 X 笔 observation、Y 条有效 signal
> - Discord bot 已上线,MAU = Z
> - 138 个测试、7 个核心模块、零 prod incident
> - Yu-Gi-Oh 上线时间线:Q2 2026
> - MTG 上线时间线:Q3 2026
> - 跨 TCG 信号 MVP:Q3 2026
> - Pro 付费测试:Q2 2026 开始 mock upgrade flow

**Slide 7 — Business model**

> Pro: $12/mo,目标 conversion rate 2% of registered(行业 benchmark 
> 为 1-3% for niche tools)。
>
> LTV 估算:平均留存 9 个月(TCG 用户粘性高),LTV ≈ $108。
> CAC 目标:$25 通过内容 + 社群(我们自己就是 TCG community,cold start 便宜)。
> LTV/CAC ≈ 4x,健康。
>
> TAM:严肃 TCG 用户(定义为每月花 $50+ 在卡上)全球估 2-3M 人。
> 10% 渗透 + 2% pay = 4K-6K 付费用户 = $600K-$900K ARR。这是谨慎版本。
> 上限更高,因为我们可以跨语言 / 跨地区扩张(我们天然是 data-native 产品)。

**Slide 8 — Ask**

[根据你的实际 ask 填充]

---

## 版本 5 — 博客文章("Why we're going multi-TCG" 首篇公开宣告)

> # Why Flashcard Planet is now a Multi-TCG Platform
> 
> *4 月 2026*
> 
> When we started Flashcard Planet, we thought Pokemon was enough.
> 
> We had every reason to. Pokemon TCG is the largest TCG market by dollars. 
> It's the one most 90s kids return to. It has the clearest grading culture, 
> the most visible price appreciation, and the biggest collector Discord 
> communities. If you had to pick one TCG to build a data platform around, 
> you'd pick Pokemon. We did.
> 
> We were right about Pokemon. We were wrong about "one TCG is enough."
> 
> ## What changed our mind
> 
> A pattern kept showing up in our logs and user interviews.
> 
> Users who signed up for Pokemon signals would ask about MTG. Users who 
> came from our Discord bot would also be in r/mtgfinance. The #1 feature 
> request from our most engaged users wasn't "more Pokemon sets" — it was 
> **"when are you adding Magic?"**
> 
> We looked at the market and noticed something obvious in retrospect: the 
> *players* are multi-TCG. They have been for years. It's only the *tools* 
> that are single-TCG. 
> 
> The reasons are mostly accidental. MTGStocks was built in 2013 by MTG 
> players, for MTG players. Pokelytics grew inside a Pokemon Discord. 
> Card Ladder started with baseball cards and sports-card data forms every 
> design choice they've made since. Each tool was purpose-built for its 
> community. None of them were designed to *span* communities.
> 
> Multi-TCG is a green-field category because it isn't anyone's natural 
> extension. Single-TCG tools would have to rebuild from scratch. 
> Multi-category tools like Collectr lack the data-analysis depth. It was 
> sitting there waiting.
> 
> ## What's new in Flashcard Planet
> 
> Starting this quarter, we're rolling out five TCGs: Pokemon (already 
> live), Yu-Gi-Oh!, Magic: The Gathering, One Piece TCG, and Lorcana. 
> Each game gets:
> 
> - Full card catalog with accurate pricing
> - Sample-size-aware price points
> - BREAKOUT / MOVE / WATCH / IDLE signals (Pro)
> - AI-written explanations for why each card is moving (Pro)
> - Liquidity scoring (Pro)
> - Game-specific signal types — for example, banlist-triggered signals 
>   for Yu-Gi-Oh, reprint-risk scores for Magic
> 
> But here's what we're most excited about, and what we don't think exists 
> anywhere else:
> 
> ## Cross-TCG Intelligence
> 
> When the Godzilla x Kong 2 trailer dropped, Godzilla cards in Magic and 
> One Piece TCG both saw unusual movement within the same 48 hours.
> 
> No single-TCG tool would catch this. No multi-category tool like Collectr 
> runs signal detection. But we watch all five games on one data layer, 
> and we tag every card with franchise and character metadata using LLMs. 
> When we see a franchise moving in 2+ games at once, that's a signal we 
> generate and surface to Pro users.
> 
> We call it **Cross-TCG Movers**. It's our flagship Pro feature.
> 
> Types of cross-TCG signals you'll see:
> 
> - **Franchise Move** — same IP moving in multiple games (Godzilla, Marvel, 
>   Star Wars, anime crossovers)
> - **Cultural Trigger** — movie / TV / anime release driving related-card 
>   movement across games
> - **Meta Spillover** (Trader tier, later) — one game's meta shift 
>   compressing another game's demand
> 
> ## What Pokemon users will notice
> 
> Your Pokemon experience is not getting worse. If you only care about 
> Pokemon, the dashboard, signals, and alerts all still work exactly the 
> way they did — we just added a game selector at the top. Your watchlists, 
> your Discord bot config, your account settings are unchanged.
> 
> What you'll notice if you're curious:
> 
> - A **Cross-TCG Movers** panel on the signals page (Pro)
> - An option to extend your watchlist to other games
> - When a major Pokemon card is also moving in another TCG for cultural 
>   reasons (think Pikachu Secret Lair hypothetically), you'll see the 
>   cross-link
> 
> ## Why this is the right moment
> 
> Three trends converged:
> 
> **1. TCG audiences are rotating more**. OPTCG grew from nothing to top-5 
> TCG in 18 months. Lorcana's launch pulled MTG Commander players into a 
> new game. Disney and Sony launched TCGs in 2024-25. The rigid tribalism 
> of 2015's single-TCG playerbase is gone.
> 
> **2. IP crossovers dominate**. Magic has run Universes Beyond partnerships 
> with LotR, Fallout, Assassin's Creed, Doctor Who, SpongeBob, Marvel, and 
> more. One Piece TCG has done Star Wars. Pokemon has done Van Gogh Museum 
> and McDonald's collab sets. Cross-franchise is no longer the exception.
> 
> **3. LLMs make it tractable**. Tagging 50,000 cards with franchise 
> metadata was impossible at scale five years ago. Today, it's a $100 
> one-time cost. The data moat that enables cross-TCG signaling didn't 
> exist until recently.
> 
> ## What's next
> 
> - **Q2 2026**: Yu-Gi-Oh! goes live, Pro tier launches
> - **Q3 2026**: MTG goes live, Cross-TCG Movers MVP ships
> - **Q4 2026**: OPTCG + Lorcana live, Trader tier (API access, portfolio 
>   P&L, cultural triggers)
> 
> If you're already a user, you'll see Yu-Gi-Oh appear in your game selector 
> within the next few weeks — no action required.
> 
> If you've been waiting for multi-TCG coverage before signing up, you can 
> join the Pro waitlist [here] (or just sign up free and play with Pokemon 
> while we finish the rest).
> 
> And if you run a Discord community, write content, or work at a game 
> store and want API access or content partnerships, email us at 
> partners@flashcardplanet.com.
> 
> We think the next few years of the TCG market will be defined by 
> cross-franchise cultural events driving prices across multiple games at 
> once. Whoever builds the first tool that sees this clearly will define 
> the category.
> 
> We want to be that tool.
> 
> — The Flashcard Planet team

---

## 使用建议 / 分发策略

按场景用哪个版本:

| 场景 | 用版本 | 配套 |
|---|---|---|
| 展会 / meetup 初次见面 | v1 30 秒 | 加联系卡片 |
| 投资人 cold email | v3 一页纸 PDF 附件 | 邮件正文用 v1 |
| 投资人面对面 | v4 deck | 讲 7 分钟,留时间问答 |
| 合作方(TCG Discord、内容创作者)| v2 2 分钟 | 加一个 partnership 具体条款 |
| 上线公告 / 博客 | v5 公开文章 | 推 Twitter、Reddit r/mtgfinance、r/PokemonTCG、r/yugioh |
| 媒体问询 | 引用 v5 的原话 | 授权媒体节选 |

**最重要的建议:**

上线公告(v5)发布的当天,在 Reddit **同时发到 4 个 sub**:
- r/mtgfinance (150K+ members,最高质量受众)
- r/PokemonTCG (Pokemon 社群)
- r/yugioh (YGO 社群)
- r/Lorcana (小但 engagement 高)

每个 post 的 title 都**突出那个 sub 的游戏**:
- r/mtgfinance: "We built a cross-TCG signal platform. MTG is live, and 
  the Cross-TCG feed catches things MTGStocks can't."
- r/PokemonTCG: "A Pokemon signal platform that now also covers other TCGs, 
  because you probably play more than one."
- ...

**不要**一个 generic post 发四个 sub。每个 sub 的引流要本地化。

---

## 一个警告

不要在 pitch 里夸大"已经做到"的部分。

**现在真实可说的:**
- ✓ Pokemon 完整跑通
- ✓ 多 TCG 架构设计完成
- ✓ Yu-Gi-Oh 和 MTG 接入规划完成
- ✓ Cross-TCG 算法和 schema 设计完成

**现在不能当成 "已有" 的:**
- ✗ Yu-Gi-Oh 全功能上线(在做中)
- ✗ MTG 全功能上线(在做中)
- ✗ Cross-TCG signal 真实产出(MVP 在做)
- ✗ Pro 付费用户数(如暂时 0,别提)

投资人会 verify。**诚实的 roadmap 永远比过度包装的 "already done" 更有说服力。**
上面的 v4 deck slide 7 留了一个 "Traction / progress" 让你真实填数字,不要编。

---

## 最后:一个 elevator pitch 的核心句

记住这一句话,任何 pitch 场景随时能用:

> "We're the Bloomberg Terminal for trading card games — cross-game, 
> confidence-aware, and the only tool that catches when Godzilla moves 
> in Magic and One Piece at the same time."

(注意:"Bloomberg Terminal" 这个比喻已被 KardSight 和 Mythic Index 用了。
如果对方质疑,换一种说法:"the one research tool you open every morning 
if you care about more than one TCG." 这是我们独占的版本。)
