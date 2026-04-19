# 02 — 跨 TCG 信号算法设计与数据库 Schema

*目的:完整的算法设计 + 可直接建表的 schema + 可直接实现的伪代码*
*配合 TASK-015 和 TASK-016 使用*

---

## 1. 核心概念

### 1.1 什么叫"跨 TCG 信号"

单 TCG 信号 = 某张卡在它自己的游戏里涨跌
**跨 TCG 信号 = 不同游戏里的、被某种共享驱动力串起来的、同步发生的价格变化**

这个功能是 Flashcard Planet 唯一一个技术上单 TCG 平台**根本做不出来**的东西。
Card Ladder 架构按 category 分割,MTGStocks 只有 MTG,Pokelytics 只有 Pokemon。
即使他们想做,数据结构就不支持。

### 1.2 三种跨 TCG 信号类型

| 类型 | 信号定义 | 最小触发条件 | 置信度基础 | MVP 优先级 |
|---|---|---|---|---|
| **Franchise Move** | 同 IP 的卡在 2+ 游戏内同时触发 MOVE/BREAKOUT | 7 天内 2+ 游戏,每个游戏 ≥1 张 MOVE+ signal | 子 signal 数、confidence 均值、是否同日 | **P0(MVP)** |
| **Cultural Trigger** | 电影/剧/动漫上映带动多游戏同期涨 | 外部事件 + 2+ 游戏卡符合该 IP 在事件后 7 天涨 | 事件可信度 × 跨游戏响应强度 | P1 |
| **Meta Spillover** | 一个游戏的 meta 变化挤压另一游戏需求 | 两游戏价量反向、且时间窗口重合 | 反相关强度 × sample size | P2(可能不做) |

---

## 2. 数据库 Schema

### 2.1 IP Tag 系统(TASK-015 对应)

```sql
-- 跨 TCG 信号的基础:IP / franchise / character 标签
CREATE TABLE ip_tag (
    id                  BIGSERIAL PRIMARY KEY,
    asset_id            BIGINT NOT NULL REFERENCES asset(id) ON DELETE CASCADE,
    tag_type            VARCHAR(20) NOT NULL,  -- FRANCHISE | CHARACTER | THEME | ARTIST
    tag_value           VARCHAR(100) NOT NULL,  -- "Godzilla", "Luffy", "anime", "Rebecca Guay"
    tag_value_normalized VARCHAR(100) NOT NULL, -- 小写、去空格,用于查询
    confidence          REAL NOT NULL,  -- 0.0 - 1.0
    source              VARCHAR(20) NOT NULL,  -- "llm" | "manual" | "rule"
    llm_model           VARCHAR(50),  -- "claude-haiku-4-5" etc,便于追溯
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    CONSTRAINT chk_confidence CHECK (confidence >= 0 AND confidence <= 1),
    CONSTRAINT chk_tag_type CHECK (tag_type IN ('FRANCHISE', 'CHARACTER', 'THEME', 'ARTIST'))
);

-- 查询:按 franchise 快速找到所有相关卡(跨 game)
CREATE INDEX idx_ip_tag_franchise_lookup 
    ON ip_tag (tag_type, tag_value_normalized, confidence) 
    WHERE tag_type = 'FRANCHISE' AND confidence > 0.7;

-- 查询:按 asset 快速找到其所有 tags
CREATE INDEX idx_ip_tag_asset ON ip_tag (asset_id);

-- 唯一约束:同一 asset 同一 tag_type + tag_value 不重复
CREATE UNIQUE INDEX idx_ip_tag_unique 
    ON ip_tag (asset_id, tag_type, tag_value_normalized);
```

**关于 `tag_value_normalized`:** 为避免 "Godzilla" / "godzilla" / "GODZILLA" 
被当成三个不同 tag,每次存储和查询都用 `lower().strip().replace(" ", "_")`。

### 2.2 Cross-TCG Signal 表

