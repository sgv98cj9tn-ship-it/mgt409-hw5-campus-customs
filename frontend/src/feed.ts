import type { AgentEvent } from './types'
import type { Mood } from './components/Minion'

/** One readable line in the live feed. */
export interface FeedItem {
  key: string
  ts: string
  agent: string
  kind: 'start' | 'tool' | 'say' | 'handoff' | 'refused' | 'report' | 'done' | 'error' | 'resolved' | 'human'
  title: string
  detail?: string
}

// Internal plumbing tools that shouldn't show up as "the agent used X".
const HIDDEN_TOOLS = new Set(['final_result', 'delegate'])

const money = (n?: number) => (n == null ? '' : `$${n.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`)

function fmtArgs(args: Record<string, unknown> | null): string {
  if (!args) return ''
  const parts = Object.entries(args)
    .filter(([, v]) => v !== null && v !== undefined && v !== '')
    .map(([k, v]) => `${k}=${typeof v === 'string' ? v : JSON.stringify(v)}`)
  const text = parts.join(', ')
  return text.length > 90 ? text.slice(0, 87) + '…' : text
}

export function toFeed(events: AgentEvent[]): FeedItem[] {
  const out: FeedItem[] = []
  events.forEach((e, i) => {
    const base = { ts: e.ts, agent: e.agent }
    const key = `${e.ts}-${i}`
    switch (e.event) {
      case 'agent_started':
        out.push({ ...base, key, kind: 'start', title: e.depth === 0 ? 'picked up the ticket' : 'got a hand-off', detail: e.task })
        break
      case 'model_response': {
        e.tools.filter((t) => !HIDDEN_TOOLS.has(t.tool)).forEach((t, j) =>
          out.push({ ...base, key: `${key}-t${j}`, kind: 'tool', title: `used ${t.tool}`, detail: fmtArgs(t.args) }),
        )
        if (e.said) out.push({ ...base, key: `${key}-s`, kind: 'say', title: 'says', detail: e.said })
        break
      }
      case 'delegation_started':
        out.push({ ...base, key, kind: 'handoff', title: `handed off to ${e.to_agent}`, detail: e.task })
        break
      case 'delegation_refused':
        out.push({ ...base, key, kind: 'refused', title: `hand-off to ${e.to_agent} blocked`, detail: e.reason })
        break
      case 'delegation_finished':
        out.push({ ...base, agent: e.to_agent ?? e.agent, key, kind: 'report', title: `reported back to ${e.agent}` })
        break
      case 'agent_finished':
        out.push({ ...base, key, kind: 'done', title: 'finished', detail: (e.output?.summary as string) ?? e.said ?? undefined })
        break
      case 'agent_error':
        out.push({ ...base, key, kind: 'error', title: 'hit an error', detail: e.error })
        break
      case 'ticket_resolved':
        out.push({ ...base, key, kind: 'resolved', title: `resolved ticket ${e.ticket_id}`,
          detail: e.agent === 'Human' ? 'The last approval is done, so nothing is waiting on a human' : 'Nothing needs a human' })
        break
      case 'crew_finished':
        out.push({ ...base, key, kind: 'done', title: `finished ticket ${e.ticket_id}`,
          detail: `${e.pending_approvals} approval(s) waiting on a human, so the ticket isn't resolved yet` })
        break
      case 'payment_approved':
        out.push({ ...base, key, kind: 'human', title: `approved ${money(e.amount)} to ${e.payee}`,
          detail: `Approved by ${e.approved_by}. Checking is now ${money(e.checking_after)}.` })
        break
      case 'customer_message_sent':
        out.push({ ...base, key, kind: 'human', title: `sent the ${e.edited ? 'edited ' : ''}reply to ${e.recipient}`,
          detail: `${e.message ?? ''} (Approved by ${e.approved_by}. Simulated: nothing was actually emailed.)` })
        break
      case 'price_override_approved':
        out.push({ ...base, key, kind: 'human', title: `approved the price override${e.amount ? ` (${money(e.amount)})` : ''}`,
          detail: `Approved by ${e.approved_by}. No cash moved.` })
        break
      case 'db_reset':
        out.push({ ...base, key, kind: 'human', title: 'reset the shop data', detail: 'Fresh copy of the original database' })
        break
    }
  })
  return out
}

/** Each agent's current mood, from the latest events. */
export function moods(events: AgentEvent[], running: boolean): Record<string, { mood: Mood; line?: string }> {
  const state: Record<string, { mood: Mood; line?: string }> = {}
  for (const e of events) {
    const cur = state[e.agent] ?? { mood: 'idle' as Mood }
    if (e.event === 'agent_started') state[e.agent] = { mood: 'working', line: 'On it!' }
    else if (e.event === 'model_response') {
      const tool = e.tools.find((t) => !HIDDEN_TOOLS.has(t.tool))
      const handoff = e.tools.find((t) => t.tool === 'delegate')
      const line = e.said ?? (handoff ? `Asking ${String(handoff.args?.to_agent ?? 'a teammate')}…`
        : tool ? `Checking ${tool.tool}…` : cur.line)
      state[e.agent] = { mood: 'working', line }
    } else if (e.event === 'delegation_started') state[e.agent] = { mood: 'working', line: `Waiting on ${e.to_agent}…` }
    else if (e.event === 'agent_finished')
      state[e.agent] = { mood: 'done', line: (e.output?.summary as string) ?? 'Done!' }
    else if (e.event === 'agent_error') state[e.agent] = { mood: 'error', line: 'Uh oh…' }
  }
  if (!running) {
    for (const k of Object.keys(state)) if (state[k].mood === 'working') state[k] = { ...state[k], mood: 'idle' }
  }
  return state
}

export interface AgentSummary {
  agent: string
  summary?: string
  tools: string[]
  handoffsTo: string[]
  flags: string[]
}

/** What each agent did in the latest run of a ticket. */
export function summarize(events: AgentEvent[]): { runId: string | null; agents: AgentSummary[] } {
  const runs = events.filter((e) => e.run_id !== 'human' && e.event === 'agent_started' && e.depth === 0)
  const runId = runs.length ? runs[runs.length - 1].run_id : null
  if (!runId) return { runId: null, agents: [] }
  const byAgent = new Map<string, AgentSummary>()
  const get = (a: string) => {
    if (!byAgent.has(a)) byAgent.set(a, { agent: a, tools: [], handoffsTo: [], flags: [] })
    return byAgent.get(a)!
  }
  for (const e of events.filter((x) => x.run_id === runId)) {
    if (e.event === 'agent_started') get(e.agent)
    if (e.event === 'model_response')
      e.tools.filter((t) => !HIDDEN_TOOLS.has(t.tool)).forEach((t) => {
        const s = get(e.agent)
        if (!s.tools.includes(t.tool)) s.tools.push(t.tool)
      })
    if (e.event === 'delegation_started' && e.to_agent) {
      const s = get(e.agent)
      if (!s.handoffsTo.includes(e.to_agent)) s.handoffsTo.push(e.to_agent)
    }
    if (e.event === 'agent_finished') {
      const s = get(e.agent)
      s.summary = (e.output?.summary as string) ?? s.summary
      const flags = e.output?.flags
      if (Array.isArray(flags)) s.flags = flags.map(String).slice(0, 3)
      const blockers = e.output?.blockers
      if (Array.isArray(blockers) && !s.flags.length) s.flags = blockers.map(String).slice(0, 3)
    }
  }
  return { runId, agents: [...byAgent.values()] }
}

export { money }
