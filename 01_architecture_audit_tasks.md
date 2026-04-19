# 01 — 架构 Audit 与 Claude Code 可执行任务包

*目的:把"后端 game-agnostic 化"拆成 Claude Code 可以一条条执行的任务*
*用法:每个 TASK 块可独立丢给 Claude Code,按顺序执行*

---

## 关于假设的说明

以下任务基于你计划书透露的架构做了合理推断。如果实际代码库路径/命名与假设不符,
把任务里的 `<假设路径>` 换成实际路径即可,核心逻辑不变。

**已知事实(来自你计划书):**
- 后端 Python,80 个文件,138 个测试
- 模块:数据采集 / 价格分析 / 信号 / LLM 抽象层 / eBay ingest / Review UI / Signals 页 / 补全 pass / Discord Bot / Web UI / Auth
- 已存在:Pokemon TCG API、RealEbayClient、IQR 过滤、signal_explainer、ai_mapper、User.access_tier

**未知(需要你核对):**
- ORM 是 SQLAlchemy / Django / 其他?
- 目录结构(以下假设为 `backend/` + `app/models/` + `app/services/`)
- 是否已有 game 概念(几乎肯定**没有**,整个系统默认就是 Pokemon)

---

## Phase 0 — 代码库盘点(Claude Code Task #0)

### TASK-000: 生成 Pokemon-specific 代码清单

```
给 Claude Code 的 prompt:

在当前仓库里,找出所有明显是 Pokemon-specific 的代码。扫描维度:
1. 文件名包含 "pokemon"、"pkmn"、"ptcg"(大小写不敏感)
2. 类名/函数名包含上述关键词
3. 字符串常量中硬编码 Pokemon TCG API base URL(api.pokemontcg.io)
4. 硬编码 Pokemon set code(如 "base1"、"jungle"、"fossil")
5. 数据库字段或枚举明确假设"只有 Pokemon"(如 asset 表没有 game 字段)

输出格式为 markdown,按上面 5 个类别分组,每项包含:
- 文件相对路径
- 行号
- 代码片段(前后 2 行上下文)
- 建议的重构方向(rename / add game param / extract interface / keep)

不要修改任何代码,只生成清单。把结果写到 audit_report.md。

完成后,报告三个数字:
- 需要 rename 的符号数
- 需要加 game 参数的函数数  
- 需要做接口抽象的地方数
```

**验收**: `audit_report.md` 存在,三类问题有明确数量。

---

## Phase 1 — 数据模型改造(Claude Code Task #1-3)

### TASK-001: 引入 Game 概念到数据模型

```
给 Claude Code 的 prompt:

目标:在现有数据模型中引入 "game" 概念,为多 TCG 做准备。

背景:当前系统默认所有数据都是 Pokemon,asset/observation/price_point/signal 
等核心表没有 game 字段。

要做的事(请严格按顺序):

1. 在 app/models/ (或实际位置) 新建 game.py,定义:

   class Game(Enum):
       POKEMON = "pokemon"
       YUGIOH = "yugioh"
       MTG = "mtg"
       ONE_PIECE = "one_piece"
       LORCANA = "lorcana"
   
   配套一个 GAME_CONFIG dict,每个 game 对应:
   - display_name: str (如 "Pokémon")
   - ebay_search_prefix: str (用于 eBay 搜索关键字)
   - external_api: str (如 "pokemon_tcg_api" / "scryfall" / "ygoprodeck")
   - status: str ("live" | "beta" | "coming_soon")
   - launched_at: datetime
   
   目前只有 POKEMON 设为 "live",其他 "coming_soon"。

2. 数据库迁移:在 asset 表加一个 game 字段(str/enum),默认值 "pokemon",
   NOT NULL 约束。同时给 observation、price_point、signal、alert 表都加 game 字段,
   通过 asset 的外键可以追溯,但冗余存储这个字段以便按 game 快速查询。

3. 生成 alembic/django migration,migration 名含日期和 "add_game_field"。

4. **关键**:所有现有数据 backfill 为 "pokemon"。migration 必须包含 data migration 步骤,
   不只是 schema migration。

5. 更新所有相关 model 的 __repr__ 加上 game 标识。

6. 跑所有测试,确保全 138 个测试仍通过(可能需要在 test fixtures 里加 game="pokemon")。
   如果有 fixtures 需要批量改,改完后确认 test pass。

7. 不要改任何 business logic,这一步纯粹是加字段和 backfill。

输出:
- git diff 摘要
- migration 文件路径
- 测试结果
```

**验收**:
- `asset.game` 字段存在,现有数据全部 = "pokemon"
- 138 个测试仍通过
- 无 business logic 改动

---

### TASK-002: 抽象 external data client 接口

