# The Minion Desk: dashboard design

The Campus Customs board (`frontend/`, React + Vite + TypeScript) is called **The Minion Desk**. Each agent is a little yellow minion-style helper, so watching the team work feels like watching a crew of characters pass a job around a back office, not like reading a log file.

Run it with the backend on port 8000 (`uvicorn main:app --reload --port 8000` from `backend/`), then `npm run dev` from `frontend/`, and open http://localhost:5173.

## Layout

Three columns, arranged in the order a person uses them:

| Left: what's on the desk | Center: the crew at work | Right: what needs me |
|---|---|---|
| **Cash jar** with the checking balance, then the **ticket queue**: open tickets on top, resolved ones below | **Stage**: the selected ticket, the big **Send in the crew** button, and all five minions with speech bubbles. Under it, the **live feed** and then **What each minion did** | **Human desk**: every approval waiting on a person, with the approve button |

- **Why:** you read left to right: pick a ticket, watch the crew, then act. Money (cash on the left, approvals on the right) frames the agents' work on both sides, because money is where a human has to stay in control.
- The header has quick counts (resolved out of 3, and how many things are waiting on you) plus a **Reset shop data** button that asks you to confirm first.
- On a narrow screen the columns stack, and the human desk moves under the crew.

## How the agents read differently

Each agent is an original, hand-drawn minion-style character (drawn as SVG in `frontend/src/components/Minion.tsx`, no copied art) with its **own silhouette, prop, and accent color**. You can tell them apart by shape alone, not just color:

| Agent | Look | Prop | Color |
|---|---|---|---|
| Boss | Tall, two eyes, sprout of hair | Clipboard | Pink |
| Inventory | Short, one big eye, spiky hair | Cardboard box | Sky blue |
| Accounting | Medium, two eyes, combed hair | Gold coin | Mint |
| Facilities | Tall, one eye, bald | Wrench | Orange |
| Customer Service | Short, two eyes, curl of hair | Headset | Violet |

- **Mood shows what they're doing.** An idle minion stands still under a "Zzz…" bubble. A working minion bobs, its eyes dart side to side, its mouth opens, and its card lights up in its color. A done minion hops once and smiles, and its status turns green. An error flattens the mouth and dulls the colors.
- **Speech bubbles** show each minion's latest line while the ticket runs: what it said, which tool it's checking, or "Waiting on Accounting…" when it has handed work off.
- **The live feed** uses the same color for each agent: a colored left edge, the agent's name in its color, and an icon for the kind of step (🔧 tool call, ➜ hand-off, ↩ reported back, ✓ finished, ⛔ hand-off blocked). Tool calls show their arguments in monospace, so you can see exactly what was checked.
- **What each minion did** gives one card per agent, topped with its color and a small minion icon: its own summary, who it handed off to, chips for the MCP tools it used, and its flags. The Boss's final plan sits above the cards.

## How resolved tickets show up

- A ticket card has four states. **Open** is gray. **Crew working…** is yellow with a pulsing border. **Awaiting approval** is pink, with a "N waiting on you" badge. **Resolved** is a mint pill, a faint mint wash, and a tilted **RESOLVED** rubber stamp on the card.
- **Resolved tickets drop to the bottom of the queue**, under a thin mint **Resolved** divider, and slide into place. The open work is always at the top, so the queue reads like a to-do list: what's left first, finished work below. When the board opens, it selects the first open ticket. A resolved ticket you run again moves back up while the crew works it.
- **A ticket is resolved only when nothing on it still needs a human.** When the crew finishes, a ticket with nothing queued is resolved right away. A ticket with payments, replies, or price overrides waiting goes to **Awaiting approval** and stays in the open part of the queue. It turns resolved the moment the last of those approvals is decided, so a resolved stamp never hides an unpaid bill or an unsent reply. While the crew is working, that ticket's cards on the human desk are locked with "🔒 Available when the crew finishes this ticket", so a human decision can't land in the middle of a run.
- A green banner says which it was, for example "The crew finished ticket 102 · 1 approval(s) on the human desk before it's resolved". The live feed marks the crew finishing with ✓, and marks the moment the ticket is resolved with ★.

## How cash shows up

- **The cash jar** is the most prominent card on the page: a pink-glow card with the checking balance in large type and a jar that's filled in proportion to the starting $3,400.
- **After a human approves a payment,** the number counts down to the new balance, flashes red for a moment, and the jar drains. A pink line shows what changed ("−$2,400 to Elm City Properties"), and a banner states the before and after.
- **Paying takes two clicks and a name.** You type your name (it signs the payment), click **Approve payment**, then **Yes, pay $2,400**. The approve button stays disabled until there's a name.
- **Other decisions have their own colored cards, and none of them move cash.** Customer messages (violet) have **Send to customer** and **Edit**: Edit opens the agent's draft in a text box so you can fix it before sending. Sending is simulated: the reply is marked sent and nothing is emailed. Price overrides (orange) have **Approve price**, which refuses any price at or below cost.

## Creative choices, and why

- **Minions as the crew.** A team of eager little helpers fits the brief exactly: they do the legwork, they chatter, they hand things off, and they need a grown-up to sign for anything that costs money. That makes the "agents prepare, a human pays" rule something you can see.
- **Black and pink with yellow characters.** The near-black background keeps a busy board calm. Pink marks anything that needs a human (buttons, the cash card, the human desk). The minions' yellow is the warmest thing on the page, so your eye goes to the crew.
- **Motion with meaning.** Every animation tells you something: bobbing means working, a hop means done, a pulse means running, a draining jar means money left. Users who prefer less motion (the reduced-motion setting) get the board with the animations turned off.
- **A desk, not a log.** Icons, rubber stamps, a cash jar, and speech bubbles make it feel like a real front desk someone would enjoy sitting at, while the feed and summary cards still show every tool call, for checking the agents' work.
- **Readable and accessible.** The text is light on dark with strong contrast, the buttons are labeled, and you can see where you are when moving around with the keyboard. The feed and the bubbles update for screen readers, and the layout works on a phone.