```sql
CREATE TABLE cross_tcg_signal (
    id                  BIGSERIAL PRIMARY KEY,
    signal_type         VARCHAR(30) NOT NULL,  -- FRANCHISE_MOVE | CULTURAL_TRIGGER | META_SPILLOVER
    
    -- 共享的 "what connects these" 描述
    anchor_tag_type     VARCHAR(20),   -- FRANCHISE / CHARACTER / THEME / NULL for meta_spillover
    anchor_tag_value    VARCHAR(100),  -- "Godzilla"
    
    -- 涉及的游戏
    games_json          JSONB NOT NULL,  -- ["mtg", "one_piece"]
    
    -- 涉及的子 signals(引用 signal 表)
    child_signal_ids    BIGINT[] NOT NULL,
    
    -- 统计
    total_cards         INT NOT NULL,  -- 涉及的卡片数
    confidence          REAL NOT NULL,  -- 0.0-100.0 (和单 signal 保持一致范围)
    
    -- AI 解释(合成)
    ai_explanation      TEXT,
    
    -- 外部触发(Cultural Trigger 类型)
    external_event_type VARCHAR(50),  -- "movie_release" | "tv_release" | "anime_season_start"
    external_event_ref  VARCHAR(200), -- "Deadpool & Wolverine (2024)"
    external_event_date DATE,
    
    -- 生命周期
    detected_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at          TIMESTAMPTZ,  -- 信号过期后自动 archive
    status              VARCHAR(20) NOT NULL DEFAULT 'active',  -- active | expired | archived | dismissed
    
    -- 人工审核
    reviewed_by         BIGINT REFERENCES user(id),
    reviewed_at         TIMESTAMPTZ,
    review_decision     VARCHAR(20),  -- accepted | dismissed | override
    review_note         TEXT,
    
    CONSTRAINT chk_confidence CHECK (confidence >= 0 AND confidence <= 100),
    CONSTRAINT chk_signal_type CHECK (signal_type IN 
        ('FRANCHISE_MOVE', 'CULTURAL_TRIGGER', 'META_SPILLOVER'))
);

CREATE INDEX idx_cross_signal_active 
    ON cross_tcg_signal (detected_at DESC) 
    WHERE status = 'active';

CREATE INDEX idx_cross_signal_by_franchise 
    ON cross_tcg_signal (anchor_tag_value, detected_at DESC);
```

### 2.3 外部事件数据源(CULTURAL_TRIGGER 用)

```sql
CREATE TABLE external_event (
    id              BIGSERIAL PRIMARY KEY,
    event_type      VARCHAR(50) NOT NULL,  -- movie_release | tv_series_return | anime_season_start | major_award
    title           VARCHAR(300) NOT NULL,
    
    -- 关联到哪些 franchise(多对多,一个电影可能覆盖多 franchise,
    -- 如 Marvel 电影可能涉及 "Marvel" + "X-Men" + "Deadpool")
    franchise_tags  TEXT[] NOT NULL,  -- ["Marvel", "Deadpool"]
    
    event_date      DATE NOT NULL,
    impact_window_days INT NOT NULL DEFAULT 14,  -- 事件后多少天内的关联价涨算 "triggered"
    
    source          VARCHAR(50),  -- "tmdb" | "manual" | "news_feed"
    source_url      VARCHAR(500),
    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_external_event_recent ON external_event (event_date DESC);
```

**MVP 阶段:这张表手工维护**,每月运营团队加 5-10 个重点事件
(主要电影上映、动漫新季、大型电视剧回归)。自动化留到 Phase 2。

---

## 3. 算法详细设计

### 3.1 IP Tagging(TASK-015 详细实现)

#### 3.1.1 Prompt 模板

