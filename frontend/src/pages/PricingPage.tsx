import { useState } from 'react'
import NavBar from '../components/NavBar'
import { useUser } from '../hooks/useUser'

type Lang = 'en' | 'zh'

const LOCALES = {
  en: {
    heroTitle: 'Signal intelligence for TCG investors.',
    heroSub: 'Start free. Upgrade when the edge matters.',
    freeName: 'Free',
    freePrice: '$0',
    plusName: 'Plus',
    plusPrice: '$9.99',
    plusPriceUnit: '/month',
    plusFounders: 'Founders: first 100 subscribers lock in at $7/mo for life',
    proName: 'Pro',
    proPrice: '$30',
    proPriceUnit: '/month',
    proFounders: 'Founders: first 50 subscribers lock in at $20/mo for life',
    popularBadge: 'POPULAR',
    currentPlan: 'Current plan',
    startTrial: 'Start 14-day free trial →',
    upgradePro: 'Upgrade to Pro →',
    loading: 'Loading…',
    faqTitle: 'Common questions',
    freeFeatures: [
      'IDLE & WATCH signals (delayed 24h)',
      '1 game (Pokémon)',
      '1 watchlist slot',
      'Card detail pages with full price history',
    ],
    plusFeatures: [
      'Everything in Free',
      'Real-time BREAKOUT & MOVE signals',
      'All 3 games (Pokémon, YGO, One Piece)',
      'Discord DMs on every signal',
      'Unlimited watchlist',
      '1-sentence AI signal explanation',
      '14-day free trial — no card required',
    ],
    proFeatures: [
      'Everything in Plus',
      'Full AI analysis — drivers, risks, thesis',
      'Japanese lead signals (4–8 week advance)',
      'Pre-grading ROI calculator',
      'Portfolio analytics & P&L tracking',
      'API access for personal automation',
    ],
    faq: [
      {
        q: 'Is there a free trial?',
        a: '14-day free trial of full Plus access, no credit card required. When your trial ends you drop to the Free tier automatically. Upgrade any time during or after.',
      },
      {
        q: 'What are the founders prices?',
        a: 'The first 100 Plus subscribers lock in at $7/month for life. The first 50 Pro subscribers lock in at $20/month for life. Founders pricing is permanent — it never expires.',
      },
      {
        q: 'What happens if I cancel?',
        a: 'You keep access until the end of your billing period. Your watchlist and settings are saved for 90 days — resubscribe and everything is exactly where you left it.',
      },
      {
        q: 'What currencies do you accept?',
        a: 'We bill in USD. LemonSqueezy (our payment provider) automatically shows your local currency at checkout.',
      },
    ],
  },
  zh: {
    heroTitle: '不只是价格追踪。跨 TCG 的市场智能。',
    heroSub: '宝可梦 · 万智牌 · 游戏王 · 航海王\n一个信号源，看到别家看不到的跨游戏规律。',
    freeName: '免费版',
    freePrice: '¥0',
    plusName: '进阶版',
    plusPrice: '¥88',
    plusPriceUnit: '/月',
    plusFounders: '创始人优惠：前 100 位订阅者终身锁定 ¥51/月',
    proName: '专业版',
    proPrice: '¥218',
    proPriceUnit: '/月',
    proFounders: '创始人优惠：前 50 位订阅者终身锁定 ¥145/月',
    popularBadge: '热门',
    currentPlan: '当前方案',
    startTrial: '开始 14 天免费试用 →',
    upgradePro: '升级至专业版 →',
    loading: '加载中…',
    faqTitle: '常见问题',
    freeFeatures: [
      'IDLE & WATCH 信号（延迟 24 小时）',
      '1 款游戏（宝可梦）',
      '1 个关注列表位',
      '卡牌详情页及完整价格历史',
    ],
    plusFeatures: [
      '含免费版全部功能',
      '实时 BREAKOUT & MOVE 信号',
      '全部 3 款游戏（宝可梦、游戏王、航海王）',
      '每个信号推送 Discord 私信',
      '无限制关注列表',
      'AI 单句信号解释',
      '14 天免费试用，无需绑卡',
    ],
    proFeatures: [
      '含进阶版全部功能',
      '完整 AI 分析——驱动因素、风险与投资逻辑',
      '日版超前信号（提前 4–8 周）',
      '评级前 ROI 计算器',
      '持仓分析与盈亏追踪',
      'API 接口（个人自动化）',
    ],
    faq: [
      {
        q: '有免费试用吗？',
        a: '进阶版有 14 天全功能免费试用，无需绑定信用卡。试用结束后自动降至免费版，随时可升级。',
      },
      {
        q: '创始人价格是什么？',
        a: '前 100 名进阶版订阅者终身锁定 ¥51/月。前 50 名专业版订阅者终身锁定 ¥145/月。创始人价格永久有效。',
      },
      {
        q: '取消订阅会怎样？',
        a: '账单周期结束前保持访问权。关注列表和设置保留 90 天——重新订阅后一切都在原位。',
      },
      {
        q: '支持哪些支付方式？',
        a: '我们以美元计费。LemonSqueezy（我们的支付商）在结账时自动显示您的本地货币。',
      },
    ],
  },
} as const