```
给 Claude Code 的 prompt:

目标:把现有的 Pokemon TCG API client 抽象成一个可替换的 interface,
让后续接入 Scryfall / YGOPRODeck / eBay-only(OPTCG, Lorcana)时只需实现该接口。

背景:当前应该有一个类似 PokemonTcgApiClient 的类负责拉取卡片元数据。
我们要把它的行为抽成抽象基类,然后让 Pokemon 版本成为一个具体实现。

步骤:

1. 在 app/services/game_data/ 下新建:
   - __init__.py
   - base.py: 定义抽象基类 GameDataClient
   - pokemon_client.py: 现有 PokemonTcgApiClient 重命名并继承 GameDataClient
   - registry.py: GameDataClientRegistry

2. GameDataClient 抽象接口:

   class GameDataClient(ABC):
       @abstractmethod
       def fetch_card_by_id(self, external_id: str) -> CardMetadata: ...
       
       @abstractmethod
       def fetch_cards_by_set(self, set_code: str) -> list[CardMetadata]: ...
       
       @abstractmethod
       def list_sets(self) -> list[SetMetadata]: ...
       
       @abstractmethod
       def get_image_url(self, card: CardMetadata, size: str = "normal") -> str: ...
       
       @property
       @abstractmethod
       def game(self) -> Game: ...
       
       @property
       @abstractmethod
       def rate_limit_per_second(self) -> float: ...

3. CardMetadata 是一个 TypedDict 或 dataclass,包含所有游戏共通的字段:
   external_id, name, set_code, set_name, collector_number, rarity, 
   image_url, game, raw_payload (dict, game-specific 原始数据留存)

4. GameDataClientRegistry 是一个单例,提供:
   - register(game: Game, client: GameDataClient)
   - get(game: Game) -> GameDataClient
   - all_live_games() -> list[Game]  # 过滤 status=live 的
   
   在 app 启动时自动 register PokemonClient(POKEMON)。

5. 现有所有代码里对 PokemonTcgApiClient 的直接引用,改为通过 registry 获取:
   client = GameDataClientRegistry.get(Game.POKEMON)

6. 给 GameDataClient 和 PokemonClient 写 unit test,放到 tests/services/game_data/。

7. 跑全部测试,确保不破坏任何现有行为。

输出:
- 新建的文件列表
- 测试结果(新增测试数 + 全量测试通过)
```

**验收**:
- 所有对 `PokemonTcgApiClient` 的直接 import 都消失
- Registry 单元测试覆盖率 100%
- 138 + 新增测试全部通过

---

### TASK-003: 抽象 asset mapping 规则

```
给 Claude Code 的 prompt:

目标:你现有的 ai_mapper 把 eBay 标题映射到 Pokemon asset,里面应该有
Pokemon-specific 的识别规则(Holo、Reverse Holo、1st Edition、PSA grading 等)。
要把它重构成 "per-game rule set" 架构。

背景:MTG 需要识别 foil/etched foil/showcase/borderless,Yu-Gi-Oh 需要识别
"1st Edition"/Ghost Rare/Starlight Rare,OPTCG 需要识别 English/Japanese,
这些规则不能写死在一个文件里。

步骤:

1. 在 app/services/mapping/ 下新建:
   - base.py: MappingRuleSet ABC
   - pokemon_rules.py: PokemonMappingRules (把现有 Pokemon 规则搬过来)
   - __init__.py

2. MappingRuleSet 接口:

   class MappingRuleSet(ABC):
       @abstractmethod
       def parse_title(self, title: str) -> ParsedListing: ...
       # ParsedListing 包含:card_name_guess, set_guess, number_guess, 
       # grade (None or "PSA 10" etc), variant (Holo/Foil/etc), 
       # language, confidence_breakdown (dict of sub-scores)
       
       @abstractmethod
       def compute_match_confidence(self, parsed: ParsedListing, 
                                     candidate: CardMetadata) -> float: ...
       # 返回 0-100 分
       
       @property
       @abstractmethod
       def game(self) -> Game: ...

3. 把现有 ai_mapper 里的 Pokemon 规则抽到 PokemonMappingRules,
   保持行为完全一致,只是位置改变。

4. ai_mapper 的主入口函数改为:
   
   def map_observation_to_asset(observation, game: Game) -> MappingResult:
       rules = MappingRuleRegistry.get(game)
       parsed = rules.parse_title(observation.raw_title)
       # ... 原有逻辑继续,但调用 rules 方法而非硬编码

5. 所有现有的 mapping 测试应该仍然 pass(因为 Pokemon 规则行为未变)。
   另外给 MappingRuleSet 架构本身加 3-5 个架构级测试。

6. **不要**在这一步实现 MTG / Yu-Gi-Oh 规则。它们是后续 task。
   但是在代码里留一个 TODO 占位文件(yugioh_rules.py, mtg_rules.py)
   内容是 NotImplementedError 的骨架。

输出:
- diff 摘要
- Pokemon 相关 mapping 测试是否全 pass
- 架构测试数量
```

**验收**:现有 Pokemon 映射行为 100% 一致,但代码已按 game 分离。

---

## Phase 2 — 信号引擎 game-aware 化(Claude Code Task #4-5)

### TASK-004: signal_explainer 的 per-game prompt 模板

