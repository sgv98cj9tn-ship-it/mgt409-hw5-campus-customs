import { useId } from 'react'
import type { AgentMeta } from '../agents'

export type Mood = 'idle' | 'working' | 'done' | 'error'

const YELLOW = '#ffd93d'
const YELLOW_SHADE = '#f2c12e'
const DENIM = '#3a6ea5'
const DENIM_DARK = '#2c5684'
const STRAP = '#262626'
const METAL = '#c9ced6'
const METAL_RIM = '#7d8590'

const TOPS = { tall: 8, medium: 22, short: 38 } as const

/** An original, hand-drawn minion-style helper. Silhouette, eyes, hair, and prop vary by agent. */
export function Minion({ agent, mood = 'idle', size = 96 }: { agent: AgentMeta; mood?: Mood; size?: number }) {
  const clipId = `body-${useId().replace(/[^a-zA-Z0-9]/g, '')}`
  const top = TOPS[agent.height]
  const eyeY = top + 34
  const mouthY = eyeY + 27
  const eyes = agent.eyes === 2 ? [{ cx: 47, r: 12 }, { cx: 73, r: 12 }] : [{ cx: 60, r: 16 }]

  return (
    <svg
      className={`minion minion--${mood}`}
      viewBox="0 0 120 160"
      width={size}
      height={(size * 160) / 120}
      role="img"
      aria-label={`${agent.name} minion, ${mood}`}
    >
      <defs>
        <clipPath id={clipId}>
          <rect x="30" y={top} width="60" height={142 - top} rx="30" />
        </clipPath>
      </defs>

      {/* feet */}
      <ellipse cx="47" cy="149" rx="11" ry="6" fill={STRAP} />
      <ellipse cx="73" cy="149" rx="11" ry="6" fill={STRAP} />

      {/* arms */}
      <path d="M31 98 Q16 108 18 124" stroke={YELLOW_SHADE} strokeWidth="7" fill="none" strokeLinecap="round" />
      <path d="M89 98 Q104 108 102 124" stroke={YELLOW_SHADE} strokeWidth="7" fill="none" strokeLinecap="round" />
      <circle cx="18" cy="126" r="5.5" fill={STRAP} />
      <circle cx="102" cy="126" r="5.5" fill={STRAP} />

      {/* body + overalls, clipped to the capsule */}
      <g clipPath={`url(#${clipId})`}>
        <rect x="30" y={top} width="60" height={142 - top} fill={YELLOW} />
        <rect x="78" y={top} width="12" height={142 - top} fill={YELLOW_SHADE} opacity="0.55" />
        <rect x="30" y="104" width="60" height="40" fill={DENIM} />
        <rect x="42" y="90" width="36" height="20" rx="4" fill={DENIM} />
        <path d="M30 86 L44 94" stroke={DENIM_DARK} strokeWidth="4" />
        <path d="M90 86 L76 94" stroke={DENIM_DARK} strokeWidth="4" />
        <rect x="52" y="96" width="16" height="10" rx="3" fill={DENIM_DARK} />
        <circle cx="45" cy="94" r="2" fill={METAL} />
        <circle cx="75" cy="94" r="2" fill={METAL} />
        <rect x="58" y="120" width="4" height="22" fill={DENIM_DARK} />
      </g>

      <Hair kind={agent.hair} top={top} />

      {/* goggle strap and goggles */}
      <rect x="27" y={eyeY - 5} width="66" height="10" fill={STRAP} />
      {eyes.map((e) => (
        <g key={e.cx}>
          <circle cx={e.cx} cy={eyeY} r={e.r + 4} fill={METAL} stroke={METAL_RIM} strokeWidth="2.5" />
          <circle cx={e.cx} cy={eyeY} r={e.r} fill="#fff" />
          <g className="minion__pupil">
            <circle cx={e.cx} cy={eyeY} r={e.r * 0.48} fill="#6b4226" />
            <circle cx={e.cx} cy={eyeY} r={e.r * 0.24} fill="#111" />
            <circle cx={e.cx - e.r * 0.2} cy={eyeY - e.r * 0.22} r={e.r * 0.1} fill="#fff" />
          </g>
          {mood === 'done' && <path d={`M${e.cx - e.r} ${eyeY - e.r + 1} Q${e.cx} ${eyeY - e.r - 6} ${e.cx + e.r} ${eyeY - e.r + 1}`} stroke={STRAP} strokeWidth="2" fill="none" />}
        </g>
      ))}

      <Mouth mood={mood} y={mouthY} />
      <Prop kind={agent.prop} eyeY={eyeY} mouthY={mouthY} accent={agent.color} />
    </svg>
  )
}