```python
IP_TAGGING_SYSTEM_PROMPT = """
You are an expert in trading card games and pop culture franchises. 
Your job is to identify the franchise, character, theme, and artist 
associations of trading cards, so that we can find cross-franchise 
opportunities (e.g. a Godzilla card in MTG and a Godzilla card in OPTCG).

Rules:
1. FRANCHISE tags are BROAD parent franchises. Use canonical names.
   - "Pokemon" (not "Pokémon TCG")
   - "Magic" (for vanilla Magic cards; the franchise IS Magic)
   - "Yu-Gi-Oh"
   - "One Piece"
   - For crossovers: the *guest* franchise, e.g. a Godzilla card in MTG 
     gets FRANCHISE="Godzilla" AND FRANCHISE="Magic".
   - Real-world IPs: "Marvel", "Star Wars", "Lord of the Rings", 
     "Stranger Things", "Fortnite", "Godzilla", "MLP", "Dr. Who", 
     "Final Fantasy", "Street Fighter", "Arcane", "League of Legends"

2. CHARACTER tags are specific named characters from that franchise.
   Only if the card represents that character, not just mentions.
   - "Charizard" / "Pikachu" / "Mewtwo" (Pokemon)
   - "Luffy" / "Zoro" / "Ace" (One Piece)
   - "Godzilla" / "Mothra" (Godzilla)
   - "Deadpool" / "Wolverine" (Marvel)

3. THEME tags are aesthetic/genre categories, optional, only if strong.
   - "anime", "kaiju", "horror", "nostalgia_90s", "cyberpunk"

4. ARTIST tags only for cross-game artists with notable fan followings.
   - "Rebecca Guay", "Greg Staples", "John Avon" (cross MTG/D&D)
   - skip if unknown or non-notable

5. Return empty list if card is native-vanilla (a normal Pokemon Pokemon 
   card with no crossover, only needs the game's own FRANCHISE tag).

Output JSON only, no prose. Format:
[{"tag_type": "FRANCHISE", "tag_value": "Godzilla", "confidence": 0.98}, ...]
"""

IP_TAGGING_USER_PROMPT_TEMPLATE = """
Card:
- Name: {name}
- Game: {game_display_name}
- Set: {set_name}
- Rarity: {rarity}
- Card text (if available): {oracle_text_or_none}
- Artist: {artist_or_none}

Extract IP tags following the rules. Output JSON only.
"""
```

#### 3.1.2 实现骨架

```python
# app/services/ip_tagging/tagger.py

from dataclasses import dataclass
from typing import Optional
import json

from app.services.llm import anthropic_client  # 你现有的 LLM 抽象
from app.models import Asset, IpTag

@dataclass
class TaggingResult:
    asset_id: int
    tags: list[IpTag]
    cost_usd: float
    latency_ms: int

def normalize_tag_value(value: str) -> str:
    return value.lower().strip().replace(" ", "_").replace("-", "_")

# Franchise 白名单:只接受这些已知 franchise,避免 LLM 幻觉
KNOWN_FRANCHISES = {
    # TCG natives
    "pokemon", "magic", "yu_gi_oh", "one_piece", "lorcana", 
    "flesh_and_blood", "digimon", "weiss_schwarz",
    # Cross-IP
    "godzilla", "star_wars", "marvel", "dc", "lord_of_the_rings",
    "stranger_things", "fortnite", "final_fantasy", "street_fighter",
    "fallout", "dr_who", "arcane", "league_of_legends", "mlp",
    "jurassic_park", "transformers", "power_rangers", "assassins_creed",
    "walking_dead", "rick_and_morty", "dune", "attack_on_titan",
    # 可持续添加
}

def tag_asset(asset: Asset) -> TaggingResult:
    prompt_user = IP_TAGGING_USER_PROMPT_TEMPLATE.format(
        name=asset.name,
        game_display_name=GAME_CONFIG[asset.game].display_name,
        set_name=asset.set_name,
        rarity=asset.rarity or "unknown",
        oracle_text_or_none=asset.raw_payload.get("oracle_text") 
            if asset.raw_payload else "(none)",
        artist_or_none=asset.raw_payload.get("artist") 
            if asset.raw_payload else "(unknown)",
    )
    
    response = anthropic_client.messages.create(
        model="claude-haiku-4-5",  # 便宜优先,这是批处理
        max_tokens=500,
        system=IP_TAGGING_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt_user}],
    )
    
    raw = response.content[0].text.strip()
    
    # 容错解析
    try:
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
        tags_json = json.loads(raw)
    except (json.JSONDecodeError, IndexError):
        logger.warning(f"Failed to parse LLM response for asset {asset.id}: {raw}")
        return TaggingResult(asset_id=asset.id, tags=[], cost_usd=0, latency_ms=0)
    
    tags = []
    for item in tags_json:
        tag_type = item.get("tag_type")
        value = item.get("tag_value", "").strip()
        confidence = float(item.get("confidence", 0))
        
        if not value or tag_type not in ("FRANCHISE", "CHARACTER", "THEME", "ARTIST"):
            continue
        if confidence < 0.5:
            continue
        
        normalized = normalize_tag_value(value)
        
        # FRANCHISE 白名单过滤(防止 LLM 造词)
        if tag_type == "FRANCHISE" and normalized not in KNOWN_FRANCHISES:
            logger.info(f"Dropping unknown franchise: {value} (asset {asset.id})")
            continue
        
        tag = IpTag(
            asset_id=asset.id,
            tag_type=tag_type,
            tag_value=value,
            tag_value_normalized=normalized,
            confidence=confidence,
            source="llm",
            llm_model="claude-haiku-4-5",
        )
        tags.append(tag)
    
    # 批量 upsert(用 tag_value_normalized 去重)
    _upsert_tags(asset.id, tags)
    
    return TaggingResult(
        asset_id=asset.id,
        tags=tags,
        cost_usd=_estimate_cost(response),
        latency_ms=0,  # 简化
    )
```

