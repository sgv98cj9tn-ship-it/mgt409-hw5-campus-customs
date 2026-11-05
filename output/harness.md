# Campus Customs Agent Harness

Database: `data/campus_customs.db` is the untouched original. Agents read and write the working copy `data/campus_customs_new.db`.

The agents are the Campus Customs operations team: they work the open tickets in `tickets` and use the MCP server's tools to check the facts in the other tables before acting. The notes below say why each table matters to them.

## Tables in `campus_customs_new.db`

| Table | Fields | Why it matters for the agents |
|---|---|---|
| `desk` | `date_today`, `notes` | The shop's "today" (2026-08-31). Agents judge due dates, overdue bills, and delivery estimates against this date, not the real clock. |
| `tickets` | `id`, `type`, `requester`, `subject`, `sku`, `size`, `qty`, `lease_id`, `invoice_id`, `status`, `notes`, `created_at` | The agents' work queue. `type` (customer_order, rent_notice, price_override) decides how a ticket is handled, and `sku`/`size`, `lease_id`, and `invoice_id` point to the records needed to resolve it. `status` tracks whether it's done. |
| `inventory` | `sku`, `name`, `size`, `qty`, `location` | Shows whether an order can be filled from stock and where to pick it. Stock is per `sku` + `size`, so agents must check the exact size requested. `qty` 0 means sold out, as with ticket 101's size S tee. |
| `pricing` | `sku`, `unit_cost`, `list_price` | `list_price` is the price agents quote. `unit_cost` is the floor for any discount, as in ticket 103's bulk ask. It's internal and is never shown to customers. |
| `vendors` | `id`, `name`, `specialty`, `lead_days` | Tells agents who can restock or deliver an item and how long it takes. This drives what they promise a customer, for example 5 days for a Bulldog Print Co reprint. |
| `leases` | `id`, `space_name`, `landlord`, `monthly_rent`, `next_due`, `notes` | The shop's rent obligation. Agents check a rent notice, like ticket 102, against the lease's amount and due date before anyone pays. |
| `cash_accounts` | `name`, `balance`, `date` | The money available to pay bills. Agents must check the balance before approving any payment so the shop doesn't overdraw. |
| `payments` | `id`, `kind`, `ref_id`, `amount`, `account`, `paid_at`, `approved_by` | The record of money going out. It starts empty, and after the Problem 9 runs it holds the two payments a human approved ($840 invoice, $2,400 rent). It shows whether a bill or rent was already paid, so it's never paid twice, and `approved_by` records who signed off. |
| `invoices` | `id`, `vendor_id`, `amount`, `due_date`, `status`, `description` | Vendor bills the shop owes. Agents check `status` and `due_date` to decide what to pay first, for example invoice 501, the overdue $840 reprint that restocks ticket 101's tee. |

## How the three open tickets link to other tables

| Ticket | Type | Links to | What the data shows |
|---|---|---|---|
| 101: Tauhid Zaman, Bulldog tee | customer_order | inventory and pricing (`CC-TEE-WHITE`, S); invoices (501), then vendors (1, Bulldog Print Co) | Size S is out of stock (qty 0). The rush reprint that would restock it is invoice 501: $840, due 2026-08-28, still open (overdue), from a vendor with 5 lead days. |
| 102: Elm City Properties, Rent due | rent_notice | leases (1, Chapel Street shop) and cash_accounts | $2,400 rent is due 2026-09-02. Checking has $3,400. |
| 103: Yale AI Club, Bulk hoodie discount | price_override | inventory and pricing (`CC-HOOD-NAVY`, M) | They want 20 hoodies, but only 8 size M are in stock. List price is $58 and cost is $22, so any discount must stay above $22. |

**Cross-ticket constraint:** paying invoice 501 ($840) plus rent ($2,400) uses $3,240 of the $3,400 in checking, which leaves $160.

## MCP tools (Problem 3)

The `campus-customs-ops` server is in `mcp_server/server.py`, and its README is `mcp_server/README.md`. All three tools read `data/campus_customs_new.db` read-only, take "today" from `desk.date_today` (2026-08-31), and return only what's in the database.