```
给 Claude Code 的 prompt:

目标:你的 signal_explainer 调用 Anthropic/Groq 生成 AI 解释。现在 prompt 
很可能是 Pokemon-specific 的(提到 "Pokemon set"、"TCG Player" 等)。
要把 prompt 模板按 game 参数化。

步骤:

1. 在 app/services/llm/ (或 signal_explainer 所在目录) 下新建:
   - prompts/
     - base.py: SignalExplainerPrompt ABC
     - pokemon_prompt.py
   - __init__.py

2. SignalExplainerPrompt 接口:

   class SignalExplainerPrompt(ABC):
       @abstractmethod
       def system_prompt(self) -> str: ...
       
       @abstractmethod
       def user_prompt(self, signal: Signal, context: dict) -> str: ...
       # context 包含:card metadata, recent observations, similar cards' 
       # trajectories, any game-specific context (banlist changes for YGO, 
       # reprint rumors for MTG, new set release for Pokemon)
       
       @abstractmethod
       def game_specific_vocabulary(self) -> dict[str, str]: ...
       # 如 MTG: {"meta": "Standard/Modern/Legacy format", 
       #          "reprint": "card being printed again in a new set"}

3. PokemonPrompt 实现包含:
   - system_prompt 强调 Pokemon TCG 文化(set releases, anniversary cycles, 
     graded market premium for vintage)
   - Japanese vs English 版本差异
   - 对 Modern Gen-9 vs Vintage WOTC 的不同分析角度
   
4. signal_explainer 的调用入口改为:
   
   def explain_signal(signal: Signal) -> str:
       prompt_cls = SignalExplainerPromptRegistry.get(signal.game)
       prompt = prompt_cls()
       messages = [
           {"role": "system", "content": prompt.system_prompt()},
           {"role": "user", "content": prompt.user_prompt(signal, context)},
       ]
       # 继续现有 LLM 调用

5. 留 yugioh_prompt.py / mtg_prompt.py 骨架(NotImplementedError)。

6. 写测试:mock LLM 响应,验证对 Pokemon signal 的 prompt 构造正确。

输出:
- diff 摘要
- 新增测试数
- 验证现有 explainer 行为未变(样本对比)
```

**验收**:signal_explainer 对现有 Pokemon signal 产出的解释质量不下降。

---

### TASK-005: signal 生成引擎 game-aware

```
给 Claude Code 的 prompt:

目标:BREAKOUT/MOVE/WATCH/IDLE 的判定阈值在不同 TCG 会不同。例如 MTG Modern 
staples 的正常波动比 Pokemon vintage 大得多。要把阈值从硬编码抽成 per-game config。

步骤:

1. 在 app/services/signal/ 下新建 thresholds.py:

   @dataclass
   class SignalThresholds:
       breakout_pct_7d: float     # >X% 涨幅 -> BREAKOUT
       move_pct_7d: float          # >X% 涨幅 -> MOVE
       watch_pct_7d: float         # >X% 涨幅 -> WATCH
       min_sample_size: int        # 至少 N 笔成交才产信号
       min_liquidity_score: float  # 至少 liquidity X 才产高置信信号
       volatility_floor: float     # 低于此波动率视为 IDLE

   THRESHOLDS = {
       Game.POKEMON: SignalThresholds(breakout_pct_7d=25, move_pct_7d=10, 
                                       watch_pct_7d=5, min_sample_size=5, 
                                       min_liquidity_score=30, 
                                       volatility_floor=2),
       # 其他 game 后续填,先用 Pokemon 值做 fallback
   }

2. signal 生成逻辑里所有硬编码的阈值数字,改为 THRESHOLDS[game].xxx 取值。

3. 如果 game 不在 THRESHOLDS,记录 warning 并 fallback 到 Pokemon 阈值。

4. 加一个 admin-only endpoint /backstage/thresholds 展示当前各 game 的阈值
   (调参时方便查看,不做 UI)。

5. 跑测试:现有 Pokemon signal 生成行为不变。新增测试覆盖 game != POKEMON 
   时的 fallback 行为。

输出:
- 现有 signal 测试是否全 pass
- 新增 fallback 测试
- /backstage/thresholds 返回 JSON 示例
```

**验收**:现有 Pokemon 信号产出的 BREAKOUT/MOVE/WATCH 分布不变。

---

## Phase 3 — eBay pipeline game-aware(Claude Code Task #6)

### TASK-006: RealEbayClient 增加 game 参数

```
给 Claude Code 的 prompt:

目标:你的 RealEbayClient 目前大概率只搜 Pokemon 相关关键字。要让它按 game 
动态组装搜索 query。

步骤:

1. GAME_CONFIG 里每个 game 补充字段:
   - ebay_categories: list[int]  # eBay category ID
   - ebay_search_terms: list[str]  # 基础关键字(如 Pokemon: ["Pokemon TCG", 
     "Pokemon card"], MTG: ["Magic the Gathering", "MTG card"])
   - ebay_exclude_terms: list[str]  # 排除噪声(如 "proxy", "custom")

2. RealEbayClient 接口改为:

   class RealEbayClient:
       def fetch_recent_sales(self, game: Game, 
                              additional_query: str = "") -> list[RawObservation]:
           config = GAME_CONFIG[game]
           # 组装 query 用 config.ebay_search_terms + additional_query
           # 过滤 config.ebay_exclude_terms
           # ...

3. 每日调度任务改为循环所有 live games:
   
   for game in GameDataClientRegistry.all_live_games():
       observations = ebay_client.fetch_recent_sales(game)
       for obs in observations:
           obs.game = game
           store_observation(obs)

4. 每日预算限额按 game 独立配额(config 里加 ebay_daily_budget 字段,
   Pokemon 继承现有,其他先给 0 以免扩展时误花钱)。

5. 测试:mock eBay API,验证不同 game 产生不同 query。现有 Pokemon 
   ingest 行为不变(因为 Pokemon 是唯一 live)。

输出:
- diff 摘要
- 测试覆盖
- 确认 Pokemon 每日 ingest 数量不变
```

**验收**:每日 Pokemon observation 数维持现有水平,pipeline 已准备好接纳新 game。

---

## Phase 4 — Web UI / API game-aware(Claude Code Task #7-8)

### TASK-007: API endpoint 接受 game 参数