#### 3.1.3 批处理任务

```python
# app/jobs/ip_tagging_batch.py

BATCH_SIZE = 50
MAX_CONCURRENCY = 5  # 防止撞 Anthropic rate limit

def tag_untagged_assets(game: Optional[Game] = None, max_assets: int = 1000):
    query = Asset.query.filter(
        ~Asset.id.in_(db.session.query(IpTag.asset_id).distinct())
    )
    if game:
        query = query.filter(Asset.game == game)
    
    assets = query.limit(max_assets).all()
    
    logger.info(f"Tagging {len(assets)} assets for game={game}")
    
    total_cost = 0
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as executor:
        for result in executor.map(tag_asset, assets):
            total_cost += result.cost_usd
    
    logger.info(f"Total cost: ${total_cost:.2f}")
```

**成本估算:**
- Pokemon 约 18k 卡
- YGO 约 13k 卡
- MTG 约 30k 卡(含所有印刷,可降到 18k 如果只做 oracle cards)
- 总计约 49k-61k 卡
- Claude Haiku 4.5: ~200-400 tokens out per card × ~300 input tokens
- 粗估 $0.001-0.003 per card
- **总成本: $50-180 一次性**

---

### 3.2 Franchise Move Detector(TASK-016 详细实现)

#### 3.2.1 核心算法

