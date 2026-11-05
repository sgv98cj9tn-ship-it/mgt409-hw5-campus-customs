# AI Prompts

## Problem 1: Vibe coder prompts

### Prompt 1

Do we have the data.zip in the scenario and data section downloaded and ready to use?

## Problem 2: Study the Campus Customs database

### Prompt 1

Duplicate. Campus underscore customs dot db as campus underscore customs underscore new dot db. And create harness.md in output folder.

### Prompt 2

List in harness.md, each table found in campus_customs_new.db, the corresponding fields, and why each table matters for the agent.

## Problem 3: Build the MCP server

### Prompt 1

Build an mcp server using FastMCP in the mcp_server folder. It should only read and write data/campus_customs_new.db for now, not the original, and never invent information. Use the date in the desk table as today’s date. Create three tools for now:

1. check product related information by matching information in inventory and pricing tables.
2. look up vendor information in vendors table
3. Cross match invoices, leases, cash, and payments tables to identify any outgoing payments have been made/are needed, and whether we have enough cash to pay for them

Add to output/harness.md what the tools are, tables it reads, and which ticket(s) from the tickets table it unlocks, and one sentence why it’s the right tool for the ticket. Also creat mcp_server/README.md to explain what the MCP server is for, databases file it uses, and the tools it has. Make sure the server starts.

## Problem 4: Add the MCP server to vibe coder and test each tool

### Prompt 1

Add the MCP server that we just created to this project so that I can use it in this code session. Save the connection JSON text in .mcp.json in the workspace and in Homework 5. Once connected, we’re gonna run a test on each of the three tools and save the evidence in the output folder as mcp_smoke.json file. For every tool test, include the prompt that I asked in order to test, the tool name, and the tool output with matching values from campus_customs_new.db in the JSON file. Here are the tests:

1. Give me information for Classic Bulldog Tee in medium.
2. Which vendor should I use to order more t-shirts?
3. Are there any outstanding payments as of today?

## Problem 5: Build the agent team and grow the MCP tools

### Prompt 1

Build the agents using PydanticAI (pydantic-ai-slim), named Boss, Inventory, Accounting, Facilities, and Customer Service. Use gpt-6-luna through Portkey with the PORTKEY_API_KEY for all the agents. Agent prompts should be in backend/prompts/ with one file per agent, data types should be in backend/models.py, and other agent files should be in the backend folder. The agents should be able to delegate work to each other. Shop facts must come from the MCP server, not straight from the database.

Here are the roles of the five agents. The inventory agent checks product stock information, flags any shortfalls, and figures out which vendor can be used to restock. The accounting agent looks out for the cash that we still have in the bank, any invoices, checks margins on sales and discounts, and prepares payments or purchase orders for human approval. The facilities agent looks out for lease and rent and anything to do with the running of the shop itself. The customer service agent drafts messages for customers. The boss agent looks at the tickets that come in and decides which of the other agents should work on it and what to do.

Some ground rules. Use the date in the desk table as today when deciding what’s overdue. Customers should never receive information regarding the operation side of the shop. For example, they should never know the cost of the product, information about other customers, what vendors we use, or internal information such as the rent and lease. Don’t ship an order or promise a restock while its invoice is unpaid. Any action that requires going beyond Campus Customs, for example sending messages to customers, placing orders with vendors, or making payments to invoices, should be explicitly reviewed and okayed by a human. Never spend money or automatically execute actions that would require payments now or at a later date before a human okays it.

Add any tools that are missing in the MCP server for the agents to do their job, list them for review, and update mcp_server/README.md to match. Every agent-loop step should be appended to output/audit_trail.json, never wiped. In output/harness.md, list each agent and each MCP tool with the table it uses, plus a safety section with guardrails and limits that keep token use in check.


## Problem 6: Plan the three tickets

### Prompt 1

Build desk_tickets.html in the output folder. It’s a page that I can double-click, with one tab per ticket for the 3 tickets, plus empty Cash and Reflection tabs for later problems. Each ticket tab should have an Expected section and an Actual section. Fill the Expected section with what I think will happen, and leave the Actual section as an empty table for after we run the tickets.

