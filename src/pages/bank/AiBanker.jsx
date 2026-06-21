/**
 * AiBanker — AI Financial Assistant ("ChatGPT for banking").
 * The PRIMARY behavioral-collection surface. Premium chat experience:
 * dedicated scroll viewport + glass scrollbar, jump-to-latest, scroll-position
 * rail, auto-scroll, sticky composer + sticky behavioral metrics, conversation
 * history (Today / Yesterday / This Week), and a resizable composer (120–600px).
 *
 * Responses are canned (bankMock.aiAnswer) — no real LLM — but reference LIVE
 * balances from BankContext, and every keystroke feeds the Entropy Prime
 * collectors (PHASE 1/4).
 */

import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { Card, Button, Badge } from '../../components/ui'
import { useAuth } from '../../context/AuthContext'
import { useTrust } from '../../context/TrustContext'
import { useBank } from '../../context/BankContext'
import { aiAnswer, aiSuggestions } from '../../data/bankMock'
import s from './bank.module.css'

const countWords = (t) => (t.trim() ? t.trim().split(/\s+/).filter(Boolean).length : 0)
const STORE = 'ep_ai_convos'
const greeting = () => ({ role: 'ai', text: 'Hi Parikshith 👋 I’m your AI Banker. Ask me about your spending, savings, investments, or whether you can afford something. Type as much as you like.' })
const newConvo = () => ({ id: `c_${Date.now()}`, title: 'New chat', startedAt: Date.now(), updatedAt: Date.now(), messages: [greeting()] })

function loadConvos() {
  try { const r = localStorage.getItem(STORE); if (r) { const c = JSON.parse(r); if (Array.isArray(c) && c.length) return c } } catch { /* ignore */ }
  return [newConvo()]
}

const RAIL = [0, 25, 50, 75, 100]
function bucket(ts) {
  const today = new Date().setHours(0, 0, 0, 0)
  if (ts >= today) return 'Today'
  if (ts >= today - 86400000) return 'Yesterday'
  if (ts >= today - 6 * 86400000) return 'This Week'
  return 'Earlier'
}