```
给 Claude Code 的 prompt:

目标:所有列表型 endpoint(卡牌浏览、信号列表、漲跌榜、watchlist 等)
支持 game filter。

步骤:

1. 盘点所有这类 endpoint,对每个:
   - 在 query params 加 game: Optional[str] = None
   - None 时默认行为:返回用户上次选择的 game(存在 user pref 里),
     没有 pref 则默认 POKEMON
   - 非 None 时验证是否 valid Game enum,否则 400
   - filter query 加 .filter(asset.game == game)

2. User model 加 preferred_game 字段(default POKEMON)。加 migration。

3. 新增 endpoint GET /api/games 返回所有 live + coming_soon games 的清单,
   供前端构建 game selector。

4. 更新 OpenAPI / API docs。

5. 测试:每个改动的 endpoint 加一个"指定 game=mtg 返回空"的测试用例
   (因为 MTG 暂无数据,但不应报错)。

输出:
- 改动的 endpoint 清单
- 测试结果
```

**验收**:现有 Pokemon UI 行为完全不变,但 API 可通过 `?game=...` 切换。

---

### TASK-008: Web UI Game Selector 组件

```
给 Claude Code 的 prompt:

目标:在顶部 nav 加一个 game selector,切换后整站上下文切换。

背景:当前 UI 默认 Pokemon。我们加一个下拉/标签式选择器,让用户明确选择。

步骤:

1. 在 components/ 下新建 GameSelector.(jsx/vue/etc):
   - 通过 GET /api/games 获取列表
   - live games 正常显示
   - coming_soon games 显示为灰色 + "Coming [ETA]" 标签,不可点
   - 用户选择后:
     a. PATCH /api/users/me { preferred_game: xxx }
     b. 触发全局 state 更新
     c. 当前路由的数据重新加载(按新 game 过滤)

2. 在 Layout/Header 组件引入 GameSelector。

3. 全局 state 增加 currentGame,由 GameSelector 控制。所有列表型 
   component 用 currentGame 作为 API query 的 game 参数。

4. 首次访问用户(未登录或无 preferred_game):
   - 默认 POKEMON
   - 首次打开时弹一个小 toast:"Flashcard Planet now covers more games — 
     pick your favorite above" (24 小时内只弹一次,localStorage 记录)

5. 移动端:不要塞在 header 里挤,做成 bottom-sheet 触发的选择器。

6. 视觉要求:遵循现有设计语言,不过度喧宾夺主,但 live/coming_soon 
   状态必须一眼区分。

输出:
- 改动文件清单
- 截图 (desktop + mobile)
- 测试:切换 game 后数据正确刷新
```

**验收**:用户可在 5 次点击内从 Pokemon 切到 Yu-Gi-Oh 再切回。

---

## Phase 5 — Yu-Gi-Oh 接入(Claude Code Task #9-11)

### TASK-009: YugiohClient 实现

```
给 Claude Code 的 prompt:

目标:基于 YGOPRODeck 的 API 实现 YugiohClient,遵循 TASK-002 建立的
GameDataClient 接口。

规格:
- Base URL: https://db.ygoprodeck.com/api/v7/
- Rate limit: 20 req/s (但保守用 10 req/s)
- 主要端点:
  - /cardinfo.php (GET card info, 支持 id / name / set 过滤)
  - /cardsets.php (所有 sets)
  - /checkDBVer.php (检查是否有更新)

步骤:

1. 创建 app/services/game_data/yugioh_client.py,实现 YugiohClient(GameDataClient)。

2. fetch_card_by_id:
   - 调 /cardinfo.php?id=X
   - 把返回映射到 CardMetadata,重要字段:
     - external_id = data["id"]
     - name = data["name"]
     - set_code / set_name / collector_number 从 data["card_sets"] 取
       (YGO 一张卡可能有多个 printing,需要选择主要 set)
     - rarity = data["card_sets"][0]["set_rarity"]
     - image_url = data["card_images"][0]["image_url"]
     - raw_payload = data (完整保留,后续做 banlist 追踪要用)

3. 实现一个 daily_sync job:
   - 每天调 /checkDBVer.php,如无变化则跳过
   - 有变化时拉取全量卡(/cardinfo.php 不带参数返回所有卡,约 13,000+ 张)
   - 对比本地 asset 表,新增 / 更新 / 标记停印
   
4. 实现 banlist 同步:
   - GET /cardinfo.php?banlist=tcg 获取当前所有被限制的卡
   - 在 asset 表加一个可选字段 game_metadata (JSON),YGO 卡存 banlist 状态
   - banlist 变化是重要 signal source,见 TASK-010

5. 把 YGOPRODeck 要求的 cache / 速率控制正确实现:
   - 响应缓存 24h(YGO 数据不频繁变)
   - 图片必须 download 到自己的 storage(CDN / S3 / 本地),不 hotlink
   - User-Agent 自定义为 "FlashcardPlanet/1.0"

6. 注册到 GameDataClientRegistry,Game.YUGIOH 仍保持 "coming_soon" 直到 UI 就绪。

7. 测试:mock YGOPRODeck 响应,验证映射逻辑。

输出:
- 文件清单
- 测试结果
- 一张实际 Yu-Gi-Oh 卡(如 "Dark Magician")的完整转换结果示例
```

**验收**:手动调 client.fetch_card_by_id("46986414") 返回 Dark Magician 的完整 CardMetadata。

---

### TASK-010: Yu-Gi-Oh 映射规则 + banlist signal

