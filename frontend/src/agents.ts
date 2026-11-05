import type { AgentName } from './types'

export interface AgentMeta {
  name: AgentName
  nickname: string
  role: string
  color: string // accent used for the agent's feed lines, bubble, and summary card
  eyes: 1 | 2
  height: 'tall' | 'medium' | 'short'
  prop: 'clipboard' | 'box' | 'coin' | 'wrench' | 'headset'
  hair: 'sprout' | 'spiky' | 'bald' | 'comb' | 'tuft'
}

// Five original minion-style helpers, one per agent. Each has its own silhouette (height,
// one or two eyes, hair, prop) and accent color so they're easy to tell apart at a glance.
export const AGENTS: AgentMeta[] = [
  { name: 'Boss', nickname: 'Big Boss', role: 'Reads the ticket and picks the crew',
    color: '#ff3d9a', eyes: 2, height: 'tall', prop: 'clipboard', hair: 'sprout' },
  { name: 'Inventory', nickname: 'Stockroom', role: 'Stock, sizes, and restocks',
    color: '#5cc8ff', eyes: 1, height: 'short', prop: 'box', hair: 'spiky' },
  { name: 'Accounting', nickname: 'Bean Counter', role: 'Cash, bills, and margins',
    color: '#5ee6a8', eyes: 2, height: 'medium', prop: 'coin', hair: 'comb' },
  { name: 'Facilities', nickname: 'Fix-It', role: 'Lease, rent, and the shop',
    color: '#ffa24c', eyes: 1, height: 'tall', prop: 'wrench', hair: 'bald' },
  { name: 'Customer Service', nickname: 'Sweet Talker', role: 'Drafts replies to customers',
    color: '#b892ff', eyes: 2, height: 'short', prop: 'headset', hair: 'tuft' },
]

export const AGENT_BY_NAME: Record<string, AgentMeta> = Object.fromEntries(AGENTS.map((a) => [a.name, a]))

export const HUMAN_COLOR = '#ffd93d'