function Mouth({ mood, y }: { mood: Mood; y: number }) {
  if (mood === 'working') return <ellipse cx="60" cy={y} rx="6" ry="5" fill="#5a1f1f" />
  if (mood === 'error') return <path d={`M50 ${y + 2} Q60 ${y - 4} 70 ${y + 2}`} stroke="#5a1f1f" strokeWidth="3" fill="none" strokeLinecap="round" />
  if (mood === 'done')
    return <path d={`M47 ${y - 3} Q60 ${y + 12} 73 ${y - 3} Z`} fill="#5a1f1f" stroke="#5a1f1f" strokeWidth="2" strokeLinejoin="round" />
  return <path d={`M51 ${y} Q60 ${y + 6} 69 ${y}`} stroke="#5a1f1f" strokeWidth="3" fill="none" strokeLinecap="round" />
}

function Hair({ kind, top }: { kind: AgentMeta['hair']; top: number }) {
  const s = { stroke: STRAP, strokeWidth: 2, fill: 'none', strokeLinecap: 'round' as const }
  switch (kind) {
    case 'sprout':
      return (
        <g {...s}>
          <path d={`M60 ${top + 1} Q57 ${top - 9} 52 ${top - 13}`} />
          <path d={`M60 ${top + 1} L60 ${top - 14}`} />
          <path d={`M60 ${top + 1} Q63 ${top - 9} 68 ${top - 13}`} />
        </g>
      )
    case 'spiky':
      return (
        <g {...s}>
          {[44, 50, 56, 62, 68, 74].map((x, i) => (
            <path key={x} d={`M${x} ${top + 5} L${x + (i % 2 ? 2 : -2)} ${top - 7}`} />
          ))}
        </g>
      )
    case 'comb':
      return (
        <g {...s}>
          <path d={`M46 ${top + 6} Q56 ${top - 5} 72 ${top + 2}`} />
          <path d={`M48 ${top + 9} Q58 ${top - 1} 74 ${top + 5}`} />
        </g>
      )
    case 'tuft':
      return <path {...s} d={`M60 ${top + 1} Q58 ${top - 12} 66 ${top - 12} Q70 ${top - 6} 63 ${top - 5}`} />
    default:
      return null
  }
}

function Prop({ kind, eyeY, mouthY, accent }: { kind: AgentMeta['prop']; eyeY: number; mouthY: number; accent: string }) {
  switch (kind) {
    case 'clipboard':
      return (
        <g>
          <rect x="96" y="106" width="20" height="28" rx="2" fill="#9a6b3f" />
          <rect x="99" y="111" width="14" height="20" fill="#fff" />
          <rect x="102" y="103" width="8" height="5" rx="1.5" fill={METAL_RIM} />
          <path d="M101 116h10M101 120h10M101 124h7" stroke={accent} strokeWidth="1.6" />
        </g>
      )
    case 'box':
      return (
        <g>
          <rect x="38" y="110" width="44" height="28" rx="2" fill="#c58b4b" />
          <rect x="38" y="110" width="44" height="7" fill="#a8733b" />
          <rect x="56" y="110" width="8" height="28" fill="#e3c08f" />
        </g>
      )
    case 'coin':
      return (
        <g>
          <circle cx="104" cy="118" r="11" fill="#ffcf33" stroke="#c9961a" strokeWidth="2.5" />
          <text x="104" y="123" textAnchor="middle" fontSize="13" fontWeight="700" fill="#8a6410" fontFamily="Fredoka, sans-serif">$</text>
        </g>
      )
    case 'wrench':
      return (
        <g transform="rotate(-35 104 118)">
          <rect x="101" y="104" width="6" height="30" rx="2" fill="#9aa3ad" />
          <path d="M96 100 a8 8 0 1 0 16 0 l-4 0 l0 5 l-8 0 l0 -5 z" fill="#9aa3ad" />
        </g>
      )
    case 'headset':
      return (
        <g fill="none" stroke={STRAP} strokeWidth="3" strokeLinecap="round">
          <path d={`M33 ${eyeY - 8} Q60 ${eyeY - 44} 87 ${eyeY - 8}`} />
          <rect x="85" y={eyeY + 6} width="8" height="14" rx="3" fill={accent} stroke="none" />
          <path d={`M89 ${eyeY + 18} Q86 ${mouthY + 4} 70 ${mouthY + 2}`} strokeWidth="2" />
          <circle cx="69" cy={mouthY + 2} r="3" fill={STRAP} stroke="none" />
        </g>
      )
  }
}