```
给 Claude Code 的 prompt:

目标:实现 YugiohMappingRules 和 "banlist-triggered signal" 新信号类型。

Part 1 — 映射规则(app/services/mapping/yugioh_rules.py):

要识别的 YGO-specific 变量:
- Edition: "1st Edition" / "Unlimited" / "Limited" (在标题里通常是 "1st Ed" / 不标)
- Rarity: Common / Rare / Super Rare / Ultra Rare / Secret Rare / 
  Ghost Rare / Starlight Rare / Quarter Century Secret Rare / 等
- Grading: PSA / BGS / CGC + grade number
- Set code: 如 "LOB-001", "SDY-046"(通常在标题里)
- Language: "English" / "Japanese" / "Korean"(影响价格)
- 版本变体:"Duel Terminal" vs normal, "Retro Pack" vs original printing

实现 parse_title 用正则组合识别上述维度。compute_match_confidence 做加权:
- set_code 精确匹配 +40
- collector_number 精确匹配 +30
- 卡名 fuzzy match +20
- rarity 匹配 +5
- edition 匹配 +5

Part 2 — Banlist signal 类型:

1. 在 Signal model 加一个 trigger_type 字段(enum):
   PRICE_MOVE, PRICE_BREAKOUT, LIQUIDITY_SHIFT, BANLIST_CHANGE, 
   REPRINT_ANNOUNCEMENT(最后两个是未来用的)。

2. 新建 app/services/signal/triggers/banlist_trigger.py:
   - 每次 Yu-Gi-Oh banlist 同步后调用
   - 对比新旧 banlist,找出 status change 的卡:
     - Unlimited -> Forbidden(通常价格会跌 30-70%)
     - Forbidden -> Limited(通常价格会涨 50-200%)
     - Limited -> Semi-Limited / Unlimited(通常涨幅中等)
   - 对每张 status 变化的卡,生成一个 BANLIST_CHANGE signal,
     confidence 默认高(80+),因为这是 fundamental 驱动
   - AI explanation 里说明 status change 方向和典型历史影响

3. 测试:构造一个 mock banlist diff,验证 signal 生成逻辑。

Part 3 — 映射规则测试:
准备 10 个真实 eBay YGO 标题样本(可从我给你的测试数据拿或让 Claude 造),
验证 parse_title 和 compute_match_confidence 对它们的输出合理。

输出:
- diff 摘要
- 映射测试准确率(>70% 视为通过)
- banlist signal 演示(mock data)
```

**验收**:给定 10 个真实 YGO eBay 标题,至少 7 个能被正确映射(confidence > 60)。

---

### TASK-011: Yu-Gi-Oh 上线 checklist

```
给 Claude Code 的 prompt:

目标:把 Yu-Gi-Oh 从 "coming_soon" 切到 "live",完整端到端验证。

步骤:

1. 跑 TASK-009 的 daily_sync,填充 Yu-Gi-Oh asset 表(预期 ~13,000 卡)。

2. 手动 enable eBay ingest for Game.YUGIOH,给一个保守预算(如 $5/天)。
   观察 24h 内 observation 数和映射率。

3. 手动触发 signal 生成 pipeline for Yu-Gi-Oh。预期至少有 10 张卡有 signal。

4. Web UI:
   - GameSelector 中 Yu-Gi-Oh 改为 live 状态
   - 首页 Top Movers 能显示 Yu-Gi-Oh 卡
   - Card Detail 页能展示 Yu-Gi-Oh 卡(图片、价格、sample size)
   - Signals 页能筛选 Yu-Gi-Oh 信号

5. Discord Bot:
   - 支持 /ygo_price <card name> 命令(或统一 /price 命令加 game option)

6. 生成一份"Yu-Gi-Oh 上线健康报告":
   - 卡片总数
   - 有价格数据的卡片数 / 占比
   - 映射成功率(近 24h observation)
   - 生成的 signal 数(按 trigger_type 分类)
   - 图片覆盖率
   - 任何异常(missing images / 错误映射 / 价格异常值)

7. 如果报告指标都达标(见下方验收),更新 GAME_CONFIG[Game.YUGIOH].status = "live"。

验收阈值:
- 卡片入库 > 12,000
- 有价格数据的卡 > 30%
- 映射成功率 > 65%
- 有效 signal 数 > 20
- 图片覆盖率 > 90%
- 无致命错误

输出:
- 健康报告
- 最终是否 "live"
- 下一步待办(如有)
```

**验收**:Yu-Gi-Oh 在 Web UI 完整可用,用户可查询卡、看信号、设预警。

---

## Phase 6 — MTG 接入(Claude Code Task #12-14)

### TASK-012: ScryfallClient 实现 + 合规架构

