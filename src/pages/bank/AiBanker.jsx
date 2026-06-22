/**
 * AiBanker — AI Financial Assistant, ChatGPT/Claude-style.
 *
 * The PRIMARY behavioural-collection surface: a true conversational chat (not a
 * dashboard widget). The conversation area dominates (~85%); behavioural metrics
 * are compact pills (~15%). Keystrokes feed the global Entropy Prime collectors
 * automatically. Responses are canned (bankMock.aiAnswer) — no real LLM — but
 * reference live balances from BankContext.
 *
 * Features: right/left message bubbles · smooth auto-scroll · drag-resizable
 * conversation (250px–80vh) · auto-growing input (1–8 lines, Enter=send,
 * Shift+Enter=newline) · suggested-prompt chips · animated typing indicator.
 */

import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { useAuth } from '../../context/AuthContext'
import { useTrust } from '../../context/TrustContext'
import { useBank } from '../../context/BankContext'
import { aiAnswer } from '../../data/bankMock'

const STORE = 'ep_ai_convos'
const SUGGESTIONS = [
  'Can I afford a bike?',
  'How much did I spend this month?',
  'Show my investments',
  'Food expenses',
  'Savings analysis',
]
const greeting = () => ({ role: 'ai', text: "Hi 👋 I'm your AI Banker. Ask me anything about your money — spending, savings, investments, or whether you can afford something. The more you chat, the better Entropy Prime keeps verifying it's really you." })
const newConvo = () => ({ id: `c_${Date.now()}`, startedAt: Date.now(), updatedAt: Date.now(), messages: [greeting()] })
function loadConvos() {
  try { const r = localStorage.getItem(STORE); if (r) { const c = JSON.parse(r); if (Array.isArray(c) && c.length) return c } } catch { /* ignore */ }
  return [newConvo()]
}

export default function AiBanker() {
  const { profileStats } = useAuth()
  const { confidence, color } = useTrust()
  const { totals } = useBank()

  const [convos, setConvos] = useState(loadConvos)
  const [activeId, setActiveId] = useState(() => convos[0].id)
  const [input, setInput] = useState('')
  const [typing, setTyping] = useState(false)
  const [chatH, setChatH] = useState(Math.min(540, Math.round(window.innerHeight * 0.58)))

  const scrollRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => { try { localStorage.setItem(STORE, JSON.stringify(convos.slice(0, 30))) } catch { /* ignore */ } }, [convos])

  const active = useMemo(() => convos.find(c => c.id === activeId) || convos[0], [convos, activeId])
  const messages = active.messages
  const samples = profileStats?.sampleCount ?? 0

  const scrollToBottom = useCallback((smooth = true) => {
    const el = scrollRef.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
  }, [])
  useEffect(() => { scrollToBottom(false) }, [activeId]) // eslint-disable-line
  useEffect(() => { scrollToBottom() }, [messages.length, typing]) // eslint-disable-line

  // Auto-grow composer: 1 line → ~8 lines.
  const autoGrow = useCallback(() => {
    const el = inputRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(Math.max(el.scrollHeight, 46), 196) + 'px'
  }, [])

  // Drag-resize the conversation area (250px … 80vh).
  const startResize = useCallback((e) => {
    e.preventDefault()
    const startY = e.clientY
    const startH = scrollRef.current ? scrollRef.current.getBoundingClientRect().height : chatH
    const maxH = Math.round(window.innerHeight * 0.8)
    const onMove = (ev) => setChatH(Math.max(250, Math.min(maxH, startH + (ev.clientY - startY))))
    const onUp = () => { window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp); document.body.style.userSelect = '' }
    document.body.style.userSelect = 'none'
    window.addEventListener('mousemove', onMove); window.addEventListener('mouseup', onUp)
  }, [chatH])

  const pushMessage = (convoId, msg) =>
    setConvos(prev => prev.map(c => c.id === convoId ? { ...c, updatedAt: Date.now(), messages: [...c.messages, msg] } : c))

  const send = (text) => {
    const q = (text ?? input).trim()
    if (!q) return
    const id = active.id
    pushMessage(id, { role: 'me', text: q })
    setInput('')
    requestAnimationFrame(() => { if (inputRef.current) inputRef.current.style.height = '46px' })
    setTyping(true)
    setTimeout(() => {
      setTyping(false)
      pushMessage(id, { role: 'ai', text: aiAnswer(q, { net: totals.net, monthSpend: totals.monthSpend }) })
    }, 800)
  }
  const onKey = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }
  const startNewChat = () => { const c = newConvo(); setConvos(prev => [c, ...prev]); setActiveId(c.id); setInput('') }

  const onlyGreeting = messages.length === 1

  return (
    <div style={st.page}>
      {/* ── Header + compact behavioural pills ─────────────────────────────── */}
      <div style={st.header}>
        <div>
          <div style={st.title}>AI Banker</div>
          <div style={st.sub}>Conversational assistant · continuously verifying it's you</div>
        </div>
        <div style={st.pills}>
          <span style={st.pill}><span style={{ ...st.dot, background: color }} /> Confidence <b style={{ color }}>{confidence}%</b></span>
          <span style={st.pill}>🧠 Samples <b>{samples}</b></span>
          <span style={st.pill}>💬 Messages <b>{messages.length}</b></span>
          <button style={st.newBtn} onClick={startNewChat}>+ New</button>
        </div>
      </div>

      {/* ── Conversation area (dominant, resizable, scrollable) ────────────── */}
      <div ref={scrollRef} style={{ ...st.conversation, height: chatH }}>
        <div style={st.thread}>
          {messages.map((m, i) => (
            <Bubble key={i} role={m.role} text={m.text} />
          ))}

          {/* Suggested prompts under the welcome message */}
          {onlyGreeting && (
            <div style={st.chips}>
              {SUGGESTIONS.map(q => (
                <button key={q} style={st.chip} onClick={() => send(q)}>{q}</button>
              ))}
            </div>
          )}

          {typing && (
            <div style={{ ...st.row, justifyContent: 'flex-start' }}>
              <div style={{ ...st.bubble, ...st.bubbleAi }}>
                <div style={st.who}>AI Banker is thinking</div>
                <div style={st.typing}>
                  <span style={st.tdot} /><span style={{ ...st.tdot, animationDelay: '.2s' }} /><span style={{ ...st.tdot, animationDelay: '.4s' }} />
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Drag handle ────────────────────────────────────────────────────── */}
      <div onMouseDown={startResize} title="Drag to resize the conversation" style={st.handle}>
        <div style={st.grip} />
      </div>

      {/* ── Input area ─────────────────────────────────────────────────────── */}
      <div style={st.inputBar}>
        <textarea
          ref={inputRef}
          value={input}
          onChange={e => { setInput(e.target.value); autoGrow() }}
          onKeyDown={onKey}
          rows={1}
          placeholder="Message your AI Banker…  (Enter to send · Shift+Enter for a new line)"
          style={st.textarea}
        />
        <button onClick={() => send()} disabled={!input.trim()} style={{ ...st.send, opacity: input.trim() ? 1 : 0.5 }}>Send ➤</button>
      </div>
      <div style={st.foot}>Every message is a natural behavioural sample — Entropy Prime measures your rhythm as you chat.</div>
    </div>
  )
}

