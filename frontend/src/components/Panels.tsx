import { useEffect, useRef, useState } from 'react'
import { AGENTS, AGENT_BY_NAME, HUMAN_COLOR } from '../agents'
import { money, type AgentSummary, type FeedItem } from '../feed'
import type { Approval, Cash, Ticket } from '../types'
import { Minion, type Mood } from './Minion'

/* ------------------------------------------------------------------ cash */

/** Count the balance up or down to its new value so a payment visibly drains the jar. */
function useAnimatedNumber(target: number | null, ms = 1100) {
  const [shown, setShown] = useState(target)
  const from = useRef(target)
  useEffect(() => {
    if (target == null) return
    const start = from.current ?? target
    if (start === target) { setShown(target); return }
    const t0 = performance.now()
    let raf = 0
    const tick = (now: number) => {
      const p = Math.min(1, (now - t0) / ms)
      const eased = 1 - Math.pow(1 - p, 3)
      setShown(start + (target - start) * eased)
      if (p < 1) raf = requestAnimationFrame(tick)
      else from.current = target
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, ms])
  return shown
}

export function CashCard({ cash, lastChange }: { cash: Cash | null; lastChange: { amount: number; payee: string } | null }) {
  const shown = useAnimatedNumber(cash?.balance ?? null)
  const START = 3400
  const pct = cash ? Math.max(0, Math.min(100, (cash.balance / START) * 100)) : 0
  return (
    <section className={`cash ${lastChange ? 'cash--dropped' : ''}`} aria-labelledby="cash-title">
      <div className="cash__jar" aria-hidden="true">
        <div className="cash__fill" style={{ height: `${pct}%` }} />
        <span className="cash__coin">$</span>
      </div>
      <div>
        <h2 id="cash-title" className="eyebrow">Checking balance</h2>
        <p className="cash__amount" aria-live="polite">
          {shown == null ? '—' : `$${shown.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
        </p>
        <p className="cash__meta">
          {lastChange ? (
            <span className="cash__delta">−{money(lastChange.amount)} to {lastChange.payee}</span>
          ) : (
            <>as of desk date {cash?.as_of ?? '…'}</>
          )}
        </p>
      </div>
    </section>
  )
}

/* ------------------------------------------------------------------ tickets */

const TICKET_ICON: Record<string, string> = { customer_order: '👕', rent_notice: '🏠', price_override: '🏷️' }

export function TicketList({ tickets, selected, runningId, onSelect }: {
  tickets: Ticket[]; selected: number | null; runningId: number | null; onSelect: (id: number) => void
}) {
  // Open tickets stay on top, in id order; resolved ones drop to the bottom under a "Resolved"
  // divider. A ticket the crew is working on again counts as open until the run finishes.
  const isDone = (t: Ticket) => t.state === 'resolved' && runningId !== t.id && !t.running
  const ordered = [...tickets].sort((a, b) => Number(isDone(a)) - Number(isDone(b)) || a.id - b.id)
  const firstDone = ordered.find(isDone)?.id
  return (
    <section className="panel" aria-labelledby="tickets-title">
      <h2 id="tickets-title" className="panel__title">Ticket queue</h2>
      <ul className="tickets">
        {ordered.map((t) => {
          const running = runningId === t.id || !!t.running
          const resolved = t.state === 'resolved'
          const awaiting = !resolved && t.pending_approvals > 0
          return (
            <li key={t.id} className="tickets__item">
              {t.id === firstDone && <p className="tickets__divider">Resolved</p>}
              <button
                className={`ticket ${selected === t.id ? 'ticket--selected' : ''} ${resolved ? 'ticket--resolved' : ''} ${running ? 'ticket--running' : ''}`}
                onClick={() => onSelect(t.id)}
                aria-pressed={selected === t.id}
              >
                <span className="ticket__icon" aria-hidden="true">{TICKET_ICON[t.type] ?? '📋'}</span>
                <span className="ticket__body">
                  <span className="ticket__id">#{t.id} · {t.type.replace('_', ' ')}</span>
                  <span className="ticket__subject">{t.subject}</span>
                  <span className="ticket__who">{t.requester}</span>
                  <span className="ticket__tags">
                    <span className={`pill pill--${running ? 'running' : resolved ? 'resolved' : awaiting ? 'waiting' : 'open'}`}>
                      {running ? 'Crew working…' : resolved ? 'Resolved' : awaiting ? 'Awaiting approval' : 'Open'}
                    </span>
                    {t.pending_approvals > 0 && (
                      <span className="pill pill--waiting">{t.pending_approvals} waiting on you</span>
                    )}
                  </span>
                </span>
                {resolved && <span className="stamp" aria-hidden="true">RESOLVED</span>}
              </button>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

/* ------------------------------------------------------------------ crew */

export function Crew({ states }: { states: Record<string, { mood: Mood; line?: string }> }) {
  return (
    <section className="crew" aria-label="The minion crew">
      {AGENTS.map((a) => {
        const s = states[a.name] ?? { mood: 'idle' as Mood }
        return (
          <article key={a.name} className={`crew__member crew__member--${s.mood}`} style={{ '--agent': a.color } as React.CSSProperties}>
            <div className={`bubble ${s.line ? '' : 'bubble--empty'}`} aria-live="polite">
              <span className="bubble__text" title={s.line}>{s.line ? clip(s.line, 120) : 'Zzz…'}</span>
            </div>
            <Minion agent={a} mood={s.mood} size={84} />
            <h3 className="crew__name">{a.name}</h3>
            <p className="crew__role">{a.role}</p>
            <span className={`crew__status crew__status--${s.mood}`}>{MOOD_LABEL[s.mood]}</span>
          </article>
        )
      })}
    </section>
  )
}

const MOOD_LABEL: Record<Mood, string> = { idle: 'Idle', working: 'Working', done: 'Done', error: 'Error' }

/* ------------------------------------------------------------------ feed */

const KIND_ICON: Record<FeedItem['kind'], string> = {
  start: '▶', tool: '🔧', say: '💬', handoff: '➜', refused: '⛔', report: '↩', done: '✓', error: '!', resolved: '★', human: '🙋',
}

export function Feed({ items, running }: { items: FeedItem[]; running: boolean }) {
  const list = useRef<HTMLOListElement>(null)
  // Keep the newest line in view by scrolling the feed box only, never the whole page.
  useEffect(() => { const el = list.current; if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' }) }, [items.length])
  return (
    <section className="panel feed" aria-labelledby="feed-title">
      <h2 id="feed-title" className="panel__title">
        Live feed {running && <span className="live-dot" aria-label="live" />}
      </h2>
      {items.length === 0 ? (
        <p className="empty">Pick a ticket and send in the crew. Every move they make shows up here.</p>
      ) : (
        <ol ref={list} className="feed__list" aria-live="polite">
          {items.map((it) => {
            const color = AGENT_BY_NAME[it.agent]?.color ?? HUMAN_COLOR
            return (
              <li key={it.key} className={`feed__item feed__item--${it.kind}`} style={{ '--agent': color } as React.CSSProperties}>
                <span className="feed__icon" aria-hidden="true">{KIND_ICON[it.kind]}</span>
                <div className="feed__text">
                  <span className="feed__head">
                    <strong>{it.agent}</strong> {it.title}
                    <time>{new Date(it.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</time>
                  </span>
                  {it.detail && <span className="feed__detail">{clip(it.detail, 320)}</span>}
                </div>
              </li>
            )
          })}
        </ol>
      )}
    </section>
  )
}

/* ------------------------------------------------------------------ summary */

export function Summary({ agents, plan }: { agents: AgentSummary[]; plan?: string }) {
  if (!agents.length) return null
  return (
    <section className="panel" aria-labelledby="summary-title">
      <h2 id="summary-title" className="panel__title">What each minion did</h2>
      {plan && <p className="summary__plan">{plan}</p>}
      <div className="summary">
        {agents.map((s) => {
          const meta = AGENT_BY_NAME[s.agent]
          return (
            <article key={s.agent} className="summary__card" style={{ '--agent': meta?.color ?? HUMAN_COLOR } as React.CSSProperties}>
              <header>
                {meta && <Minion agent={meta} mood="done" size={36} />}
                <h3>{s.agent}</h3>
              </header>
              <p>{s.summary ? clip(s.summary, 360) : 'No summary returned.'}</p>
              {s.handoffsTo.length > 0 && <p className="summary__line"><b>Handed off to:</b> {s.handoffsTo.join(', ')}</p>}
              {s.tools.length > 0 && (
                <div className="chips">{s.tools.map((t) => <code key={t} className="chip">{t}</code>)}</div>
              )}
              {s.flags.length > 0 && (
                <ul className="summary__flags">{s.flags.map((f) => <li key={f}>{clip(f, 140)}</li>)}</ul>
              )}
            </article>
          )
        })}
      </div>
    </section>
  )
}

/* ------------------------------------------------------------------ approvals */

const ACTION_LABEL: Record<Approval['action_type'], string> = {
  payment: 'Payment', purchase_order: 'Purchase order', customer_message: 'Customer message',
  price_override: 'Price override', other: 'Other',
}

export function Approvals({ approvals, tickets, lockedTicket, approver, setApprover, onApprove, onSend, onApprovePrice, busyId }: {
  approvals: Approval[]; tickets: Ticket[]; lockedTicket: number | null; approver: string; setApprover: (s: string) => void
  onApprove: (a: Approval) => Promise<void>; onSend: (a: Approval, message: string) => Promise<boolean>
  onApprovePrice: (a: Approval) => Promise<void>
  busyId: number | null
}) {
  const [confirming, setConfirming] = useState<number | null>(null)
  const [editing, setEditing] = useState<Record<number, string>>({})
  const locked = (a: Approval) => a.ticket_id != null && a.ticket_id === lockedTicket
  const lockNote = <p className="approval__lock" role="status">🔒 Available when the crew finishes this ticket</p>
  const recipientOf = (a: Approval) => tickets.find((t) => t.id === a.ticket_id)?.requester ?? 'the customer'
  const messages = approvals.filter((a) => a.action_type === 'customer_message')
  const prices = approvals.filter((a) => a.action_type === 'price_override')
  const pays = approvals.filter((a) => a.action_type === 'payment' || a.action_type === 'purchase_order')
  const others = approvals.filter((a) => !pays.includes(a) && !messages.includes(a) && !prices.includes(a))
  return (
    <section className="panel approvals" aria-labelledby="approvals-title">
      <h2 id="approvals-title" className="panel__title">Human desk <span className="count">{approvals.length}</span></h2>
      <label className="field">
        <span>Your name (signs the approval)</span>
        <input value={approver} onChange={(e) => setApprover(e.target.value)} placeholder="e.g. Penny Hao" />
      </label>
      {approvals.length === 0 && <p className="empty">Nothing waiting on you. The minions never pay anything without a human okay.</p>}
      {pays.map((a) => (
        <article key={a.id} className="approval approval--pay">
          <div className="approval__top">
            <span className="pill pill--waiting">{ACTION_LABEL[a.action_type]} · #{a.id}</span>
            <span className="approval__ticket">Ticket {a.ticket_id}</span>
          </div>
          <p className="approval__amount">{money(a.amount ?? 0)} <span>to {a.payee}</span></p>
          <p className="approval__summary">{clip(a.summary, 260)}</p>
          <p className="approval__by">Requested by {a.requested_by}</p>
          {locked(a) ? lockNote : confirming === a.id ? (
            <div className="approval__actions">
              <button className="btn btn--primary" disabled={busyId === a.id}
                onClick={async () => { await onApprove(a); setConfirming(null) }}>
                {busyId === a.id ? 'Paying…' : `Yes, pay ${money(a.amount ?? 0)}`}
              </button>
              <button className="btn btn--ghost" onClick={() => setConfirming(null)}>Cancel</button>
            </div>
          ) : (
            <button className="btn btn--primary" disabled={!approver.trim()} onClick={() => setConfirming(a.id)}
              title={approver.trim() ? '' : 'Enter your name first'}>
              Approve {ACTION_LABEL[a.action_type].toLowerCase()}
            </button>
          )}
        </article>
      ))}
      {messages.map((a) => {
        const isEditing = editing[a.id] !== undefined
        const text = isEditing ? editing[a.id] : a.draft_message ?? ''
        const who = recipientOf(a)
        const confirmKey = -a.id // keep message confirms apart from payment confirms
        return (
          <article key={a.id} className="approval approval--msg">
            <div className="approval__top">
              <span className="pill pill--review">Customer message · #{a.id}</span>
              <span className="approval__ticket">Ticket {a.ticket_id}</span>
            </div>
            <p className="approval__to">To <strong>{who}</strong> · drafted by {a.requested_by}</p>
            {isEditing ? (
              <label className="field field--area">
                <span>Edit the reply before it goes out</span>
                <textarea value={text} rows={7}
                  onChange={(e) => setEditing((m) => ({ ...m, [a.id]: e.target.value }))} />
              </label>
            ) : (
              <blockquote className="approval__draft">{text}</blockquote>
            )}
            {locked(a) ? lockNote : confirming === confirmKey ? (
              <div className="approval__actions">
                <button className="btn btn--primary" disabled={busyId === a.id}
                  onClick={async () => {
                    const ok = await onSend(a, text)
                    setConfirming(null)
                    if (ok) setEditing((m) => { const c = { ...m }; delete c[a.id]; return c })
                  }}>
                  {busyId === a.id ? 'Sending…' : `Yes, send to ${who}`}
                </button>
                <button className="btn btn--ghost" onClick={() => setConfirming(null)}>Cancel</button>
              </div>
            ) : (
              <div className="approval__actions">
                <button className="btn btn--primary" disabled={!approver.trim() || !text.trim()}
                  title={approver.trim() ? '' : 'Enter your name first'} onClick={() => setConfirming(confirmKey)}>
                  {isEditing ? 'Send edited reply' : 'Send to customer'}
                </button>
                {isEditing ? (
                  <button className="btn btn--ghost" onClick={() => setEditing((m) => { const c = { ...m }; delete c[a.id]; return c })}>
                    Discard edits
                  </button>
                ) : (
                  <button className="btn btn--ghost" onClick={() => setEditing((m) => ({ ...m, [a.id]: a.draft_message ?? '' }))}>
                    Edit
                  </button>
                )}
              </div>
            )}
            <p className="approval__by">Demo mode: sending marks the reply sent and resolves the ticket. No email goes out.</p>
          </article>
        )
      })}
      {prices.map((a) => {
        const confirmKey = 100000 + a.id
        return (
          <article key={a.id} className="approval approval--price">
            <div className="approval__top">
              <span className="pill pill--price">Price override · #{a.id}</span>
              <span className="approval__ticket">Ticket {a.ticket_id}</span>
            </div>
            {a.amount != null && <p className="approval__amount">{money(a.amount)} <span>proposed price</span></p>}
            <p className="approval__summary">{clip(a.summary, 320)}</p>
            <p className="approval__by">Requested by {a.requested_by} · approving okays the discount, no cash moves</p>
            {locked(a) ? lockNote : confirming === confirmKey ? (
              <div className="approval__actions">
                <button className="btn btn--primary" disabled={busyId === a.id}
                  onClick={async () => { await onApprovePrice(a); setConfirming(null) }}>
                  {busyId === a.id ? 'Approving…' : 'Yes, approve this price'}
                </button>
                <button className="btn btn--ghost" onClick={() => setConfirming(null)}>Cancel</button>
              </div>
            ) : (
              <button className="btn btn--primary" disabled={!approver.trim()}
                title={approver.trim() ? '' : 'Enter your name first'} onClick={() => setConfirming(confirmKey)}>
                Approve price
              </button>
            )}
          </article>
        )
      })}
      {others.map((a) => (
        <article key={a.id} className="approval">
          <div className="approval__top">
            <span className="pill pill--review">{ACTION_LABEL[a.action_type]} · #{a.id}</span>
            <span className="approval__ticket">Ticket {a.ticket_id}</span>
          </div>
          <p className="approval__summary">{clip(a.summary, 220)}</p>
          {a.draft_message && <blockquote className="approval__draft">{a.draft_message}</blockquote>}
          <p className="approval__by">Waiting for human review · nothing to pay or send here</p>
        </article>
      ))}
    </section>
  )
}

function clip(s: string, n: number) {
  return s.length > n ? s.slice(0, n - 1) + '…' : s
}