### 1. `check_product`
- **Tables it reads:** `inventory` (qty and location for each `sku` + `size`) and `pricing` (`list_price`, `unit_cost`).
- **Tickets it unlocks:** 101 and 103.
  - **101 (Tauhid Zaman, 1 Classic Bulldog Tee, size S):** `check_product(sku="CC-TEE-WHITE", size="S", quantity_needed=1)` shows S has qty 0, so the order can't ship from stock. Called without `size`, it shows M (5), L (3), and XL (2) are available at $28. It's the right tool because the ticket can only be answered by checking that exact SKU and size against inventory, and the price comes from the same call.
  - **103 (Yale AI Club, 20 Basic Hoodies, size M, bulk discount):** `check_product(sku="CC-HOOD-NAVY", size="M", quantity_needed=20)` returns 8 in stock (12 short), a $58 list price, and a $22 unit cost. It's the right tool because a price override needs both numbers at once: how many we can actually fill, and how far the price can drop before the shop loses money ($36 margin per hoodie).

### 2. `lookup_vendor`
- **Tables it reads:** `vendors` (`name`, `specialty`, `lead_days`).
- **Ticket it unlocks:** 101.
  - **101:** invoice 501 for the size S reprint is billed by vendor 1. `lookup_vendor(vendor_id=1)` shows Bulldog Print Co (apparel reprint) with 5 lead days, so a reprint ordered today would be ready about 2026-09-05. It's the right tool because the size S tee is out of stock, and the only honest answer to "when can I get it?" is the reprint vendor's lead time.
  - It can also find a supplier for 103's missing 12 hoodies with `lookup_vendor(specialty="apparel")`.

### 3. `review_outgoing_payments`
- **Tables it reads:** `invoices` (joined to `vendors` for the payee), `leases`, `payments`, and `cash_accounts`.
- **Tickets it unlocks:** 102 and 101.
  - **102 (Elm City Properties, rent due):** the tool confirms lease 1 rent of $2,400 is due 2026-09-02 (in 2 days). It finds no rent payment in `payments`, so the rent is still unpaid, and checking holds $3,400. It's the right tool because a rent notice arrives as an email: the agent needs to check it against the lease and confirm it's actually unpaid and affordable before anyone pays.
  - **101:** the tool shows invoice 501 ($840 to Bulldog Print Co, due 2026-08-28) is open and 3 days overdue, with no matching payment. It's the right tool because the size S restock depends on this bill, and paying it competes with rent for the same cash.
  - **Combined result:** $840 + $2,400 = $3,240 needed against $3,400 in cash. There's enough to pay both, with $160 left over.

## Agent team (Problem 5)

The code is in `backend/`:
- **Agents:** `agents.py`
- **Data types:** `models.py`
- **MCP connection and per-agent tool access:** `mcp_client.py`
- **Audit trail:** `audit.py`
- **Model and limits:** `config.py`
- **Command-line runner:** `run_tickets.py`
- **Prompts:** one file per agent in `backend/prompts/`

Every agent is a PydanticAI agent on **gpt-6-luna** through Portkey (`PORTKEY_API_KEY`), with the model set by `OPENAI_MODEL`. All shop facts come from the `campus-customs-ops` MCP server over stdio. No agent code touches the database directly.

**Delegation:** every agent has a `delegate(to_agent, task)` tool, so any agent can hand work to any other. In the test run, Inventory asked Accounting about invoice 501, and Accounting asked Inventory about stock.

| Agent | Prompt | Role | MCP tools it can use |
|---|---|---|---|
| **Boss** | `boss.md` | Reads incoming tickets, decides which agents work on each one and what to do, checks their answers against the shop rules, and returns a `TicketPlan`. | `get_tickets`, `update_ticket`, `list_approval_requests` (+ `delegate`) |
| **Inventory** | `inventory.md` | Checks stock for the exact SKU and size, flags shortfalls, and finds which vendor can restock it and how fast. | `get_tickets`, `check_product`, `lookup_vendor`, `update_ticket` (+ `delegate`) |
| **Accounting** | `accounting.md` | Watches cash and invoices, checks margins on sales and discounts, and prepares payments and purchase orders for human approval. | `get_tickets`, `review_outgoing_payments`, `check_discount`, `check_product`, `lookup_vendor`, `request_human_approval`, `list_approval_requests`, `update_ticket` (+ `delegate`) |
| **Facilities** | `facilities.md` | Handles the lease, rent, and running the shop. It checks rent notices against the lease and queues rent payments for approval. | `get_tickets`, `get_lease`, `review_outgoing_payments`, `request_human_approval`, `list_approval_requests`, `update_ticket` (+ `delegate`) |
| **Customer Service** | `customer_service.md` | Drafts customer messages using only customer-safe facts, and queues each draft for a human to okay. | `get_tickets`, `customer_safe_product_info`, `request_human_approval`, `list_approval_requests`, `update_ticket` (+ `delegate`) |

