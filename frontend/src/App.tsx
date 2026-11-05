import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { moods, summarize, toFeed } from './feed'
import { Approvals, CashCard, Crew, Feed, Summary, TicketList } from './components/Panels'
import type { AgentEvent, Approval, Cash, RunResult, Ticket } from './types'

const POLL_MS = 1500

export default function App() {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [today, setToday] = useState('')
  const [cash, setCash] = useState<Cash | null>(null)
  const [approvals, setApprovals] = useState<Approval[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [runningId, setRunningId] = useState<number | null>(null)
  const [runStart, setRunStart] = useState<string | null>(null)
  const [lastRun, setLastRun] = useState<RunResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [approver, setApproverState] = useState(() => localStorage.getItem('approver') ?? '')
  const [busyId, setBusyId] = useState<number | null>(null)
  const [lastChange, setLastChange] = useState<{ amount: number; payee: string } | null>(null)
  const [confirmReset, setConfirmReset] = useState(false)
  const [loading, setLoading] = useState(true)

  const setApprover = (s: string) => { setApproverState(s); localStorage.setItem('approver', s) }

  const refreshBoard = useCallback(async () => {
    try {
      const [t, c, a] = await Promise.all([api.tickets(), api.cash(), api.approvals('pending')])
      setTickets(t.tickets)
      setToday(t.today)
      setCash(c)
      setApprovals(a.approvals)
      // A link like http://localhost:5173/#ticket=102 opens that ticket.
      const fromHash = Number(new URLSearchParams(location.hash.slice(1)).get('ticket'))
      setSelected((s) => s ?? (t.tickets.some((x) => x.id === fromHash) ? fromHash
        : (t.tickets.find((x) => x.state !== 'resolved') ?? t.tickets[0])?.id ?? null))
      setError(null)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  const loadEvents = useCallback(async (ticketId: number, since?: string) => {
    try {
      const r = await api.events({ ticketId, since })
      setEvents(r.events)
    } catch (e) {
      setError((e as Error).message)
    }
  }, [])

  useEffect(() => { void refreshBoard() }, [refreshBoard])

  // When you pick a ticket (and nothing is running), show its most recent run.
  useEffect(() => {
    if (selected != null && runningId == null) void loadEvents(selected)
  }, [selected, runningId, loadEvents])

  // While the crew works, poll the audit trail so the feed and bubbles update live.
  useEffect(() => {
    if (runningId == null || runStart == null) return
    const id = setInterval(() => { void loadEvents(runningId, runStart); void refreshBoard() }, POLL_MS)
    return () => clearInterval(id)
  }, [runningId, runStart, loadEvents, refreshBoard])

  const startRun = async () => {
    if (selected == null || runningId != null) return
    const ticketId = selected
    const since = new Date(Date.now() - 2000).toISOString()
    setRunningId(ticketId)
    setRunStart(since)
    setEvents([])
    setLastRun(null)
    setNotice(null)
    setError(null)
    try {
      const result = await api.runTicket(ticketId)
      setLastRun(result)
      setNotice(result.ticket_status === 'resolved'
        ? `Ticket ${ticketId} resolved by the crew · nothing needs a human`
        : `The crew finished ticket ${ticketId} · ${result.pending_approvals} approval(s) on the human desk before it's resolved`)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setRunningId(null)
      setRunStart(null)
      await refreshBoard()
      await loadEvents(ticketId)
    }
  }

  const approve = async (a: Approval) => {
    setBusyId(a.id)
    setError(null)
    try {
      const r = await api.approve(a.id, approver.trim())
      setLastChange({ amount: r.amount, payee: r.payee })
      setNotice(`Paid ${r.payee} $${r.amount.toLocaleString()} · checking went from $${r.checking_before.toLocaleString()} to $${r.checking_after.toLocaleString()}`)
      await refreshBoard()
      if (selected != null) await loadEvents(selected)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusyId(null)
    }
  }

  const sendMessage = async (a: Approval, message: string): Promise<boolean> => {
    setBusyId(a.id)
    setError(null)
    try {
      const r = await api.sendMessage(a.id, approver.trim(), message)
      setNotice(`${r.edited ? 'Edited reply' : 'Reply'} sent to ${r.recipient} · ticket ${a.ticket_id} resolved (demo: nothing was emailed)`)
      await refreshBoard()
      if (selected != null) await loadEvents(selected)
      return true
    } catch (e) {
      setError((e as Error).message)
      return false
    } finally {
      setBusyId(null)
    }
  }

  const approvePrice = async (a: Approval) => {
    setBusyId(a.id)
    setError(null)
    try {
      const r = await api.approvePrice(a.id, approver.trim())
      const c = r.price_check
      setNotice(`Price override approved for ticket ${a.ticket_id}` +
        (c ? ` · $${c.unit_price.toFixed(2)} a unit (${c.discount_percent}% off), $${c.order_total.toLocaleString()} total` : '') +
        ' · no cash moved')
      await refreshBoard()
      if (selected != null) await loadEvents(selected)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusyId(null)
    }
  }

  const reset = async () => {
    setConfirmReset(false)
    try {
      await api.reset()
      setLastRun(null)
      setLastChange(null)
      setEvents([])
      setNotice('Shop data reset to the original values. Every ticket is open again.')
      await refreshBoard()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  // The feed shows the current run while it's going, otherwise the ticket's latest run.
  const shownEvents = useMemo(() => {
    if (runningId != null) return events
    const { runId } = summarize(events)
    if (!runId) return events.filter((e) => e.run_id === 'human')
    const startTs = events.find((e) => e.run_id === runId)?.ts ?? ''
    return events.filter((e) => e.run_id === runId || (e.run_id === 'human' && e.ts >= startTs))
  }, [events, runningId])

  const feed = useMemo(() => toFeed(shownEvents), [shownEvents])
  const crewStates = useMemo(() => moods(shownEvents, runningId != null), [shownEvents, runningId])
  const summary = useMemo(() => summarize(shownEvents), [shownEvents])
  const ticket = tickets.find((t) => t.id === selected) ?? null
  const bossPlan = lastRun?.ticket_id === selected ? lastRun?.plan.summary : summary.agents.find((a) => a.agent === 'Boss')?.summary
  const resolvedCount = tickets.filter((t) => t.state === 'resolved').length

  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <span className="brand__goggle" aria-hidden="true" />
          <div>
            <p className="eyebrow">Campus Customs · desk date {today || '…'}</p>
            <h1>The Minion Desk</h1>
          </div>
        </div>
        <div className="top__stats">
          <div className="stat">
            <span className="stat__num">{resolvedCount}/{tickets.length || 3}</span>
            <span className="stat__label">resolved</span>
          </div>
          <div className="stat">
            <span className="stat__num">{approvals.length}</span>
            <span className="stat__label">waiting on you</span>
          </div>
          {confirmReset ? (
            <div className="reset-confirm">
              <span>Reset all shop data?</span>
              <button className="btn btn--danger" onClick={reset}>Reset</button>
              <button className="btn btn--ghost" onClick={() => setConfirmReset(false)}>Cancel</button>
            </div>
          ) : (
            <button className="btn btn--ghost" onClick={() => setConfirmReset(true)} disabled={runningId != null}>
              Reset shop data
            </button>
          )}
        </div>
      </header>

      {error && <div className="banner banner--error" role="alert">{error}</div>}
      {notice && !error && <div className="banner banner--ok" role="status">{notice}</div>}

      <main className="grid">
        <aside className="col col--left">
          <CashCard cash={cash} lastChange={lastChange} />
          {loading ? <div className="panel skeleton">Loading tickets…</div> :
            <TicketList tickets={tickets} selected={selected} runningId={runningId} onSelect={(id) => { setSelected(id); history.replaceState(null, '', `#ticket=${id}`) }} />}
        </aside>

        <section className="col col--center">
          <div className="stage panel">
            <div className="stage__head">
              <div>
                <p className="eyebrow">Now on the desk</p>
                <h2 className="stage__title">
                  {ticket ? <>#{ticket.id} · {ticket.subject}</> : 'Pick a ticket'}
                </h2>
                {ticket && <p className="stage__sub">{ticket.requester}{ticket.notes ? ` · ${ticket.notes.split('\n')[0]}` : ''}</p>}
              </div>
              <button className="btn btn--primary btn--big" onClick={startRun} disabled={ticket == null || runningId != null}>
                {runningId != null ? 'Crew working…' : ticket?.state === 'resolved' ? 'Run the crew again' : 'Send in the crew'}
              </button>
            </div>
            <Crew states={crewStates} />
            {lastRun && lastRun.ticket_id === selected && (
              <p className="usage">
                Run used {lastRun.usage.requests} model calls, {lastRun.usage.tool_calls} tool calls,{' '}
                {(lastRun.usage.input_tokens + lastRun.usage.output_tokens).toLocaleString()} tokens
              </p>
            )}
          </div>
          <Feed items={feed} running={runningId != null} />
          {runningId == null && <Summary agents={summary.agents} plan={bossPlan} />}
        </section>

        <aside className="col col--right">
          <Approvals approvals={approvals} tickets={tickets} lockedTicket={runningId ?? tickets.find((t) => t.running)?.id ?? null} approver={approver} setApprover={setApprover}
            onApprove={approve} onSend={sendMessage} onApprovePrice={approvePrice} busyId={busyId} />
        </aside>
      </main>

      <footer className="foot">Every agent step is saved to output/audit_trail.json · the minions prepare, a human pays</footer>
    </div>
  )
}
