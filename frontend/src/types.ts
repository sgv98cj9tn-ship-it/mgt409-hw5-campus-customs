export type AgentName = 'Boss' | 'Inventory' | 'Accounting' | 'Facilities' | 'Customer Service'

export interface Ticket {
  id: number
  type: string
  requester: string
  subject: string
  sku: string | null
  size: string | null
  qty: number | null
  lease_id: number | null
  invoice_id: number | null
  status: string
  notes: string | null
  created_at: string
  state: 'open' | 'resolved'
  pending_approvals: number
  running?: boolean
}

export interface ToolCall {
  tool: string
  args: Record<string, unknown> | null
}

export interface AgentEvent {
  ts: string
  run_id: string
  ticket_id: number | null
  agent: string
  depth: number
  event: string
  said: string | null
  tools: ToolCall[]
  to_agent?: string
  task?: string
  status?: string
  reason?: string
  error?: string
  amount?: number
  payee?: string
  kind?: string
  approved_by?: string
  checking_after?: number
  agent_status?: string
  pending_approvals?: number
  output?: Record<string, unknown>
  recipient?: string
  edited?: boolean
  message?: string
}

export interface Approval {
  id: number
  ticket_id: number | null
  action_type: 'payment' | 'purchase_order' | 'customer_message' | 'price_override' | 'other'
  summary: string
  amount: number | null
  payee: string | null
  draft_message: string | null
  requested_by: string
  status: string
  created_at: string
  decided_by: string | null
  decided_at: string | null
}

export interface Cash {
  account: string
  balance: number
  as_of: string
}

export interface RunResult {
  run_id: string
  ticket_id: number
  plan: { summary?: string; ticket_status?: string; blockers?: string[]; approval_request_ids?: number[] }
  delegations: { from_agent: string; to_agent: string; status: string }[]
  usage: { requests: number; tool_calls: number; input_tokens: number; output_tokens: number }
  ticket_status: string
  agent_status: string
  pending_approvals: number
}