## All MCP tools and the tables they use

| Tool | Tables | Added in | Used by |
|---|---|---|---|
| `check_product` | `inventory`, `pricing` | P3 | Inventory, Accounting |
| `lookup_vendor` | `vendors` | P3 | Inventory, Accounting |
| `review_outgoing_payments` | `invoices`, `vendors`, `leases`, `payments`, `cash_accounts` | P3 | Accounting, Facilities |
| `get_tickets` | `tickets` | P5 | All five |
| `get_lease` | `leases` | P5 | Facilities |
| `check_discount` | `pricing`, `inventory` | P5 | Accounting |
| `customer_safe_product_info` | `inventory`, `pricing` (cost, counts, and aisle removed) | P5 | Customer Service |
| `update_ticket` | `tickets` (writes `status`, `notes`) | P5 | All five |
| `request_human_approval` | `approval_requests` (writes; new table) | P5 | Accounting, Facilities, Customer Service |
| `list_approval_requests` | `approval_requests` | P5 | Boss, Accounting, Facilities, Customer Service |

Every tool also reads `desk` for today's date.

**New table:** `approval_requests` (`id`, `ticket_id`, `action_type`, `summary`, `amount`, `payee`, `draft_message`, `requested_by`, `status`, `created_at`, `decided_by`, `decided_at`, and `final_message`, which the send route adds for the text that actually went out). It's the queue of actions waiting for a human, and `request_human_approval` creates it on first use. A request is `pending` until a human decides it on the board: `approved` for payments, purchases, and price overrides, or `sent` for customer messages. No agent tool can change its status.

## Audit trail

`output/audit_trail.json` gets one JSON object per line, **appended and never wiped**. Each agent-loop step is written as it happens:

