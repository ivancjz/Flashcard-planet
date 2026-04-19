# 03 — Pro Tier 定价页面文案

*可直接交给前端工程师实现,或粘贴到 Claude Code 让它生成页面*
*双语:英文为主(主要市场),中文备用*

---

## 定位总览

**关键原则:** 不卖 "更多数据",卖 "更好的决策"。
竞品(Collectr, PokePriceTracker)卖的是"更长的价格历史"。我们卖的是
"跨 TCG 的市场智能 + 你看到的每个数字都有置信度支撑"。

---

## 方案对比页面 —— 英文版(主要)

### Hero

```
Not another price tracker.
Market intelligence for every TCG you play.

Pokemon. Magic. Yu-Gi-Oh. One Piece. Lorcana.
One signal feed. Cross-game insights you won't find anywhere else.

[See plans]    [Watch 60-second demo]
```

### Plan Comparison

```
                              Free              Pro              Trader
                              $0                $12 / month       $29 / month
                                                (or $120 / year)  (or $290 / year)

                              [Sign up]         [Start 7-day trial] [Contact us]
                              Always free       Cancel anytime     For power users
```

### Feature comparison table

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  WHAT YOU SEE                         Free          Pro            Trader
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  GAMES COVERED
  Pokemon                               ✓             ✓               ✓
  Magic: The Gathering                  ✓             ✓               ✓
  Yu-Gi-Oh!                             ✓             ✓               ✓
  One Piece TCG                         ✓             ✓               ✓
  Lorcana                               ✓             ✓               ✓

  PRICE & CARD DATA
  Card browser & search                 ✓             ✓               ✓
  Current market price                  ✓             ✓               ✓
  Price history (30 days)               ✓             ✓               ✓
  Price history (full / 2+ years)       —             ✓               ✓
  Sample size on every price            —             ✓               ✓
  Data source breakdown (eBay vs TCGP)  —             ✓               ✓

  SIGNALS (this is why you're here)
  Daily top movers                      ✓             ✓               ✓
  Simple BREAKOUT / MOVE / WATCH tags   ✓             ✓               ✓
  Confidence score on every signal      —             ✓               ✓
  Liquidity score                       —             ✓               ✓
  AI-written explanation for each       —             ✓               ✓
    signal (why it's moving)
  Banlist-triggered signals (YGO)       —             ✓               ✓
  Reprint risk alerts (MTG)             —             ✓               ✓

  🌐 CROSS-TCG INTELLIGENCE (flagship, Pro-only)
  Cross-TCG movers feed                 —             ✓               ✓
  Franchise-level watchlists            —             ✓               ✓
    (e.g. track "Godzilla" across
     MTG + OPTCG at once)
  Cultural trigger alerts               —             —               ✓
    (movie / TV / anime launches
     that could move cards)
  Meta spillover signals                —             —               ✓

  WATCHLISTS & ALERTS
  Watchlist cards (total)               20            Unlimited       Unlimited
  Price alerts (active)                 5             Unlimited       Unlimited
  Alert channels                        Web           Web + Discord   Web + Discord
                                                                      + Email + SMS
  Custom alert conditions              Basic         Advanced        Advanced
                                                                      + webhook

  POWER-USER TOOLS
  Daily digest                          —             Email           Email + Discord
  CSV export                            —             ✓               ✓
  API access                            —             —               ✓
  Portfolio tracking                    Basic         Advanced        Advanced +
                                                                      realized/unrealized
  Historical backtest                   —             —               ✓

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 每个 Plan 的 "Why" 叙事

### Free —— "Get the lay of the land"

**For:** Collectors who want accurate card prices across every major TCG 
without paying for anything.

**What you get:** Card data for Pokemon, Magic, Yu-Gi-Oh, One Piece, and 
Lorcana. Current prices. Recent top movers. 30 days of history.

**What you don't:** Confidence scores. AI explanations of *why* a card is 
moving. The cross-TCG intelligence feed. Full history.

> *"Free is generous on purpose. We want you to see what we have before 
> we ask you to pay. If 'the card is $45' is what you need, stop here — 
> we'll never bug you to upgrade."*

---

### Pro — $12/month — "Know why, not just what"

**For:** Serious collectors and part-time flippers who want to understand 
*why* prices move, not just that they did.

**The three things Pro unlocks that matter most:**

**1. Every number has a confidence label.**  
You see a card valued at $45 on other platforms. Here, you see  
"$45 · based on 47 eBay sales in the last 7 days · mapping confidence 92."  
If the data is thin, we tell you. If the mapping is shaky, we tell you. 
You never have to guess whether to trust a number.

**2. Every signal comes with an AI-written reason.**  
Not just "Base Set Charizard +18% this week" — but "Base Set Charizard 
is showing a BREAKOUT. Likely driver: 30th-anniversary Pokemon TCG 
tournament announcement last Wednesday; similar cards in the set also 
moved. Reprint risk: low (WOTC-era, reserved from reprint)."

**3. Cross-TCG intelligence — the feature no other platform has.**  
When Godzilla x Kong releases a new trailer, Godzilla cards move in MTG 
*and* One Piece TCG at the same time. Card Ladder can't see that. 
MTGStocks can't see that. Pokelytics can't see that. We can — and we 
tell you the moment it happens.

**What you pay for:** The decision quality of 100 hours of eBay research 
per month, delivered in a 15-minute morning coffee read.

---

### Trader — $29/month — "For when this is part of your income"

**For:** Resellers, LGS owners, content creators, and portfolio-serious 
investors who make real money decisions weekly.

**Everything in Pro, plus:**

**API access.** Pull our data into your own spreadsheets, automations, or 
Discord bots. Rate-limited but usable (60 req/min).

**Cultural trigger alerts.** We watch for movie/TV/anime events that 
historically move related cards. Deadpool 3 dropped? You get a ping 
*before* the speculation wave.

**Meta spillover signals.** When a new Pokemon set releases and pulls 
attention (and wallet share) away from MTG Standard, we tell you. Inverse 
opportunities in the game losing attention.

**Portfolio tracking with realized/unrealized P&L.** Log purchase prices, 
track cost basis across games, see your true return — not just "current 
value."

**Historical backtest.** "What if I'd bought every BREAKOUT signal in 2025?" 
Run the numbers. See which signal types actually print money in your 
category.

**SMS alerts + webhook integration.** For when staring at a dashboard isn't 
your primary job.

---

## CTA & Trust Sections

### Below the plans table:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Why pay when other trackers are free?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Because the other trackers are showing you prices.
  We're showing you decisions.

  A price alone can be wrong. A price with "based on 47 sales, 
  confidence 92, liquidity 68" is actionable. That's what Pro is.
```

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Is Pro worth $12/month?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  A single correct BREAKOUT call on a $40 card returns your year.
  One avoided purchase of an overpriced card pays for 3 months.
  
  But don't take our word for it. 7-day free trial, cancel with 
  two clicks.
```

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  What we're NOT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ✗  We are not a marketplace. We don't sell cards or earn from 
     your trades.
  
  ✗  We are not a grading service.
  
  ✗  We are not affiliated with Pokemon, Wizards of the Coast, 
     Konami, Bandai, or Disney.
  
  ✓  We are an independent market intelligence tool. Our job is 
     to help you see what's actually happening in the market — 
     cleanly, honestly, with our reasoning exposed.
```

---

## Common objections (FAQ section)

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Frequently asked
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Q: How is this different from Card Ladder?
A: Card Ladder is a sports-card-first platform with the deepest 
   historical sales database in the hobby. We respect that. We take 
   a different angle: we're TCG-native (no sports), we connect signals 
   across TCGs, and every number comes with a confidence label. If 
   you want 100M historical sales, use Card Ladder. If you want 
   "here's what's moving across your games and why," that's us.

Q: How is this different from MTGStocks / Pokelytics?
A: Those are single-game tools. The fact that you probably play 
   more than one TCG is the entire premise of Flashcard Planet. 
   If you only care about MTG, MTGStocks at $5/mo does its job. 
   If you track multiple games, switching between three tabs of 
   three different platforms is what we're replacing.

Q: Where does your price data come from?
A: Live eBay sales (not just listings — actual completed 
   transactions) for the ground truth, plus TCGplayer for market 
   floor reference, plus vendor-neutral aggregation. We filter 
   outliers with IQR and we tell you our sample size on every 
   number. Every data source is labeled on every card page.

Q: I saw your "Cross-TCG" feature — is that real or a gimmick?
A: It's real and it's our flagship. We use LLMs to tag every card 
   with franchise/character/theme metadata (Godzilla, Star Wars, 
   Marvel, etc). When 2+ games' cards of the same franchise move 
   together, we flag it. The math is simple; the data work is 
   what's new. You can browse the current Cross-TCG feed on any 
   Pro account and judge for yourself.

Q: Do you support Japanese / Korean cards?
A: Yes for Pokemon (limited Japanese coverage currently expanding) 
   and for any game where language impacts the price significantly. 
   Language is detected from eBay listings and tracked as a 
   separate dimension in our asset model.

Q: What if I stop paying — do I lose my data?
A: No. Your watchlists, alerts, notes, and portfolio history stay 
   in your account. You lose access to Pro features (confidence, 
   AI explanations, full history, cross-TCG feed). If you come 
   back, everything is where you left it.

Q: What's your refund policy?
A: Full refund within 14 days, no questions. Just email us.

Q: Do I need a Discord account to use this?
A: No. Discord is a nice-to-have for alerts but the full product 
   runs on the web / mobile web. Log in with email or Google.

Q: I run a card shop. Do you have a plan for us?
A: Yes — email us about Trader plan bulk licensing. We also offer 
   white-label embed of our signal feed for content creators.
```

---

## Upgrade CTA placements across the site

不要只在一个地方放升级入口,要在"痛点发生的瞬间"弹出。按位置和文案:

### 位置 1: Card Detail page — 价格图表

```
[Chart showing last 30 days]

  ╔════════════════════════════════════════════════╗
  ║                                                 ║
  ║    🔒  Unlock the full price history            ║
  ║                                                 ║
  ║    See 2+ years of movement, sample size,      ║
  ║    and source breakdown per data point.        ║
  ║                                                 ║
  ║    [Start 7-day trial]                         ║
  ║                                                 ║
  ╚════════════════════════════════════════════════╝
```

### 位置 2: Signals page — 免费列表底部

```
Showing 5 of 147 signals for today.

  ╔════════════════════════════════════════════════╗
  ║  142 more signals, with confidence scores and  ║
  ║  AI explanations. Plus the cross-TCG feed.     ║
  ║                                                 ║
  ║  [See all signals with Pro]                    ║
  ╚════════════════════════════════════════════════╝
```

### 位置 3: Watchlist — 超过 20 张

```
You've reached the free watchlist limit (20).
Pro removes the cap and lets you create themed lists 
(e.g. "Godzilla across all TCGs" or "Modern staples").

[Upgrade to Pro]     [Remove a card]
```

### 位置 4: Cross-TCG teaser(免费用户的首页)

```
  ╔════════════════════════════════════════════════╗
  ║  🌐 Cross-TCG Intelligence                      ║
  ║                                                 ║
  ║  Today 3 franchises are moving across 2+       ║
  ║  TCGs: ████████ ██████ ███████████             ║
  ║                                                 ║
  ║  The pattern is available to Pro members.      ║
  ║                                                 ║
  ║  [See what's moving]                           ║
  ╚════════════════════════════════════════════════╝
```

(故意模糊具体的 franchise 名字 —— 制造好奇心,但不给空着所以不虚)

### 位置 5: Alert limit 到达时

```
You've set 5 alerts. Free plan cap.
  
  Pro members get:
  • Unlimited alerts
  • Advanced conditions (e.g. "breakout with liquidity > 50")
  • Discord / Email / SMS delivery
  
  [Start 7-day trial]    [Edit an existing alert]
```

---

## 中文版(配合海外市场做中文版界面 / 中国收藏家市场)

### Hero(中文)

```
不只是价格追踪。
跨 TCG 的市场智能。

宝可梦 · 万智牌 · 游戏王 · 航海王 · 迪士尼洛卡纳
一个信号源,看到别家看不到的跨游戏规律。

[查看方案]    [60 秒演示]
```

### Plan 命名

| 英文 | 中文 |
|---|---|
| Free | 免费版 |
| Pro | 专业版 |
| Trader | 交易者版 |

### Pro 的核心 3 点(中文精简)

```
专业版解锁的三件事,别家给不了:

1. 每个数字都有可信度标签
   不是 "$45",而是 "$45 · 基于近 7 天 47 笔成交 · 映射置信度 92"。
   数据单薄我们会告诉你,映射存疑我们会告诉你,你不用猜。

2. 每个信号都有 AI 解释
   不是"涨了 18%",而是"Base Set 喷火龙 BREAKOUT。可能驱动:
   上周三宣布的 30 周年巡回赛;同 set 其他卡片也在同步上涨;
   重印风险:低(WOTC 时期卡,受保留名单保护)"。

3. 跨 TCG 智能 —— 市面上唯一
   《哥斯拉大战金刚》续集预告片放出,万智牌和航海王 TCG 的
   哥斯拉卡同时涨。Card Ladder 看不到。MTGStocks 看不到。
   我们看到,并在发生的那一刻告诉你。
```

### 定价(中文)

```
免费版       ¥0
专业版       ¥88 / 月 (或 ¥880 / 年,送 2 个月)
交易者版     ¥218 / 月 (或 ¥2180 / 年)

所有方案:7 天免费试用,随时取消。
```

**关于中文定价:** $12 USD ≈ ¥88 RMB (4 月汇率)。用整数定价符合
本地习惯。$29 USD ≈ ¥218,保持结构一致。

---

## 视觉设计要求(给前端 / 设计师)

1. **不要三列平排 plan table** —— Pro 要视觉强调(边框加色、"Most popular"
   标签)。Trader 放右侧,显得高端但不抢主视觉。

2. **Cross-TCG 这个 feature 要独立一个 hero section**,用视觉动画展示
   "一个 franchise 在 3 个游戏图标之间连线"。这是唯一一个别家没有的东西,
   要花重笔墨。

3. **所有 Pro feature 边上都放一个 "example" hover** —— 鼠标悬浮 5 秒出
   示例截图,让用户直接"看到"这个功能长啥样,而不是想象。

4. **FAQ 展开不要默认全开**,手风琴式。但 "Is Pro worth $12?" 和 
   "How is this different from Card Ladder?" 默认展开。

5. **移动端 plan table**:堆叠成 3 张 card,每张 card 内用粗体标出
   该 plan 独有的 top 3 feature,避免完整 table 在手机上不可读。

6. **配色**:Pro 的主色调不要用灰色(看起来像折扣),用品牌主色。
   Free 反而可以用灰色(中性)。

---

## 给 Claude Code 的前端实现任务

```
实现一个 /pricing 页面。需求:

1. Hero section:文案见上方
2. 三栏 plan comparison 见 feature table(desktop),移动端堆叠
3. 每个 plan 有 CTA(Free=注册,Pro=7 天试用,Trader=联系我们)
4. FAQ accordion
5. 所有文本使用国际化字符串(i18n key),中英文支持
6. Pro 栏目视觉强调(边框、badge)
7. 对接现有 user/auth 系统,Pro 升级 CTA 跳转到 TASK-006 里的 
   mock upgrade flow
8. 响应式:desktop 3 列,tablet 2 列(Pro 跨 2 列),mobile 单列
9. SEO meta tags:title、description、og:image(突出 cross-TCG)
10. 所有数字(价格、limit 值)从一个 config 文件读取,便于后续调整

文件位置:app/pages/pricing 或 src/routes/pricing
样式:遵循现有设计 token
交付:
  - 页面完整可用
  - 移动端/桌面端截图
  - 国际化 keys 完整,中英文填充
```

---

## A/B 测试建议

上线后一个月内建议测的变量:

| 测试项 | 变量 A | 变量 B | 预期影响 |
|---|---|---|---|
| Pro 定价 | $12/mo | $15/mo | 看 price sensitivity |
| Pro 标签位置 | Middle column | Right column | 转化率差异 |
| Trial 长度 | 7 天 | 14 天 | trial → paid 转化 |
| CTA 文案 | "Start trial" | "See Pro in action" | 点击率 |
| Hero 强调 | Cross-TCG 为主 | Confidence 为主 | 理解度 |

---

**最后一件事:** 不要在上线第一个月就开 Trader plan。
先把 Pro 做好,等有 100+ Pro 用户后再引入 Trader,那时候已经知道用户
真实想要的高阶功能是什么。当前文档里的 Trader feature 是"可能"的方向,
不是"已经建好"的。上线时 pricing 页面只需要 Free + Pro 两栏。
