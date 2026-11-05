# Campus Customs: multi-agent operations desk

MGT409 Homework 5. Five PydanticAI agents (Boss, Inventory, Accounting, Facilities, Customer Service) work the shop's tickets
through an MCP server, a FastAPI backend serves them to a React board ("The Minion Desk"), and a human approves every payment,
price, and customer message.

## Layout

| Path | What it is |
|---|---|
| `data/campus_customs.db` | The original database. Never changed. |
| `data/campus_customs_new.db` | The working copy the agents read and write. |
| `mcp_server/server.py` | The `campus-customs-ops` MCP server (FastMCP): the agents' only way into the data. See `mcp_server/README.md`. |
| `backend/` | The agents (`agents.py`, prompts in `prompts/`), the MCP connection, the audit trail, and the FastAPI app (`main.py`). |
| `frontend/` | The React + Vite + TypeScript board. |
| `output/` | `harness.md` (how it all works), `desk_tickets.html` (plan vs. actual, cash, reflection), `resolved_tickets.json`, `resolved_board.html`, `design.md`, `audit_trail.json`, `mcp_smoke.json`, `github_url.txt`. |
| `AI_prompts.md` | The prompts used to build this. |

## Setup (once)

You need Python 3.11+ and Node 20+.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # then put your key in .env: PORTKEY_API_KEY=...
cd frontend && npm install && cd ..
```

The model is `gpt-6-luna` through Portkey. Set `OPENAI_MODEL` in `.env` to change it.

## Run it

**1. Start from a clean working copy** whenever you want a fresh run:

```bash
cp data/campus_customs.db data/campus_customs_new.db
```

**2. The MCP server.** The backend starts it automatically over stdio, so you don't need a separate terminal. To run it on
its own (for example, to try the tools in Claude Code with `.mcp.json`):

```bash
.venv/bin/python mcp_server/server.py          # stdio
.venv/bin/python mcp_server/server.py --http   # http://127.0.0.1:8002
```

**3. The FastAPI backend** (from `backend/`):

```bash
cd backend
../.venv/bin/uvicorn main:app --reload --port 8000
```

Every route can be tried at http://localhost:8000/docs.

**4. The React board** (in a second terminal, from `frontend/`):

```bash
cd frontend
npm run dev
```

Open http://localhost:5173.

## A full three-ticket run

1. **Reset the database first:** click **Reset shop data** on the board (or `curl -X POST localhost:8000/reset`). Checking goes back to $3,400, and all three tickets reopen. The audit trail is kept, with a `db_reset` marker added.
2. Pick ticket 101 and click **Send in the crew**. Watch the minions and the live feed.
3. When the run finishes, use the **Human desk**: type your name, then approve payments, send or edit customer replies, and approve prices. The desk is locked while the crew is working a ticket, and a ticket is resolved only once nothing on it is waiting.
4. Repeat for 102 and 103.

Results land in `output/audit_trail.json` (every step) and `output/resolved_tickets.json` (updated after every run and decision).
You can also run tickets from the command line: `.venv/bin/python -m backend.run_tickets --all-open`.

## Safety

Agents can't pay, order, or contact anyone. They can only queue requests for a human. Customer Service can't see costs, vendors,
or rent, and every customer message (including a human's edits) is checked for internal information before it's sent. Sending is
simulated: nothing is emailed. Details and token limits are in `output/harness.md`.