Ticket 101: I expect the Boss to call the Inventory robot first to check whether the product is available. Since size S is out of stock and its restock depends on an invoice, I expect Inventory to hand off to the Accounting robot to check whether that invoice is paid. Then the Boss calls the Customer Service robot to draft a reply. Tools: get_tickets, check_product, lookup_vendor, review_outgoing_payments, customer_safe_product_info, request_human_approval, update_ticket.

Ticket 102: I expect the Boss to call the Facilities robot first to verify the rent notice against the lease. Then Facilities hands off to the Accounting robot to check whether our cash covers rent along with the other bills due. Tools: get_tickets, get_lease, review_outgoing_payments, list_approval_requests, request_human_approval, update_ticket.

Ticket 103: I expect the Boss to call the Inventory robot first to check whether 20 are in stock. Then Inventory hands off to the Accounting robot to check the margin on a bulk discount. Then the Boss calls the Customer Service robot to draft a reply. Tools: get_tickets, check_product, lookup_vendor, check_discount, customer_safe_product_info, request_human_approval, list_approval_requests, update_ticket.

## Problem 7: Backend routes

### Prompt 1

Create main.py in the backend folder using FastAPI, with routes that:
1. Return the three tickets and whether each is open or resolved.
2. Take a ticket id and run the agent team on that ticket.
3. Return recent agent events (what each agent said and which tools it used) so the board can refresh.
4. Approve a payment or purchase after a human clicks approve. Agents only prepare payments; this route is the only thing that actually changes cash, and agents must never be able to call it.
5. Return the current checking balance from cash_accounts.
6. Reset the database to the original values for a fresh run.

Once that's done, start the server from the backend folder with `uvicorn main:app --reload --port 8000`. Then, in output/harness.md, list each route on one line with its URL and what it does.

## Problem 8: Agent dashboard

### Prompt 1

Let’s build the frontend dashboard. Put everything in the frontend folder, built with React, Vite, and TypeScript. It should call the backend routes we just built at http://localhost:8000, and the backend should allow the Vite page origin (http://localhost:5173) so the browser can call them. The board should start with npm run dev.
The board should:

* list all three tickets;
* let me pick a ticket and start the agent team on it;
* show each agent and what it’s saying and doing while the ticket runs;
* mark the ticket resolved when the run finishes, still showing any approvals waiting;
* show a short summary of what each agent did on that ticket;
* let a human approve a pay or purchase when asked;
* show the checking balance, which should drop after an approved payment.

Make the agents each look like a different minion from despicable me. Also include a live feed of agent activity, and cash and resolved tickets that stand out clearly.
Create output/design.md describing the dashboard look (the layout, how agents read differently, how resolved tickets and cash show up) and why, including the creative choices.

## Problem 9: Resolve the tickets

### Prompt 1

We're going to start testing the agents. First, reset data/campus_customs_new.db so we start clean, and tell me the starting checking balance. Then I'll run tickets 101, 102, and 103 on the board until each is resolved. After each ticket resolves, I'll tell you, and you take a screenshot of the board for that ticket.

When all three are resolved:
- In output/desk_tickets.html, fill each ticket's Actual section from my runs: which agents worked, what they delegated, and which tools they used. Keep the Expected section unchanged.
- On the Cash tab, itemize the money: the starting checking balance after the reset; for each ticket, how cash changed when it resolved and why (which payment or purchase, and the dollar amount, or why nothing changed); and the ending checking balance, which must match cash_accounts in the working database.
- Create output/resolved_tickets.json with, for each ticket: the id, final status, a short outcome, what each agent contributed, and any human approvals.
- Create output/resolved_board.html, a page I can double-click, with the board screenshot for each resolved ticket.
- Check that my real runs were appended to output/audit_trail.json.
- Finish output/harness.md so it covers the tables, MCP tools, the five agents, API routes, the dashboard, and safety rules.

### Prompt 2

