/**
 * Journal — Money Journal / Daily Reflection.
 * A long-form writing surface: pick a reflection prompt, write freely, save.
 * Encourages 100–300 word entries that continuously feed the behavioral engine.
 */

import { useState } from 'react'
import { Card, Button, TextArea, Badge } from '../../components/ui'
import { useBank } from '../../context/BankContext'
import { journalPrompts } from '../../data/bankMock'
import s from './bank.module.css'

const countWords = (t) => (t.trim() ? t.trim().split(/\s+/).filter(Boolean).length : 0)

export default function Journal() {
  const { journal: entries, addJournalEntry } = useBank()
  const [prompt, setPrompt] = useState(journalPrompts[0])
  const [text, setText] = useState('')

  const words = countWords(text)
  const save = () => {
    if (words < 3) return
    addJournalEntry({ prompt, body: text, words })
    setText('')
  }

  return (
    <div className={s.journalGrid}>
      <Card title="Today’s Reflection" sub="Write naturally — there are no wrong answers">
        <div className={s.promptPick}>
          {journalPrompts.map(p => (
            <button key={p} className={s.chip} onClick={() => setPrompt(p)}
              style={p === prompt ? { borderColor: 'var(--accent)', color: 'var(--text)' } : undefined}>
              {p.length > 42 ? p.slice(0, 42) + '…' : p}
            </button>
          ))}
        </div>

        <div style={{ fontFamily: 'var(--display)', fontSize: 18, fontWeight: 700, color: 'var(--text)', margin: '6px 0 12px' }}>
          {prompt}
        </div>

        <TextArea
          value={text}
          onChange={e => setText(e.target.value)}
          placeholder="Start writing your thoughts…"
          style={{ minHeight: 220 }}
        />

        <div className={s.saveBar} style={{ marginTop: 14 }}>
          <span className={s.wordTag}>{words} words {words >= 100 && '· great depth ✓'}</span>
          <Button onClick={save} disabled={words < 3}>Save entry</Button>
        </div>
      </Card>

      <Card title="Past Entries" action={<Badge tone="neutral">{entries.length}</Badge>}>
        {entries.length === 0 && (
          <div style={{ fontSize: 13, color: 'var(--text-3)', padding: '20px 0', textAlign: 'center' }}>
            No entries yet. Your reflections will appear here.
          </div>
        )}
        {entries.map(e => (
          <div key={e.id} className={s.entry}>
            <div className={s.entryDate}>{new Date(e.at).toLocaleString('en-IN')}</div>
            <div className={s.entryPrompt}>{e.prompt} {e.auto && <Badge tone="ok">auto</Badge>}</div>
            <div className={s.entryBody}>{e.body}</div>
          </div>
        ))}
      </Card>
    </div>
  )
}