```
给 Claude Code 的 prompt:

目标:实现 ScryfallClient 并严格遵守 Scryfall 的 "no paywall" 条款。

**关键合规要求(必须先读):**

Scryfall 明文规定:
> "You may not 'paywall' access to Scryfall data. You may not require anyone 
> to make payments, take subscriptions, rate your content, join chat servers, 
> or follow channels in exchange for access to Scryfall data."

这意味着:MTG 卡的**基础信息**(卡名、图片、oracle text、set、rarity、
mana cost)必须对所有用户 Free 可见。Flashcard Planet 的 Pro 收费
只能对 "我们自己生成的分析"(signal、confidence、liquidity、AI explanation、
跨 TCG 关联)收费。

实施对策:在数据层就要把 Scryfall-sourced 字段和 FP-generated 字段分离。

步骤:

1. 创建 app/services/game_data/scryfall_client.py,实现 ScryfallClient。
   - 使用 scrython 库(pip install scrython)
   - 主要工作模式是 bulk data:每日下载 default_cards bulk,不走单卡 API
   - User-Agent: "FlashcardPlanet/1.0 (contact@flashcardplanet.com)"

2. 在 asset 表加一个字段 data_source: str,记录元数据来源:
   - "pokemon_tcg_api" / "ygoprodeck" / "scryfall" / "manual" / "tcgplayer_scrape"
   
3. 在 API 响应层(serializer)增加逻辑:
   - 来自 scryfall 的字段必须在 Free tier 可见
   - 明确标注 "Card data provided by Scryfall. Flashcard Planet is 
     unaffiliated with Scryfall or Wizards of the Coast."
   - Footer / About 页加归属声明

4. fetch 逻辑:
   - 每日 cron 调 /bulk-data/default_cards 获取 URL
   - 下载 JSON(几百 MB),解析
   - 映射到 CardMetadata:
     - external_id = scryfall id (UUID)
     - name = card["name"]
     - set_code = card["set"], set_name = card["set_name"]
     - collector_number = card["collector_number"]
     - rarity = card["rarity"]
     - image_url = card["image_uris"]["normal"] (双面卡走 card_faces)
     - raw_payload = card (完整保留,tcgplayer_id 等后续要用)

5. 图片处理:
   - 下载并缓存到自己的 storage(Scryfall 允许使用图片,但不要 hotlink 大规模)
   - 保持 artist name 和 copyright 完整,不要裁剪

6. 双面卡(Transform、MDFC、Adventure)特殊处理:
   - card["card_faces"] 存在时,存两张 face 共享 asset 或用主 face
   - 决策:初版只存 front face,raw_payload 里保留 faces 数组

7. 注册到 Registry,Game.MTG 维持 "coming_soon"。

8. 测试:
   - mock bulk data,验证解析
   - 验证 data_source 字段正确填充
   - 合规 checklist 测试:fetch 出来的 MTG asset 的元数据字段对匿名用户(Free)可见

输出:
- 文件清单
- 测试结果
- 一张 MTG 卡(如 "Lightning Bolt")的完整转换示例
- 合规 checklist 自查结果
```

**验收**:
- ScryfallClient 可用
- `data_source` 字段正确
- 合规 checklist 全项勾选

---

### TASK-013: MTG 映射规则

```
给 Claude Code 的 prompt:

目标:实现 MtgMappingRules,处理 MTG 独特的版本复杂性。

MTG 的版本维度(按标题出现概率排序):
1. Finish: normal / foil / etched foil / surge foil / galaxy foil
2. Frame treatment: borderless / showcase / extended art / retro frame / 
   alternate art
3. Promo: prerelease stamp / date stamp / judge promo / buy-a-box / 
   FNM promo
4. Language: English / Japanese / Russian / etc
5. Condition + Grade: NM/LP/MP/HP 或 PSA/BGS/CGC 分数
6. Set code: 如 "LEA" (Alpha), "MH2" (Modern Horizons 2)

步骤:

1. 创建 app/services/mapping/mtg_rules.py,实现 MtgMappingRules。

2. parse_title 重点识别(用正则 + 关键字字典):

   FINISH_PATTERNS = {
       "foil": re.compile(r'\b(foil|holo(foil)?)\b', re.I),
       "etched": re.compile(r'\betched[\s-]?foil\b', re.I),
       "galaxy": re.compile(r'\bgalaxy[\s-]?foil\b', re.I),
       "surge": re.compile(r'\bsurge[\s-]?foil\b', re.I),
   }
   FRAME_PATTERNS = {
       "borderless": re.compile(r'\bborderless\b', re.I),
       "showcase": re.compile(r'\bshowcase\b', re.I),
       "extended_art": re.compile(r'\bextended[\s-]?art|EA\b', re.I),
       "retro": re.compile(r'\bretro\s?frame\b', re.I),
   }
   PROMO_PATTERNS = {
       "prerelease": re.compile(r'\bprerelease|pre-release\b', re.I),
       "fnm": re.compile(r'\bFNM\b'),
       "judge": re.compile(r'\bjudge\s?(promo|foil)\b', re.I),
   }

3. compute_match_confidence 打分权重:
   - set_code exact match: +35
   - collector_number exact: +20
   - card name fuzzy match (>90%): +25
   - finish match: +10
   - frame treatment match: +5
   - language match: +5
   
   如果 parsed 标明是 foil 但 candidate 不是 foil 的印刷,confidence -50
   (这是 MTG 特有的,foil 和 non-foil 价格差异巨大)。

4. 对于有 tcgplayer_id 的 asset,可以在 observation 里尝试 direct match
   (eBay 标题如含 "TCG" 和 ID)。

5. 特殊处理:
   - MTG 有 "Secret Lair" 系列,卡名和 set 都特殊,单独一类规则
   - 基本地(Basic Land)不追踪,volume 太大噪音太多

6. 测试:
   - 15 个真实 MTG eBay 标题样本,验证 parse + confidence
   - 特别测试 foil/non-foil 区分
   - Secret Lair 测试

输出:
- diff 摘要
- 测试 accuracy(目标 >65%,MTG 本身难度高)
- 失败 case 分析
```

**验收**:给定 15 个真实 MTG eBay 标题,至少 10 个映射 confidence > 60 且方向正确。

---

### TASK-014: MTG signal + meta-aware prompt