| Event | When |
|---|---|
| `agent_started` | An agent begins, with its task and the delegation chain. |
| `model_request` | What went to the model: the prompt, or the tool results. |
| `model_response` | What the model returned: the tool calls with their arguments, or text. |
| `agent_finished` | The agent's final report. |
| `delegation_started` / `delegation_finished` / `delegation_refused` | One agent handing work to another. |
| `agent_error` | An agent's run failed. |
| `crew_finished` / `ticket_resolved` | A run ended with approvals still waiting, or the ticket was resolved (by the run, or by a human's last decision). |
| `payment_approved` / `customer_message_sent` / `price_override_approved` | A human decision on the board, with who made it and, for payments, checking after. |
| `db_reset` | The working database was restored from the original. Earlier lines are kept. |

Every line has a timestamp, `run_id`, `ticket_id`, `agent`, delegation `depth`, the model name, and the running token usage. Long tool results are clipped to 1,500 characters.

## Safety: guardrails and token limits

**Guardrails for real customers and real money:**
1. **No tool can spend money or contact anyone.** The MCP server has no pay, order, or send tool. Payments, purchase orders, discounts, and customer messages can only be queued with `request_human_approval`, and they stay `pending` until a human decides. Agents can't approve their own requests.
2. **Human sign-off for anything outside Campus Customs.** This covers messages to customers, orders with vendors, and payments on invoices or rent. The prompts and the plan's `needs_human_approval` flags make every such step a "Human" step.
3. **Customers only see customer-safe data.**
   - Customer Service has no access to cost, vendor, lease, or cash tools. Its product tool, `customer_safe_product_info`, strips cost, margin, exact counts, and aisle.
   - Before a customer message draft is queued, it's scanned for internal terms (cost, margin, vendor, invoice, rent, lease, cash, and so on). It's also scanned for real vendor names, landlord names, and other customers' names, which are fetched live over MCP. A draft that leaks is sent back to be rewritten.
4. **Least privilege.** Each agent only sees the MCP tools its role needs.
5. **Limited writes.** The writing tools only touch internal records: ticket status and notes, and the approval queue. Agents can't resolve or close a ticket. Read tools open the database read-only. The original `campus_customs.db` is never used.
6. **Business rules in every prompt:**
   - Today is the `desk` date.
   - Verify a bill is unpaid before preparing a payment, so nothing is paid twice.
   - Don't ship an order or promise a restock while its invoice is unpaid.
   - Check a rent notice against the lease before acting on it.
   - Never sell at or below unit cost.
7. **No invented data.** Tools return only database values and say "not found" otherwise. The prompts require every number to come from a tool, and reports list each fact with its source tool.
8. **Duplicate protection.** A second pending approval request of the same type on the same ticket returns the existing one.
9. **Auditability.** Every step, tool call, hand-off, and human decision is in the append-only audit trail. A reset adds one `db_reset` line and never removes earlier ones.
10. **Humans pay, and only once.** Cash changes in one place, the approve route. It checks the request against the real invoice or lease amount, refuses anything already paid, and refuses if checking can't cover it.
11. **No decisions mid-run.** While the crew is working a ticket, the board locks that ticket's approval cards and the backend refuses payments, replies, and price approvals on it. The agents never see a decision land halfway through their run.
12. **Resolved means nothing is waiting.** A ticket is resolved only when none of its approvals is still pending. Until then it stays `awaiting_approval`.
13. **Human edits get the same checks.** An edited customer reply is scanned for internal information before it's sent, and sending is simulated: nothing is emailed. A price override is refused if the price is at or below unit cost.

**Limits that keep token use in check** (`backend/config.py`):

| Limit | Value | What it stops |
|---|---|---|
| Model requests per ticket (all agents combined) | 40 | Runaway agent loops |
| Tool calls per ticket (all agents combined) | 60 | Endless tool calls |
| Total tokens per ticket (all agents combined) | 250,000 | Cost blow-ups |
| Max output tokens per model response | 16,000 (raised from 4,000 after the Boss's final plan hit the cap in the ticket 101 run, because hidden reasoning counts toward it) | Runaway answers |
| Customer Service reasoning effort | low (others use the default) | Runaway deliberation: at the default effort, Customer Service spent 2–3 minutes and up to 16,000 hidden tokens on its final report in the 101 and 103 runs; at low effort it finishes in 6–11 seconds |
| Delegation depth | 3 levels | Deep hand-off chains |
| Delegations per ticket | 10 | Too many hand-offs |
| No delegating to yourself or back up the chain | n/a | Ping-pong loops (refused and logged) |
| Audit text clipping | 1,500 characters | A bloated audit file |

All five agents in one ticket run share one usage counter, so the limits cap the whole ticket, not each agent.

**Test run:** ticket 101 on a scratch copy of the database used 25 model requests, 35 tool calls, and about 81,000 tokens, well within these limits.

## Backend routes (Problem 7)

`backend/main.py` (FastAPI). Start from `backend/` with `uvicorn main:app --reload --port 8000`; try every route at http://localhost:8000/docs.

- `GET /tickets`: the three tickets, each marked open or resolved, with how many approvals are still pending.
- `POST /tickets/{ticket_id}/run`: runs the agent team (Boss first) on one ticket and returns the plan, hand-offs, and token usage. When the run finishes, the ticket is resolved if nothing needs a human, or set to `awaiting_approval` if any approvals are still pending.
- `GET /events?limit=50&ticket_id=&since=`: recent agent events from `output/audit_trail.json`: which agent, what it said, and which tools it called (`since` keeps only the current run, for the live feed).
- `GET /approvals?status=pending&ticket_id=`: the actions agents queued for a human, so the board knows what to approve.
- `POST /approvals/{approval_id}/approve` (body `{"approved_by": "name"}`): a human approves a queued payment or purchase; the only route that moves cash. Resolves the ticket if this was its last pending approval.
- `POST /approvals/{approval_id}/send` (body `{"approved_by": "name", "message": "optional edited text"}`): a human sends a customer reply, as drafted or edited. It's simulated, so nothing is emailed. The final text is checked for internal information first, and the ticket resolves if this was its last pending approval.
- `POST /approvals/{approval_id}/approve-price` (body `{"approved_by": "name"}`): a human approves a discount. It's refused at or below unit cost, and no cash moves.
- `GET /cash`: the current checking balance from `cash_accounts`.
- `POST /reset`: restores `campus_customs_new.db` from the original `campus_customs.db` for a fresh run (the audit trail is kept).

All approval routes refuse a decision on a ticket the crew is still working (409). Every route that changes data also rewrites `output/resolved_tickets.json`.

**Who can pay:** only a human, through the approve route. The agents reach the shop only through MCP tools, none of which can pay, and they can't call these HTTP routes. Before paying, the approve route checks that the request is still pending, is a payment or purchase, matches the real invoice or lease amount, isn't already paid, and that checking can cover it. It then records the payment, lowers checking, marks the invoice paid, closes the request, marks the ticket resolved once nothing else is pending, and adds a `payment_approved` event to the audit trail.

**Test run (scratch copy of the database):** ticket 102 through `POST /tickets/102/run` used 14 model requests, 15 tool calls, and about 40,000 tokens. It queued rent request #1 for $2,400. Approving it paid the rent (checking $3,400 to $1,000) and resolved ticket 102. Approving it again returned 409, and `POST /reset` put everything back. The real `campus_customs_new.db` was not touched.

## Dashboard (Problem 8)

`frontend/` (React + Vite + TypeScript), "The Minion Desk". Start the backend first, then run `npm run dev` in `frontend/` and open http://localhost:5173. The board calls the routes above at http://localhost:8000, and the backend allows the `http://localhost:5173` origin. The look and the reasons behind it are in `output/design.md`.

| Part of the board | What it shows | Routes |
|---|---|---|
| Cash jar | Checking balance; counts down and drains after a payment | `GET /cash` |
| Ticket queue | Open tickets on top, resolved below a divider; Open / Crew working… / Awaiting approval / Resolved | `GET /tickets` |
| Crew | One minion per agent with a speech bubble and status (idle, working, done, error) | `GET /events` |
| Live feed | Every step in the agent's color: tool calls with arguments, hand-offs, reports, human decisions | `GET /events?since=` (polled every 1.5 s during a run) |
| What each minion did | Per-agent summary, hand-offs, tools used, and flags from the latest run | `GET /events?ticket_id=` |
| Human desk | Pay (payments, purchases), Send or Edit (customer replies), Approve price (discounts); locked while the crew works that ticket | `GET /approvals`, the three approval routes |
| Send in the crew / Reset shop data | Starts a run on the selected ticket, or resets the data after a confirm | `POST /tickets/{id}/run`, `POST /reset` |

## Problem 9: the real runs

After a reset (checking $3,400), the three tickets were run on the board. The full comparison with my plan is in `output/desk_tickets.html`, the cash itemization is on its Cash tab, the per-ticket results are in `output/resolved_tickets.json`, and the board screenshots are in `output/resolved_board.html`.

| Ticket | Run | Agents (first call → hand-offs) | Model calls | Tokens | Human decisions | Cash |
|---|---|---|---|---|---|---|
| 101 | `f2e09d3ec4a8` | Boss → Inventory → Accounting; Boss → Accounting; Boss → Customer Service; then a second round of checks | 38 | ~174,000 | Paid invoice 501; sent reply | −$840 |
| 102 | `b49f3ac5a7f1` | Boss → Facilities; Boss → Accounting | 15 | ~43,000 | Paid rent | −$2,400 |
| 103 | `62255fcd7a4d` | Boss → Inventory; Boss → Accounting → Inventory (hand-back refused by the loop guard); Boss → Customer Service (retried once) | 28 | ~109,000 | Approved 15% discount; sent reply | $0 |

Ending checking: $3,400 − $840 − $2,400 = **$160**, matching `cash_accounts`. Every run stayed within the per-ticket limits, though 101 came close: 38 of its 40 model calls, because of the second round of checks.

**What the runs taught me (and what changed):**
- **First 101 run (before the second reset):** the Boss's final plan hit the old 4,000-token output cap. The cap went up to 16,000, and the next 101 run finished cleanly. The failed run is still in the audit trail.
- **101:** I approved the payment and sent the reply while the crew was still working. That led to the lock on mid-run decisions and to the rule that a ticket resolves only when nothing is pending.
- **103:** Customer Service spent about 3 minutes reasoning, hit the token cap, and had to be retried. Customer Service now runs at low reasoning effort and returns its report right after queuing the draft. It takes 6–11 seconds.

**Audit trail:** `output/audit_trail.json` has 297 lines covering all of these runs and decisions, plus two `db_reset` markers. Nothing was removed.