export default function PricingPage() {
  const { tier } = useUser()
  const [loading, setLoading] = useState(false)
  const [lang, setLang] = useState<Lang>('en')

  const t = LOCALES[lang]

  async function handleStartTrial() {
    setLoading(true)
    try {
      const resp = await fetch('/api/v1/trial/start', {
        method: 'POST',
        credentials: 'include',
      })
      if (!resp.ok) {
        window.location.href = '/login'
        return
      }
      const data = await resp.json()
      if (data.status === 'started') {
        window.location.href = '/market'
      } else {
        await handleCheckout('plus')
      }
    } finally {
      setLoading(false)
    }
  }

  async function handleCheckout(variant: 'plus' | 'pro') {
    const resp = await fetch(`/api/v1/account/checkout-url?variant=${variant}`, {
      credentials: 'include',
    })
    if (!resp.ok) {
      window.location.href = '/?upgrade=1'
      return
    }
    const { checkout_url } = await resp.json()
    window.location.href = checkout_url
  }

  const isFree = !tier || tier === 'free'
  const isPlus = tier === 'plus'
  const isPro = tier === 'pro'

  return (
    <div>
      <NavBar />
      <div className="page-content" style={{ maxWidth: 940, margin: '0 auto', padding: '40px 24px' }}>

        {/* Language toggle */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
          <button
            onClick={() => setLang(lang === 'en' ? 'zh' : 'en')}
            style={{
              background: 'none',
              border: '1px solid var(--border)',
              borderRadius: 4,
              padding: '4px 10px',
              fontSize: 12,
              cursor: 'pointer',
              color: 'var(--text-secondary)',
            }}
          >
            {lang === 'en' ? '中文' : 'EN'}
          </button>
        </div>

        {/* Hero */}
        <div style={{ textAlign: 'center', marginBottom: 48 }}>
          <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 36, fontWeight: 700, marginBottom: 12 }}>
            {t.heroTitle}
          </h1>
          <p style={{ fontSize: 16, color: 'var(--text-secondary)', whiteSpace: 'pre-line' }}>
            {t.heroSub}
          </p>
        </div>

        {/* Plan cards — 3 column */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 20, marginBottom: 48 }}>

          {/* Free */}
          <div className="surface" style={{ padding: 24 }}>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: 20, fontWeight: 700, marginBottom: 4 }}>
              {t.freeName}
            </div>
            <div style={{ fontSize: 28, fontWeight: 700, marginBottom: 20 }}>{t.freePrice}</div>
            <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 24px', display: 'flex', flexDirection: 'column', gap: 10 }}>
              {t.freeFeatures.map(f => (
                <li key={f} style={{ display: 'flex', gap: 8, fontSize: 13, color: 'var(--text-secondary)' }}>
                  <span style={{ color: 'var(--breakout)', flexShrink: 0 }}>✓</span>
                  {f}
                </li>
              ))}
            </ul>
            {isFree ? (
              <div
                className="btn btn-ghost"
                style={{ width: '100%', justifyContent: 'center', cursor: 'default' }}
              >
                {t.currentPlan}
              </div>
            ) : null}
          </div>

          {/* Plus — highlighted */}
          <div
            className="surface"
            style={{ padding: 24, border: '1px solid var(--gold)', boxShadow: '0 0 32px var(--gold-glow)' }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 20, fontWeight: 700 }}>{t.plusName}</div>
              <span style={{ fontSize: 11, background: 'var(--gold)', color: '#000', padding: '2px 8px', borderRadius: 4, fontWeight: 700 }}>
                {t.popularBadge}
              </span>
            </div>
            <div style={{ marginBottom: 2 }}>
              <span style={{ fontSize: 28, fontWeight: 700 }}>{t.plusPrice}</span>
              <span style={{ fontSize: 13, color: 'var(--text-muted)', marginLeft: 4 }}>{t.plusPriceUnit}</span>
            </div>
            <div style={{ fontSize: 12, color: 'var(--gold)', marginBottom: 20 }}>
              {t.plusFounders}
            </div>
            <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 24px', display: 'flex', flexDirection: 'column', gap: 10 }}>
              {t.plusFeatures.map(f => (
                <li key={f} style={{ display: 'flex', gap: 8, fontSize: 13 }}>
                  <span style={{ color: 'var(--gold)', flexShrink: 0 }}>✓</span>
                  {f}
                </li>
              ))}
            </ul>
            {isPlus ? (
              <div
                className="btn btn-ghost"
                style={{ width: '100%', justifyContent: 'center', cursor: 'default' }}
              >
                {t.currentPlan}
              </div>
            ) : isPro ? null : (
              <button
                className="btn btn-primary"
                style={{ width: '100%', justifyContent: 'center' }}
                disabled={loading}
                onClick={handleStartTrial}
              >
                {loading ? t.loading : t.startTrial}
              </button>
            )}
          </div>

          {/* Pro */}
          <div className="surface" style={{ padding: 24 }}>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: 20, fontWeight: 700, marginBottom: 4 }}>
              {t.proName}
            </div>
            <div style={{ marginBottom: 2 }}>
              <span style={{ fontSize: 28, fontWeight: 700 }}>{t.proPrice}</span>
              <span style={{ fontSize: 13, color: 'var(--text-muted)', marginLeft: 4 }}>{t.proPriceUnit}</span>
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 20 }}>
              {t.proFounders}
            </div>
            <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 24px', display: 'flex', flexDirection: 'column', gap: 10 }}>
              {t.proFeatures.map(f => (
                <li key={f} style={{ display: 'flex', gap: 8, fontSize: 13, color: 'var(--text-secondary)' }}>
                  <span style={{ color: 'var(--breakout)', flexShrink: 0 }}>✓</span>
                  {f}
                </li>
              ))}
            </ul>
            {isPro ? (
              <div
                className="btn btn-ghost"
                style={{ width: '100%', justifyContent: 'center', cursor: 'default' }}
              >
                {t.currentPlan}
              </div>
            ) : (
              <button
                className="btn btn-ghost"
                style={{ width: '100%', justifyContent: 'center' }}
                disabled={loading}
                onClick={() => handleCheckout('pro')}
              >
                {loading ? t.loading : t.upgradePro}
              </button>
            )}
          </div>
        </div>

        {/* FAQ */}
        <div style={{ maxWidth: 600, margin: '0 auto' }}>
          <h2
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 20,
              fontWeight: 700,
              marginBottom: 24,
            }}
          >
            {t.faqTitle}
          </h2>
          {t.faq.map(({ q, a }) => (
            <div key={q} style={{ marginBottom: 28 }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>{q}</div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>{a}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