```
给 Claude Code 的 prompt:

目标:MTG 的 signal 需要理解 "meta" 概念 —— 这是 MTG finance 的语言核心。

MTG signal 的主要驱动:
1. **Format meta shift**: Standard/Modern/Pioneer/Commander 某个 deck 崛起 
   -> 相关卡涨
2. **Ban announcement**: 每季度 banlist 更新,重磅禁牌会让卡崩或副牌崛起
3. **Reprint announcement**: 某张贵卡被宣布重印 -> 暴跌(或 "已被印了还会再印" 的
   心理)
4. **New set release**: 首周热度 -> 主推卡涨,一两周后回调

步骤:

1. MtgSignalContext dataclass:
   - 当前 Standard banlist 状态(可手工维护 JSON,每季度更新)
   - 已知 reprint schedule(Anthology / Masters sets 未来 3 个月)
   - 正在开始的 set releases
   
   这些数据 bootstrap 时手工填入 app/data/mtg_context.json,后续运营人员更新。

2. MtgPrompt (app/services/llm/prompts/mtg_prompt.py):
   - system_prompt 里强调 MTG finance 常用词汇:
     "spec"(speculative buy)、"reprint risk"、"meta share"、"foil multiplier"、
     "EDH staple"、"tier 1/2/3 deck"
   - user_prompt 组装 context 时带上:
     最近 7 天该卡所在 deck 的 meta share 变化(如有)、
     最近是否有相关 reprint 新闻、
     是否是 commander staple(EDHREC 数据,后续可接)

3. signal 生成:
   - 沿用 BREAKOUT/MOVE/WATCH/IDLE 架构
   - MTG-specific 阈值(在 TASK-005 的 THRESHOLDS 里填):
     - 现代卡波动本来大,breakout_pct_7d = 35
     - 但 reserved list(禁重印)卡波动小且单向,阈值更低,暂不细分
   - 加一个 trigger_type = REPRINT_ANNOUNCEMENT 的 signal 类型,
     由运营手工或从 news feed 触发(MVP 用手工)

4. 测试:用 3-5 张热门 MTG 卡(如 The One Ring, Sheoldred the Apocalypse)
   的历史价格数据,验证 signal 生成合理。

输出:
- MTG prompt 示例输出(给一个 signal,看 explanation 是否 MTG-native)
- 阈值配置
- 测试结果
```

**验收**:MTG signal 的 AI explanation 能自然用到至少 3 个 MTG-finance-native 术语。

---

## Phase 7 — 跨 TCG 信号 MVP(Claude Code Task #15-16)

### TASK-015: IP tagging 系统

```
给 Claude Code 的 prompt:

目标:给所有游戏的卡打上 "IP / franchise / character / theme" 标签,
为跨 TCG 信号做基础。

步骤:

1. 新建表 ip_tag:
   - id
   - asset_id (FK)
   - tag_type: enum (FRANCHISE, CHARACTER, THEME, ARTIST)
   - tag_value: str (如 "Godzilla", "Luffy", "anime", "Rebecca Guay")
   - confidence: float (0-1)
   - source: str ("llm" / "manual")

2. 创建 app/services/ip_tagging/tagger.py:
   
   def tag_asset(asset: Asset) -> list[IpTag]:
       # 构造 LLM prompt:
       prompt = f"""
       Given this trading card:
       Name: {asset.name}
       Game: {asset.game}
       Set: {asset.set_name}
       
       Extract any of:
       - FRANCHISE tags (Pokemon, Godzilla, Star Wars, MLP, Marvel, etc) — 
         use broad franchise names
       - CHARACTER tags (if the card represents a specific named character, 
         include the character's canonical name)
       - THEME tags (anime, kaiju, horror, nostalgia, 90s, etc) — high-level
       - ARTIST tag (if card artist is notable cross-game)
       
       Only include confident tags. Return JSON list of {{tag_type, tag_value, 
       confidence (0-1)}}.
       """
       # 调用 Anthropic (复用 LLM 抽象层)
       # 解析 JSON,存入 ip_tag 表

3. 批处理任务:
   - 每个 game 首次上线后,对所有 asset 跑一次 tag_asset
   - 后续新卡入库时自动跑
   - rate limit:每分钟不超过 60 张,避免 LLM 账单炸

4. 建立跨 game 的 tag 聚合视图:
   - GET /api/ip_tags/franchises 返回所有 FRANCHISE 跨多少游戏
   - 特别关注"至少 2 个游戏都有此 FRANCHISE 卡"的 tags,
     这些是跨 TCG 信号的候选

5. **初版只对 Promo / Crossover / Secret Lair 这类明显跨 IP 的卡打标签**,
   不要对每张卡都打 —— 基本 vanilla 卡(Pikachu、Goblin Guide)
   没有跨 IP 意义,只给 FRANCHISE="Pokemon"/"MTG" 这样的 native 标签。

6. 成本控制:
   - tag 只跑一次,结果永久存储
   - 估算:Pokemon 18k 卡 + YGO 13k + MTG 30k ≈ 60k 张,
     按 Claude Haiku 估算 ~$50-100 总成本,一次性

7. 测试:对 20 张已知跨 IP 卡(Godzilla MTG, Luffy OPTCG 等),
   验证 tag 正确识别。

输出:
- schema
- tagger 实现
- 20 张样本卡的 tag 结果
- 成本估算
```

**验收**:对明显跨 IP 的 20 张卡,至少 17 张能被正确识别 FRANCHISE。

---

### TASK-016: Cross-TCG Signal detector