export default function AiBanker() {
  const { liveTheta, profileStats } = useAuth()
  const { confidence, color } = useTrust()
  const { totals } = useBank()

  const [convos, setConvos] = useState(loadConvos)
  const [activeId, setActiveId] = useState(() => convos[0].id)
  const [input, setInput] = useState('')
  const [typing, setTyping] = useState(false)
  const [scrollPct, setScrollPct] = useState(1)
  const [atBottom, setAtBottom] = useState(true)

  const scrollRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => { try { localStorage.setItem(STORE, JSON.stringify(convos.slice(0, 30))) } catch { /* ignore */ } }, [convos])

  const active = useMemo(() => convos.find(c => c.id === activeId) || convos[0], [convos, activeId])
  const messages = active.messages

  const scrollToBottom = useCallback((smooth = true) => {
    const el = scrollRef.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
  }, [])

  const onScroll = () => {
    const el = scrollRef.current
    if (!el) return
    const max = el.scrollHeight - el.clientHeight
    const pct = max <= 0 ? 1 : el.scrollTop / max
    setScrollPct(pct)
    setAtBottom(pct > 0.96 || max <= 0)
  }

  // Auto-scroll when the active conversation changes or a message lands.
  useEffect(() => { scrollToBottom(false); setAtBottom(true) }, [activeId]) // eslint-disable-line
  useEffect(() => { if (atBottom || typing) scrollToBottom() }, [messages.length, typing]) // eslint-disable-line

  const autoGrow = useCallback(() => {
    const el = inputRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(Math.max(el.scrollHeight, 120), 600) + 'px'
  }, [])

  const pushMessage = (convoId, msg, titleFrom) =>
    setConvos(prev => prev.map(c => c.id === convoId
      ? { ...c, updatedAt: Date.now(), messages: [...c.messages, msg], title: titleFrom && c.title === 'New chat' ? titleFrom.slice(0, 38) : c.title }
      : c))

  const send = (text) => {
    const q = (text ?? input).trim()
    if (!q) return
    const id = active.id
    pushMessage(id, { role: 'me', text: q }, q)
    setInput('')
    requestAnimationFrame(() => { if (inputRef.current) inputRef.current.style.height = '120px' })
    setTyping(true)
    scrollToBottom()
    setTimeout(() => {
      setTyping(false)
      pushMessage(id, { role: 'ai', text: aiAnswer(q, { net: totals.net, monthSpend: totals.monthSpend }) })
    }, 750)
  }
  const onKey = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }

  const startNewChat = () => { const c = newConvo(); setConvos(prev => [c, ...prev]); setActiveId(c.id); setInput('') }

  // group conversations for the history panel
  const groups = useMemo(() => {
    const order = ['Today', 'Yesterday', 'This Week', 'Earlier']
    const g = {}
    ;[...convos].sort((a, b) => b.updatedAt - a.updatedAt).forEach(c => { (g[bucket(c.updatedAt)] ||= []).push(c) })
    return order.filter(k => g[k]?.length).map(k => [k, g[k]])
  }, [convos])

  const words = countWords(input)
  const chars = input.length
  const typingConf = Math.round((liveTheta ?? 0) * 100)
  const samples = profileStats?.sampleCount ?? 0
  const confColor = (v) => (v > 70 ? 'var(--accent)' : v > 40 ? 'var(--gold)' : 'var(--danger)')

  return (
    <div className={s.chatWrap}>
      {/* ── Conversation history ──────────────────────────────────────────── */}
      <div className={s.convoPanel}>
        <button className={s.newChatBtn} onClick={startNewChat}>+ New chat</button>
        {groups.map(([label, items]) => (
          <div key={label}>
            <div className={s.convoGroupLabel}>{label}</div>
            {items.map(c => (
              <button key={c.id} className={`${s.convoItem} ${c.id === activeId ? s.convoItemActive : ''}`} onClick={() => setActiveId(c.id)}>
                {c.title}
              </button>
            ))}
          </div>
        ))}
      </div>

      {/* ── Chat column ───────────────────────────────────────────────────── */}
      <div className={s.chatCol}>
        <Card pad={false} className={s.chatCard}>
          <div className={s.behaviorHead}>
            <div className={s.bChip}><span className={s.bChipLabel}>Conversation</span><span className={s.bChipVal}>{messages.length} msgs</span></div>
            <div className={s.bChip}><span className={s.bChipLabel}>Behavior samples</span><span className={s.bChipVal}>{samples}</span></div>
            <div className={s.bChip}><span className={s.bChipLabel}>Profile confidence</span><span className={s.bChipVal} style={{ color }}>{confidence}%</span></div>
          </div>

          <div className={s.chatScroll} ref={scrollRef} onScroll={onScroll}>
            {messages.map((m, i) => (
              <div key={i} className={`${s.msg} ${m.role === 'me' ? s.msgMe : s.msgAi}`}>
                <div className={s.msgRole}>{m.role === 'me' ? 'You' : 'AI Banker'}</div>
                {m.text}
              </div>
            ))}
            {typing && (
              <div className={`${s.msg} ${s.msgAi} ${s.typing}`}>
                <span className={s.typingDot} /><span className={s.typingDot} style={{ animationDelay: '.2s' }} /><span className={s.typingDot} style={{ animationDelay: '.4s' }} />
              </div>
            )}
          </div>

          {/* scroll position rail */}
          <div className={s.scrollRail}>
            <div className={s.railTrack} />
            {RAIL.map(m => <span key={m} className={s.railMark}>{m}</span>)}
            <span className={s.railDot} style={{ top: `${10 + scrollPct * 80}%` }} />
          </div>

          <div className={s.composer}>
            <div className={s.composerMeta}>
              <span className={s.metaItem}>Words: <b>{words}</b></span>
              <span className={s.metaItem}>Characters: <b>{chars}</b></span>
              <span className={s.metaItem}><span className={s.metaDot} style={{ background: confColor(typingConf) }} />Typing confidence <b>{typingConf}%</b></span>
              <span className={s.metaItem}>Behavior samples <b>{samples}</b></span>
            </div>
            <div className={s.chatInputBar}>
              <textarea
                ref={inputRef}
                className={s.chatInput}
                value={input}
                onChange={e => { setInput(e.target.value); autoGrow() }}
                onKeyDown={onKey}
                placeholder="Ask about your money — spending, goals, investments, future purchases… (Enter to send, Shift+Enter for a new line). Drag the corner to resize."
              />
              <div className={s.sendCol}><Button onClick={() => send()} disabled={!input.trim()}>Send ➤</Button></div>
            </div>
          </div>
        </Card>

        {!atBottom && (
          <button className={s.jumpBtn} onClick={() => scrollToBottom()}>↓ Jump to Latest</button>
        )}
      </div>

      {/* ── Side panel ────────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-5)' }}>
        <Card title="Try asking" sub="Tap to ask, or type your own">
          <div className={s.chips}>
            {aiSuggestions.map(q => <button key={q} className={s.chip} onClick={() => send(q)}>{q}</button>)}
          </div>
        </Card>
        <Card title="Why this page exists" action={<Badge tone="ok" dot>Live</Badge>}>
          <p style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.6 }}>
            Every message you type here is a natural behavioral sample. Entropy Prime measures your
            rhythm continuously — so even a casual chat keeps verifying it’s really you.
          </p>
        </Card>
      </div>
    </div>
  )
}