For messages requiring approval before sending to customer, add a send button that sends to message to the cusstomer and an edit button that enables suggested text to be edited right at the human desk and send once completed. (but for our purposes, don't actually send messages or emails out, just mark ticket as resolved and update approriate sections in resolved_tickets.json)

### Prompt 3

Just finished ticket 101, so you can grab the screenshot and add to resolved_board.html. Also add the approval needed for 103

### Prompt 4

Fix the boss error and we'll reset and run 101 again. Make sure when you reset,  audit_trail.json isn't touched

### Prompt 5

Make that fix. But I won't run ticket 101 again

*Note: "that fix" means locking the human desk while the crew is working a ticket. During the 101 run, I approved the $840 payment and sent the customer reply before the agents were done, so the board showed the ticket stamped RESOLVED while it still said "Crew working…". The fix: while a ticket is running, its approval cards show "Available when the crew finishes" instead of buttons, the backend refuses any payment, reply, or price approval on that ticket, and the ticket is marked resolved only when the run itself finishes.*

### Prompt 6

One more change (this may also affect design.md): when a ticket is resolved, move to bottom of the ticket queue on frontend

### Prompt 7

It seems like everytime the customer service agent is involved, thigns get real slow. let's troubleshoot that

### Prompt 8

Don't resolve ticket if there's human approval still needed

## Problem 10: Reflection

### Prompt 1

Update the Reflection tab of output/desk_tickets.html with my thoughts below. Organize them under the five Reflection questions, keep my wording and opinions (don't add ones I didn't give), cite ticket IDs and numbers from the ticket tabs and Cash tab as evidence, and leave questions 3–5 as placeholders for now.

All tickets eventually got resolved, but at what cost? And resolved doesn't always mean the customer was served: ticket 101 ended with no tee for Tauhid and no purchase order queued, so "resolved" only meant nothing was waiting on a human. Every actual first call matched my expectation, but the delegations, especially on 102 and 103, involved the Boss a lot, and I don't know if that was necessary. On 102 the Boss used 42% of the run's tokens on what was really one check. In this app every agent runs the same model, but if the Boss ran on a higher-reasoning model, it would use up more tokens than the other agents, so the better design is to involve the Boss as little as possible while still making sure tasks finish correctly. Ticket 101 took 38 model calls across the team (the Boss made 9 of them), and 17 of the 38 came after I approved the payment mid-run, so some of that cost was caused by me. I think there's room to optimize there.

### Prompt 2

And the ticket 102, maybe that could have been resolved by one agent who's able to see both outgoing payment and verified invoices. As well as standing payments. Involving the facilities agent and the accounting agent separately is much more complicated.

### Prompt 3

Something the agents can't solve right now is to preemptively expect things. For example, the lease is a standing payment, and we have information on how long the lease is for. So we could build a anticipation type tool or like a standing payments agent that look out for or standing payments. Any tickets involving vendors asking for details of orders also can't be resolved. Things that can be resolved. Um, Any other customer inquiries?

### Prompt 4

I could build an agent that automatically triggers daily to check for payments within the week or the month

### Prompt 5

Money coming in. Right now cash only goes down, so the Cash tab shows the $840 and $2,400 going out but nothing coming in. If Yale AI Club pays for the hoodies on 103, nothing records it. And with only $160 left, that matters for whether we can afford the 101 restock. We'd need a way to record sales and payments received, with a human confirming the money came in, and maybe a receivables agent.

### Prompt 6

For question 4, three things the team can already do. One, purchase orders. I could submit a ticket to restock what's short, and the agents find the vendor, figure out the cost, and queue a purchase order for me to approve. That would finish what 101 left hanging. Two, spotting a fake rent bill. Like if an email says rent is now $3,000, Facilities can check the lease, see it's $2,400, and flag it instead of paying. None of our tickets tested that. Three, which bill to pay first. We only have $160 left, so Accounting could look at everything coming due in the next couple months and rank it, without paying anything. Kind of a manual version of the daily payments agent.

## Problem 11: Submit to GitHub

### Prompt 1

We're gonna push the codes to a public GitHub repo now. First create a README that explains how to copy the original DB to the working copy for a clean run, start the MCP server, start the FastAPI backend, start the React board, and reset the DB before a full three-ticket run. Once that's done, update the URL in the github_url.txt in output folder and push that too. And then give me the URL. Make sure when you push it, don't push the real env file, but do include both database files under data so graders can run the app.