function Bubble({ role, text }) {
  const me = role === 'me'
  return (
    <div style={{ ...st.row, justifyContent: me ? 'flex-end' : 'flex-start' }}>
      <div style={{ ...st.bubble, ...(me ? st.bubbleMe : st.bubbleAi) }}>
        <div style={st.who}>{me ? 'You' : 'AI Banker'}</div>
        <div style={st.msgText}>{text}</div>
      </div>
    </div>
  )
}

const st = {
  page: { display: 'flex', flexDirection: 'column', gap: 10, maxWidth: 920, margin: '0 auto' },
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', flexWrap: 'wrap', gap: 12 },
  title: { fontSize: 20, fontWeight: 700, color: 'var(--text)' },
  sub: { fontSize: 12.5, color: 'var(--text-2)', marginTop: 2 },
  pills: { display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' },
  pill: { display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--text-2)', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 999, padding: '5px 11px' },
  dot: { width: 8, height: 8, borderRadius: '50%', display: 'inline-block' },
  newBtn: { fontSize: 12, color: 'var(--text)', background: 'var(--surface-3)', border: '1px solid var(--border)', borderRadius: 999, padding: '6px 12px', cursor: 'pointer' },

  conversation: { overflowY: 'auto', minHeight: 250, maxHeight: '80vh', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 14, scrollBehavior: 'smooth' },
  thread: { display: 'flex', flexDirection: 'column', gap: 14, padding: '22px 20px' },
  row: { display: 'flex', width: '100%' },
  bubble: { maxWidth: '78%', padding: '11px 15px', borderRadius: 16, fontSize: 14.5, lineHeight: 1.55 },
  bubbleMe: { background: 'var(--accent)', color: '#04121d', borderBottomRightRadius: 5 },
  bubbleAi: { background: 'var(--surface-2)', color: 'var(--text)', border: '1px solid var(--border)', borderBottomLeftRadius: 5 },
  who: { fontSize: 10.5, opacity: 0.7, marginBottom: 3, fontWeight: 600, letterSpacing: 0.3 },
  msgText: { whiteSpace: 'pre-wrap' },
  typing: { display: 'flex', gap: 5, marginTop: 4 },
  tdot: { width: 7, height: 7, borderRadius: '50%', background: 'var(--text-3)', display: 'inline-block', animation: 'pulse 1s infinite' },

  chips: { display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 2, marginLeft: 2 },
  chip: { fontSize: 13, color: 'var(--text)', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 999, padding: '8px 14px', cursor: 'pointer' },

  handle: { height: 16, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'ns-resize', userSelect: 'none' },
  grip: { width: 46, height: 4, borderRadius: 99, background: 'var(--border)' },

  inputBar: { display: 'flex', alignItems: 'flex-end', gap: 10, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 14, padding: 10 },
  textarea: { flex: 1, resize: 'none', height: 46, minHeight: 46, maxHeight: 196, border: 'none', outline: 'none', background: 'transparent', color: 'var(--text)', fontSize: 14.5, lineHeight: 1.5, fontFamily: 'inherit', padding: '11px 12px' },
  send: { flexShrink: 0, padding: '11px 20px', background: 'var(--accent)', color: '#04121d', border: 'none', borderRadius: 10, fontSize: 14, fontWeight: 700, cursor: 'pointer' },
  foot: { fontSize: 11.5, color: 'var(--text-3)', textAlign: 'center', padding: '2px 0 4px' },
}