```python
# app/services/signal/cross_tcg/franchise_move.py

from dataclasses import dataclass
from collections import defaultdict
from datetime import datetime, timedelta

from app.models import Signal, IpTag, CrossTcgSignal, Game

@dataclass
class FranchiseBucket:
    franchise: str  # normalized tag value
    signals_by_game: dict[Game, list[Signal]]
    
    @property
    def games(self) -> set[Game]:
        return set(self.signals_by_game.keys())
    
    @property
    def total_cards(self) -> int:
        return sum(len(sigs) for sigs in self.signals_by_game.values())
    
    @property
    def all_signals(self) -> list[Signal]:
        return [s for sigs in self.signals_by_game.values() for s in sigs]


# "native" franchise mapping —— 这些 franchise 在对应游戏不算 cross
NATIVE_FRANCHISE_GAME = {
    "pokemon": Game.POKEMON,
    "magic": Game.MTG,
    "yu_gi_oh": Game.YUGIOH,
    "one_piece": Game.ONE_PIECE,  # native to OPTCG
    "lorcana": Game.LORCANA,
}


def is_native(franchise_normalized: str, game: Game) -> bool:
    """
    Godzilla 在 MTG 不是 native(Godzilla 不是 Magic 自身 IP,是联名)
    Pikachu 在 Pokemon 是 native(就是这游戏本身的角色)
    """
    native_game = NATIVE_FRANCHISE_GAME.get(franchise_normalized)
    return native_game == game


def detect_franchise_moves(
    time_window_days: int = 7,
    min_games_required: int = 2,
    min_confidence_per_signal: float = 60,
) -> list[CrossTcgSignal]:
    """
    返回检测到的 Franchise Move 列表(已去重、已排序)。
    """
    cutoff = datetime.utcnow() - timedelta(days=time_window_days)
    
    # Step 1: 拿近 N 天所有 MOVE/BREAKOUT signal
    recent_signals = Signal.query.filter(
        Signal.trigger_type.in_(["PRICE_MOVE", "PRICE_BREAKOUT"]),
        Signal.created_at >= cutoff,
        Signal.confidence >= min_confidence_per_signal,
    ).all()
    
    # Step 2: 按 franchise 聚合
    buckets: dict[str, FranchiseBucket] = {}
    
    for signal in recent_signals:
        # 拿到这个 asset 的所有 FRANCHISE tags(confidence > 0.7)
        franchise_tags = [
            t for t in signal.asset.ip_tags
            if t.tag_type == "FRANCHISE" and t.confidence >= 0.7
        ]
        
        for tag in franchise_tags:
            fr = tag.tag_value_normalized
            if fr not in buckets:
                buckets[fr] = FranchiseBucket(
                    franchise=fr,
                    signals_by_game=defaultdict(list)
                )
            buckets[fr].signals_by_game[signal.asset.game].append(signal)
    
    # Step 3: 过滤出"跨 game"的 bucket
    cross_signals = []
    for franchise, bucket in buckets.items():
        if len(bucket.games) < min_games_required:
            continue
        
        # 排除"native game"—— 如 Pokemon franchise 在 Pokemon game 不算
        # 但 Pokemon IP 联动到其他游戏算
        non_native_games = {
            g for g in bucket.games
            if not is_native(franchise, g)
        }
        
        # 规则:
        # 1. 至少 2 个 non-native game(跨界严格) OR
        # 2. 1 个 non-native + native game 都动(说明 "本家 + 联名一起动")
        if len(non_native_games) >= min_games_required or (
            len(non_native_games) >= 1 and 
            len(bucket.games) >= 2
        ):
            confidence = compute_cross_confidence(bucket)
            cross_signals.append(_build_cross_signal(bucket, confidence))
    
    # Step 4: 去重 —— 同 franchise 今天已经生成过就跳过
    cross_signals = _dedupe_recent(cross_signals, cooldown_days=3)
    
    # 按 confidence 排序
    cross_signals.sort(key=lambda s: s.confidence, reverse=True)
    
    return cross_signals


def compute_cross_confidence(bucket: FranchiseBucket) -> float:
    """
    Confidence 打分:
    - base = 涉及 signal 的平均 confidence
    - +15 如果 >= 3 个 game 都动(强跨界)
    - +10 如果所有 signal 都在同 24h 内(同步性强)
    - +5 如果 franchise 在 CROSS_IP_WHITELIST(已验证高可信跨界 IP)
    - -10 如果 total_cards < 3(样本小)
    - cap at 95
    """
    signals = bucket.all_signals
    base = sum(s.confidence for s in signals) / len(signals)
    
    bonus = 0
    if len(bucket.games) >= 3:
        bonus += 15
    
    # 所有 signal 在同 24h
    times = [s.created_at for s in signals]
    if max(times) - min(times) < timedelta(hours=24):
        bonus += 10
    
    if bucket.franchise in CROSS_IP_WHITELIST:
        bonus += 5
    
    if bucket.total_cards < 3:
        bonus -= 10
    
    return min(95, max(0, base + bonus))


# 经过验证的高可信 cross-IP franchise
CROSS_IP_WHITELIST = {
    "godzilla", "star_wars", "marvel", "dc", "lord_of_the_rings",
    "stranger_things", "fortnite", "walking_dead", "fallout",
    "assassins_creed", "jurassic_park", "transformers",
}


def _build_cross_signal(bucket: FranchiseBucket, confidence: float) -> CrossTcgSignal:
    return CrossTcgSignal(
        signal_type="FRANCHISE_MOVE",
        anchor_tag_type="FRANCHISE",
        anchor_tag_value=bucket.franchise,
        games_json=sorted([g.value for g in bucket.games]),
        child_signal_ids=[s.id for s in bucket.all_signals],
        total_cards=bucket.total_cards,
        confidence=confidence,
        ai_explanation=None,  # 由后续 step 填入
        expires_at=datetime.utcnow() + timedelta(days=7),
        status="active",
    )


def _dedupe_recent(
    signals: list[CrossTcgSignal], 
    cooldown_days: int
) -> list[CrossTcgSignal]:
    """同一 franchise 最近 N 天已生成过则跳过,避免刷屏"""
    cutoff = datetime.utcnow() - timedelta(days=cooldown_days)
    recent_franchises = set(
        s.anchor_tag_value for s in CrossTcgSignal.query.filter(
            CrossTcgSignal.detected_at >= cutoff,
            CrossTcgSignal.signal_type == "FRANCHISE_MOVE",
            CrossTcgSignal.status == "active"
        )
    )
    return [s for s in signals if s.anchor_tag_value not in recent_franchises]
```

#### 3.2.2 Cross-TCG 的 AI Explanation

