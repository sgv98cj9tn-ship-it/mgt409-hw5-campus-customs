# Campus Customs operations MCP server

## What it's for

This MCP server gives the Campus Customs agent team (Boss, Inventory, Accounting, Facilities, Customer Service) shared, reliable access to the shop's operations data: tickets, stock, prices, vendors, bills, rent, and cash. Every agent gets its shop facts through these tools, never by querying the database directly. Each tool returns only what is in the database and never invents data. If nothing matches, it says so.

Built with [FastMCP](https://gofastmcp.com). Server name: `campus-customs-ops`.

## Database it uses

- **`../data/campus_customs_new.db`**: the working copy of the shop's SQLite database.
- The original `../data/campus_customs.db` is never touched.
- To point the server at another copy (for example a test copy), set the `CAMPUS_CUSTOMS_DB` environment variable.
- "Today" is always `desk.date_today` (2026-08-31), not the computer's clock.
- Read tools open the database read-only. Only two tools write, and both write Campus Customs' own internal records: `update_ticket` (ticket status and notes) and `request_human_approval` (the approval queue). **No tool pays, orders from a vendor, or messages anyone.** Those actions wait in `approval_requests` for a human.
- `request_human_approval` creates the `approval_requests` table the first time it's used.

## Tools (10)

| Tool | Tables | What it does |
|---|---|---|
| `check_product` | `inventory`, `pricing` | Finds products by `sku` or part of the `name`, optionally for one `size`. Returns qty, aisle, in-stock flag, list price, unit cost, and margin. With `quantity_needed`, it says whether stock can fill that amount and the shortfall. **Internal** (shows cost). |
| `lookup_vendor` | `vendors` | Finds vendors by `vendor_id`, `name`, or `specialty`. Returns lead days and `ready_if_ordered_today`. **Internal.** |
| `review_outgoing_payments` | `invoices`, `vendors`, `leases`, `payments`, `cash_accounts` | Lists bills and rent already paid and those needed (overdue or due within `days_ahead`, default 30). Compares them to total cash: enough or not, money left over, and any shortfall. **Internal.** |
| `get_tickets` | `tickets` | Reads one ticket (`ticket_id`), tickets with a given `status`, or all tickets. |
| `get_lease` | `leases` | Reads lease details: landlord, monthly rent, next due date, and days until due. **Internal.** |
| `check_discount` | `pricing`, `inventory` | For a `sku`, `quantity`, and `discount_percent` or `offered_unit_price`, returns the discounted price, margin per unit and in total, whether the price stays above cost, and the deepest discount that still covers cost. With `size`, it also checks stock. **Internal.** |
| `customer_safe_product_info` | `inventory`, `pricing` | The customer-safe view: product name, size, list price, and in stock or not (can we fill `quantity_needed`). It never returns cost, margin, exact counts, aisle, or vendor. |
| `update_ticket` | `tickets` (writes) | Sets a ticket's status (`open`, `in_progress`, `awaiting_approval`, or `blocked`) and/or appends a note signed by the agent. Agents can't resolve or close tickets. |
| `request_human_approval` | `approval_requests` (writes) | Queues a `payment`, `purchase_order`, `customer_message` (with `draft_message`), `price_override`, or `other` action for a human to approve. Nothing is executed. A duplicate pending request for the same ticket and type returns the existing one. |
| `list_approval_requests` | `approval_requests` | Lists pending (default) or all approval requests, optionally for one ticket. |

**How `review_outgoing_payments` decides "paid":**
- An invoice is paid if its `status` is `paid`, or if a payment exists with `kind = "invoice"` and `ref_id` set to the invoice id.
- Rent is paid if a payment exists with `kind = "rent"` and `ref_id` set to the lease id, made within the month before `next_due` or later.

Whoever records payments later (a human) should use these `kind` and `ref_id` values.

## Run it

From this folder, using the Homework 5 virtual environment (`pip install -r ../requirements.txt`):

```bash
../.venv/bin/python server.py
```

That runs it over stdio, which is how Claude Code (`.mcp.json`) and the agent team (`backend/mcp_client.py`) launch it. To serve over HTTP instead:

```bash
../.venv/bin/python server.py --http
```

The HTTP address is http://127.0.0.1:8002/mcp. It uses port 8002 because 8001 belongs to the Lecture 9 server.