```
给 Claude Code 的 prompt:

目标:用 IP tags 实现三类跨 TCG 信号(Franchise Move / Cultural Trigger / 
Meta Spillover),MVP 先做 Franchise Move。

步骤:

1. 创建 app/services/signal/cross_tcg/franchise_move.py:

   def detect_franchise_move(time_window_days=7) -> list[CrossTcgSignal]:
       """
       找出同一 FRANCHISE tag 在 2+ 个游戏内都触发了 MOVE/BREAKOUT 
       的情况。
       """
       # 1. 查询过去 N 天所有 MOVE/BREAKOUT signal
       recent_signals = Signal.query.filter(
           Signal.trigger_type.in_([PRICE_MOVE, PRICE_BREAKOUT]),
           Signal.created_at >= now() - timedelta(days=time_window_days)
       ).all()
       
       # 2. 按 FRANCHISE tag 分组
       franchise_buckets = defaultdict(list)
       for sig in recent_signals:
           for tag in sig.asset.ip_tags:
               if tag.tag_type == "FRANCHISE" and tag.confidence > 0.7:
                   franchise_buckets[tag.tag_value].append(sig)
       
       # 3. 找出跨 game 的情况
       cross_signals = []
       for franchise, sigs in franchise_buckets.items():
           games_involved = {s.asset.game for s in sigs}
           if len(games_involved) >= 2:
               # native 游戏不算(Pokemon 在 Pokemon 游戏里涨不算 cross)
               non_native_games = [g for g in games_involved 
                                    if not is_native(franchise, g)]
               if len(non_native_games) >= 2 or \
                  (len(non_native_games) >= 1 and franchise in CROSS_IP_FRANCHISES):
                   cross_signals.append(CrossTcgSignal(
                       franchise=franchise,
                       games=list(games_involved),
                       signals=sigs,
                       confidence=compute_cross_confidence(sigs)
                   ))
       
       return cross_signals

2. is_native(franchise, game) 逻辑:
   - franchise="Pokemon" 且 game=POKEMON -> True (不算 cross)
   - franchise="Yu-Gi-Oh" 且 game=YUGIOH -> True
   - 其他 -> False

3. CROSS_IP_FRANCHISES 白名单:已知经常跨 IP 的 franchise
   ["Godzilla", "Star Wars", "Marvel", "DC", "Stranger Things", 
    "Fortnite", "One Piece"(作为 IP,不是 OPTCG 游戏)]

4. compute_cross_confidence:
   - base = average(signals.confidence)
   - 如果 games_involved >= 3: bonus + 15
   - 如果所有 signal 都在同 24h: bonus + 10
   - cap at 95

5. 持久化:
   - 新表 cross_tcg_signal
     (id, franchise, games_json, signal_ids_json, confidence, created_at)
   - 每次 detect 跑完,新的 cross signal 入库

6. API endpoint(Pro-only):
   - GET /api/cross_tcg_signals?days=7
   - 返回近期 cross signals,按 confidence 排序

7. Web UI:
   - 在 Signals 页顶部新增 "🌐 Cross-TCG Movers" section(Pro gated)
   - 每个 cross signal 卡片显示:franchise + 涉及 games + 
     icon stack + confidence + "View signals" 展开

8. 测试:
   - 构造 mock 数据:Godzilla 在 MTG + OPTCG 同日触发 MOVE,
     验证 detector 捕获
   - 构造反例:Pokemon Charizard 在 Pokemon 涨,不应触发 cross signal
   - 边界:单 game 多张卡涨不触发 cross

输出:
- detector 实现
- schema
- Pro-gated endpoint
- UI 截图
- 测试结果
```

**验收**:造出 Godzilla 跨 MTG+OPTCG mock 数据后,UI 上能看到 "🌐 Godzilla — 
detected in MTG, One Piece TCG".

---

## 总执行顺序速查

```
Week 1     TASK-000 (audit)
Week 2     TASK-001 (game field) + TASK-002 (data client abstract)
Week 3     TASK-003 (mapping abstract) + TASK-004 (prompt abstract) + 
           TASK-005 (thresholds)
Week 4     TASK-006 (ebay game-aware) + TASK-007 (API game param)
Week 5     TASK-008 (GameSelector UI) + TASK-009 (YugiohClient)
Week 6     TASK-010 (YGO mapping + banlist signal) + TASK-011 (YGO go-live)
Week 7     TASK-012 (ScryfallClient + compliance)
Week 8     TASK-013 (MTG mapping)
Week 9     TASK-014 (MTG signal) + TASK-015 (IP tagging)
Week 10    TASK-016 (cross-TCG detector) + OPTCG client (类似 TASK-009)
Week 11    Lorcana MVP + diagnostics / KPI
Week 12    Full end-to-end validation + 回顾
```

## 给 Claude Code 的通用提示

每个 task 丢给 Claude Code 时,建议这样包装 prompt:

```
你是 Flashcard Planet 的一位熟悉架构的工程师。请阅读 CLAUDE.md (如果存在) 
了解项目约定,然后执行以下任务:

[粘贴上面的 TASK 内容]

执行要求:
1. 先用 Read + Grep 了解现有代码结构,再写任何代码
2. 遇到和假设不符的地方(如路径不对、已有类名冲突),先报告再修改
3. 每改一组相关文件就跑一次相关测试,不要一次改完才跑
4. Commit 以 Conventional Commits 风格:"feat(game): add game enum and ..."
5. 如果发现某个改动会破坏现有行为超出预期,停下来问我
6. 最后给一个简短的 summary:改了什么、新增多少测试、有无回归风险
```