```python
# 跨 TCG 信号的解释用 Claude(不用 Haiku,这是高价值信号,Sonnet 更好)

CROSS_TCG_EXPLAINER_PROMPT = """
You are a trading card market analyst writing a 2-3 sentence explanation 
for why multiple games' cards are moving together.

Signal details:
- Franchise/theme: {franchise}
- Games affected: {games}
- Cards that moved: {card_count}
- Top cards:
{top_cards}
- Time window: last {days} days

Possible drivers to consider (pick the most likely, don't force a reason 
if none fits):
1. Recent movie/TV/anime release featuring this franchise
2. New crossover product announced (e.g. "Secret Lair X", "Universes Beyond")
3. Anniversary or milestone for the IP
4. Nostalgia cycle (generational demand revival)
5. Unrelated coincidence (say so plainly if confidence is low)

Be honest. Do not invent events you are not sure about. 
If you don't know why, say "Driver unclear; worth watching."

Output: 2-3 sentences, plain English, no bullet points.
"""


def explain_cross_signal(signal: CrossTcgSignal) -> str:
    top_cards = _get_top_cards_for_signal(signal, limit=5)
    
    prompt = CROSS_TCG_EXPLAINER_PROMPT.format(
        franchise=signal.anchor_tag_value,
        games=", ".join(signal.games_json),
        card_count=signal.total_cards,
        top_cards="\n".join(
            f"  - {c.name} ({c.game}): {c.price_change_pct:+.1f}% in 7d"
            for c in top_cards
        ),
        days=7,
    )
    
    response = anthropic_client.messages.create(
        model="claude-sonnet-4-6",  # 这是 flagship 功能,用好模型
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()
```

---

### 3.3 Cultural Trigger Detector(P1,MVP 后)

```python
# app/services/signal/cross_tcg/cultural_trigger.py

def detect_cultural_triggers() -> list[CrossTcgSignal]:
    """
    对每个过去 14 天内的 external_event:
    1. 找到该 franchise 所有跨游戏的 asset
    2. 检查其价格在事件日前后 14 天的变化
    3. 如果 >X% 的相关卡在事件后有 MOVE+,生成 Cultural Trigger signal
    """
    recent_events = ExternalEvent.query.filter(
        ExternalEvent.event_date >= datetime.utcnow().date() - timedelta(days=14),
        ExternalEvent.event_date <= datetime.utcnow().date(),
    ).all()
    
    triggers = []
    for event in recent_events:
        relevant_assets = _find_assets_by_franchises(event.franchise_tags)
        
        # 检查事件后价格响应
        responding_assets = []
        for asset in relevant_assets:
            price_change = _get_price_change_since(
                asset, since=event.event_date, window_days=14
            )
            if price_change > 10:  # 10% 阈值
                responding_assets.append((asset, price_change))
        
        # 如果 >30% 的相关卡响应,认为这是真正的 cultural trigger
        if len(responding_assets) / max(1, len(relevant_assets)) >= 0.3:
            games = set(a[0].game for a in responding_assets)
            if len(games) >= 2:
                triggers.append(_build_cultural_trigger_signal(event, responding_assets))
    
    return triggers
```

MVP 阶段 external_event 表手工维护,这是成本最低的启动方式。

---

## 4. UI/UX 建议

### 4.1 Signals 页面的 Cross-TCG section

```
┌─────────────────────────────────────────────────────┐
│ 🌐 Cross-TCG Movers                        Pro only  │
├─────────────────────────────────────────────────────┤
│                                                       │
│  Godzilla             [88] confidence                 │
│  🎴 MTG + 🗡️ One Piece TCG                            │
│  12 cards moving — Driver: Godzilla x Kong 2 trailer │
│  [View signals →]                                     │
│                                                       │
│  ─────────────────────────────────────────────────── │
│                                                       │
│  Star Wars            [76] confidence                 │
│  🎴 MTG + ✨ Lorcana (announced)                      │
│  8 cards moving — Driver: unclear; worth watching    │
│  [View signals →]                                     │
│                                                       │
└─────────────────────────────────────────────────────┘
```

### 4.2 Cross-TCG Signal Detail Page

