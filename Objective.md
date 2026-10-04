Your seat
Seat 14 · Project Agent

Projects

Which projects are behind, and who is overloaded.

The questions it must answer

Which projects are behind?

project.behind_schedule

Who is overloaded next week?

project.overloaded_next_week

A tick means a predicate already checks that answer against the database. An empty circle means nothing verifies it yet — that is the work.

What already exists
The data. One shared database, the same for every team. All 36 seats and 65 goals are already defined.
The API. Full CRUD over every entity, plus the module endpoints. Nothing needs to be built to read or write business data.
The runtime. Sessions, jobs, approvals, tool policies and the audit trail. Your agent runs inside it rather than beside it.
The evaluator. 17 of 65 goals have a predicate that decides, from the database alone, whether the answer was right.
What you build
One agent, for your seat, that answers its questions using this API. You run it on your own machine with your own model keys. Answers are judged by the seat's predicate against real data — not by how the reply reads, so an agent that sounds right and gets the number wrong fails.

What you may change
Yours: your agent's code, prompts, tools, planning, retries and model choice.
Ask first: the harness itself — the runtime, the predicates, the schemas. If your seat genuinely cannot be done without a change there, report it as a bug with the case that proves it, and it gets fixed for everyone rather than forked.
Never: another team's agent, or the shared data as a way of making your own goal pass. Every write is attributed in the audit trail.
When something is broken
Use the bug button in the header, on the screen where it happened. Say what you did, what you expected, and what happened instead — a report that cannot be reproduced cannot be fixed.

Reference
API explorer(https://agentswitch.theschoolofai.in/docs) Every endpoint, grouped by app. Try calls in the browser.
API reference(https://agentswitch.theschoolofai.in/redoc) The same surface, laid out for reading rather than poking.
Entity schemas(blob:https://agentswitch.theschoolofai.in/234cc7d6-9192-4cf1-9fd7-e636ca718779) Fields, types, options and required lists for all entities.
Agent tools(blob:https://agentswitch.theschoolofai.in/571beb79-6bf1-4a77-8d62-5c30f4a3197e) The tools an agent may call, each with its JSON Schema.