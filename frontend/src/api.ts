import type { AgentEvent, Approval, Cash, RunResult, Ticket } from './types'

// The FastAPI backend (backend/main.py). Override with VITE_API_URL in frontend/.env.
export const API_URL = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '')

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(API_URL + path, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    })
  } catch {
    throw new Error(`Can't reach the backend at ${API_URL}. Start it from backend/ with: uvicorn main:app --reload --port 8000`)
  }
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    const detail = typeof body?.detail === 'string' ? body.detail : JSON.stringify(body?.detail ?? body)
    throw new Error(detail || `${res.status} ${res.statusText}`)
  }
  return body as T
}

export const api = {
  tickets: () => call<{ today: string; tickets: Ticket[] }>('/tickets'),
  runTicket: (id: number) => call<RunResult>(`/tickets/${id}/run`, { method: 'POST' }),
  events: (params: { ticketId?: number; since?: string; limit?: number }) => {
    const q = new URLSearchParams()
    if (params.ticketId != null) q.set('ticket_id', String(params.ticketId))
    if (params.since) q.set('since', params.since)
    q.set('limit', String(params.limit ?? 500))
    return call<{ events: AgentEvent[]; count: number }>(`/events?${q}`)
  },
  approvals: (status: string | null = 'pending') =>
    call<{ approvals: Approval[] }>(`/approvals${status ? `?status=${status}` : '?status='}`),
  approve: (id: number, approvedBy: string) =>
    call<{ amount: number; payee: string; checking_after: number; checking_before: number; kind: string }>(
      `/approvals/${id}/approve`,
      { method: 'POST', body: JSON.stringify({ approved_by: approvedBy }) },
    ),
  sendMessage: (id: number, approvedBy: string, message?: string) =>
    call<{ recipient: string; edited: boolean; message: string }>(
      `/approvals/${id}/send`,
      { method: 'POST', body: JSON.stringify({ approved_by: approvedBy, message }) },
    ),
  approvePrice: (id: number, approvedBy: string) =>
    call<{ price_check: { unit_price: number; discount_percent: number; order_total: number } | null; ticket_status: string }>(
      `/approvals/${id}/approve-price`,
      { method: 'POST', body: JSON.stringify({ approved_by: approvedBy }) },
    ),
  cash: () => call<Cash>('/cash'),
  reset: () => call<{ ok: boolean; message: string }>('/reset', { method: 'POST' }),
}