```
Godzilla — Cross-TCG Franchise Move                    
Detected 2 days ago · Confidence 88 · Active

WHY THIS MATTERS
Godzilla x Kong: The New Empire 2 released its first trailer this week, 
and related cards across two games have seen unusual price action. 
This kind of cross-franchise synchronicity often precedes broader market 
attention to the IP over the following 2-4 weeks.

CARDS MOVING                         

┌─────────────────────────┬─────────────────────────┐
│ 🎴 MTG (7 cards)         │ 🗡️ OPTCG (5 cards)      │
├─────────────────────────┼─────────────────────────┤
│ Godzilla, Primal Hunter  │ Godzilla (Promo)        │
│   +32% / 7d, conf 84    │   +45% / 7d, conf 78    │
│ Mothra, Supersonic Quee  │ Mothra (OP-09-017)      │
│   +18% / 7d, conf 72    │   +21% / 7d, conf 70    │
│ ...                      │ ...                      │
└─────────────────────────┴─────────────────────────┘

ACTION SUGGESTIONS (Pro)
• Add Godzilla franchise to your watchlist
• Compare MTG Godzilla series with OPTCG Godzilla releases
• Consider EDH staples in Ikoria set for long-tail appreciation
```

---

## 5. 测试策略

### 5.1 IP Tagging 测试样本

至少 20 张已知跨 IP 卡,验证 FRANCHISE 识别准确率:

| 卡名 | 游戏 | 期望 FRANCHISE tags |
|---|---|---|
| Godzilla, King of the Monsters | MTG | godzilla + magic |
| Deadpool, Trading Card (Secret Lair) | MTG | marvel + deadpool + magic |
| Luffy - Straw Hat Pirate | OPTCG | one_piece |
| Pikachu | Pokemon | pokemon |
| Elsa (Lorcana) | Lorcana | lorcana + disney + frozen |
| Stranger Things - Eleven | MTG Secret Lair | stranger_things + magic |
| ... | | |

目标准确率 > 85%(20 张对 17+ 张)。

### 5.2 Franchise Move 测试

构造 mock 数据场景:

**场景 1: 真正的 Franchise Move**
- 插入 3 张 MTG Godzilla 卡,每张一个 MOVE signal(7 天内)
- 插入 2 张 OPTCG Godzilla 卡,每张一个 MOVE signal(7 天内)
- 运行 detector
- 期望:输出 1 个 "Godzilla" cross signal,confidence > 70

**场景 2: 同 franchise 只在 1 个 game(不应触发)**
- 5 张 Pokemon Charizard variant 都涨
- 运行 detector
- 期望:空(因为只在 Pokemon 一个 game,且是 native)

**场景 3: native franchise 不计入 cross**
- 10 张 Pokemon 卡涨(FRANCHISE="pokemon")
- 5 张 MTG Magic 卡涨(FRANCHISE="magic")
- 运行 detector
- 期望:空(两个都是 native)

**场景 4: 冷却期**
- 今天生成 Godzilla cross signal
- 3 天后再次检测到 Godzilla move
- 期望:第二次不再生成(cooldown)

---

## 6. 实施路径建议

按风险递增顺序实施:

```
Week 9.1: TASK-015 IP tagging 基础设施 + 手工 tag 20 个测试 asset
Week 9.2: 跑全量 Pokemon tagging(先小范围验证成本和质量)
Week 9.3: TASK-016 Franchise Move detector 骨架
Week 9.4: 端到端跑通 mock 场景,验证算法正确

Week 10+: 接入真实 YGO + MTG 数据后,detector 会开始产真实结果
         观察 1-2 周,调 confidence 阈值和 cooldown

Week 11+(可选): Cultural Trigger MVP(手工 event 表)
```

---

## 7. 长期 roadmap(不在 12 周 scope 但值得规划)

- **Cultural Trigger 自动化**:接入 TMDB / Anilist / Goodreads 等 API 自动抓影视/动漫事件
- **Meta Spillover**:分析两游戏价量反向关系,MTG 新 set 上市 vs Pokemon 销量迁移
- **用户订阅**:用户可以订阅 "Godzilla" franchise,有 cross signal 时 push 通知
- **Historical backtest**:回看过去 1 年的 cross signal 是否真的提前预警了重要行情
- **Dashboard**:Franchise-level 视图,显示哪些 IP 跨游戏活跃度最高

---

这是 Flashcard Planet 的唯一护城河,值得 75% 的 flagship 资源投入。
