# hw4 AI Prompts

This file stores the exact prompts provided for the hw4 work session.

## Section 2

Ground yourself in the real data. Before writing any code, open data/campus_customs.db, print the full schema and ~10 sample rows from each table, and build against what you find. Do not invent columns. Existing tables: catalogue (102 products), inventory (612 rows, 6 sizes per product), users, chat_messages. Extend the schema only if you explain why.

## Section 3

Build a customer-facing web app for Campus Customs, a Yale merch store. React + Vite + TypeScript front end, Python FastAPI backend (backend/main.py), with a PydanticAI agent as the chatbot brain.

WEB APP FEATURES
- There should be a navigation bar at the top of the web app that links to the main pages: home, products, about us, log in, and create account.
- Home and About Us Pages: please selectively take text from yalebulldogblue.com and paraphrase them for this web app's Home and About Us Pages.
- Products Page: product grid with images from data/products/, filters for category, color, size availability, and price. Clicking on each product should open its individual item page.
- Individual item pages: should have a large image of the product on the left side and text on the other side. The text should include description, price, sizes/stock.
The app should use the product information in the database and should not make up information on its own.

Known data quirks you must handle:
- garment_type is free text: 22 distinct strings covering ~6 real categories (t-shirt, crewneck, hoodie, quarter-zip, fleece/jacket, long-sleeve). Casing and phrasing vary. Normalize on read; don't edit the table.
- colors and search_tags are JSON-encoded arrays stored as TEXT. "navy" and "navy blue" are the same color; several gray variants exist. Three products have an empty colors array — the UI must not break.
- Price is fully determined by garment type: $32 t-shirts, $45 long-sleeve, $58 crewneck, $68 hoodie, $72 quarter-zip, $88 full-zip hoodie, $98 fleece.
- Accounts: create account (takes in first name, last name, email, and password; adds them to the user database) + login (Takes in email and password and verified against database). Password hashes must use the existing format, pbkdf2_sha256$<salt>$<64-char hex>, so the three seeded users still work. Session/JWT auth; chat history is per-user.
- Chat: This interface should be on the bottom right of the website at all times. POST /chat returns BOTH prose and a structured product list. Store every turn to chat_messages, storing the product list in products_json exactly as the existing rows do. Load prior turns on page load so the agent has conversation context.
- The returned product list drives a live results panel next to the chat — when the agent finds items, the page updates. This is the core interaction; don't settle for product names in markdown.

## Section 3

Use PydanticAI with tools over the local DB — search_products, get_product, check_stock. Rules:

- The agent may only state a price, color, or stock level that came back from a tool call in the current turn. Never from memory or inference.
- If a tool returns nothing, say so plainly and offer a related search. Do not substitute a near-match and present it as the answer. Specifically: a quarter-zip is not a fleece — "cheapest fleece" must filter on normalized category, not on tag text.
- Resolve pronouns ("do you have this in pink?", "this hoodie is cool right") against the products shown in recent turns.
- Address the logged-in user by their first name.

The API app should be in the backend main.py. There should also be prompt.md for the system prompts, agent.py, tools.py, and models.py.

## Section 4

update the harness to say how password auth works, the safety rules for the user database, how the frontend talks to the fastapi, and how the agent is loaded.

## Section 5

The agent should be able to look up product description, price, the amount in stock (and by size if the user asks) from the database. The agent can also use the search tags during the search. When the user asks about specific products, the agent should be able to answer accordingly. The agent should only use the product information in the database to answer questions and should not make up information on its own.

## Section 6

update prompt.md so the agent knows to call the tools for price and stock questions. add return types in models.py. in the harness, list the tools and explain the model types.

## Section 7

When the agent is returning products as answers to the user, it should also show a list of those product cards floating on the website (the actual website should be in a muted tone behind the returned product cards). These product cards should also be openable to the corresponding individual product pages that we built before.

Update prompt.md and the harness so it's clear how the results reach the page.

## Section 8

give the chat agent persistent memory of the conversation, a real sense of who it's talking to, and awareness of the page the user is on. Use bounded per-user message history, server-derived identity context, validated page context, and the prompt resolution order for “this”, “that one”, and “it” described in the request.

## Section 9

In "HW 4", make the agent enforce in code what prompts/prompt.md currently only
asks for in prose. Read backend/tools.py, backend/models.py, backend/agent.py,
backend/main.py and frontend/src/main.tsx first.
PART 1 — hard category gate. prompt.md says "A quarter-zip is not a fleece," but search_products() in tools. pyscores every product against a haystack that includes search_tags, so a quarter-zip tagged "fleece" still ranks for "cheapest fleece." The rule is advisory; the tool ignores it.
Make it structural: a) In search_products(), detect a garment-type term in filters.query and  apply itas a hard filter, exactly as filters.category already is. Map against the normalized set: t-shirt, long-sleeve, crewneck, hoodie, full-zip hoodie, quarter-zip, fleece/jacket. Reuse _category() — do not write a second mapper. b) When a garment type is detected, products of other categories must be excluded outright, even if their search_tags match the term. c) Keep tag matching for everything that is not a garment type (Yale groups, colors, sports, "bulldog", residential colleges) — that is working well. d) Return a field on each result saying which category gate was applied, so the agent can tell the customer "no fleece jackets under $80" instead of silently substituting.
PART 2 — stock the agent can actually reason about.
search_catalogue returns up to 8 products, each carrying all 6 raw inventory rows.
That is 48 rows of JSON per search for the model to parse, and nothing summarizes
it, so the agent can recommend an item that is sold out in the size being
discussed.
a) In _product(), add in_stock_sizes and sold_out_sizes as plain string lists
alongside the existing inventory array. Keep inventory — the frontend uses it.
b) Add a total_in_stock integer.
c) In prompt.md, require that whenever a customer names a size, the reply states
that size's availability explicitly, and that a sold-out item is never
recommended without saying it is sold out.
PART 3 — fix the page context that feeds both of these.
In frontend/src/main.tsx, send() builds context with product_id hardcoded to null
and route derived from page, which never becomes 'product' because ProductPage
is a separate route. Derive route and product_id from the actual router location
so that on /product/:id the agent receives route:'product' and that product_id.
CONSTRAINTS:
- Do not change the catalogue, inventory, users, sessions or chat_messages schemas.
- Keep the model as gpt-5.6-luna via Portkey, key read from the environment at
  runtime; never hard-code, print, or commit it.
- Keep the answered_by flag and the logger.exception path in /api/chat.
- Do not touch auth or password hashing.
VERIFY and show me the before/after for each: "whats your cheapest fleece?"  → must return a fleece/jacket, never the School of Art quarter-zip at $72 "show me hoodies"              → still returns the 27 hoodie-family items "anything with bulldog on it?" → tag matching must still work "do you have the big yale hoodie in XS?" → must state that size's stock On /product/basic-hoodie-big-yale ask "do you have this in navy?" → must resolve from page context

In "HW 4" frontend/src/main.tsx, add loading affordances and chat input guards.
PART 1 — loading states.
a) The product grid has none. api('/api/products?'+query).then(setProducts)
swaps the grid with no pending flag, so a filter change looks like nothing
happened and a slow request looks broken. Add a loading flag, and while it is
true render 8 skeleton cards that match .card's existing footprint — same
aspect-ratio image block and text line heights — so the grid does not reflow
when real data lands.
b) ProductPage has a text-only "LOADING / Finding your…" state. Replace it with a
skeleton matching the real detail layout, for the same reason.
c) Add aria-busy on the grid container and a visually-hidden live region that
announces "Loading products" then "N products" so the state is not purely
visual.
d) While loading, keep the previous results visible and dimmed rather than
clearing to empty — avoids a flash of nothing on every filter change.
PART 2 — chat composer guards.
In the whole file disabled appears exactly once, on the auth submit button. The
chat composer has none.
a) Disable the send button and the input while busy, and ignore the Enter
handler while busy, so a slow agent turn cannot be queued twice.
b) Replace the bare .pulse dot with a visible assistant typing indicator in the
message list, so it is clear a reply is coming.
c) On a failed turn, do not push the error into the transcript as if the
assistant said it. Show it as a distinct error row with a Retry button that
resends the same message.
d) Add a "Clear conversation" control in the chat header. It should clear the
on-screen transcript. Ask me before deleting any stored chat_messages rows —
I want to decide whether clearing is visual-only or also server-side.
e) Trim empty/whitespace-only messages before sending.
CONSTRAINTS:
- Keep the pastel look. Reuse the existing classes in styles.css and
  floating.css — .card, .grid, .composer, .messages, .chat-title, .pulse,
  .primary, .eyebrow. Soft pastel colors, gentle borders, restrained rounded
  corners. Do not restyle the site.
- Do not change any API contract or backend file.
- Keep the floating product cards and their links to /product/:id working.
VERIFY: throttle the network to Slow 3G, change a filter, and confirm skeletons
appear without layout shift; send a chat message and confirm the input locks and
double-Enter sends only one turn; kill the backend and confirm a failed turn shows
a retry affordance rather than a fake assistant reply.

# Section 10

make the following visual changes:
- the cursor when you hover above the page should be that of a bulldog.
- the floating window should display the names of the products in
- when my mouse hovers over a product item in the floating window, it should display a preview window with the product. When I click on the product item in the floating window, the large item page with the single item should appear above the list of products and cover the list.
- add a shopping cart feature and add it to the navigation bar. logged in users should be able to add in stock items to the cart and remove them from the cart.

# Section 11

using the three images in app_check_images, create a simple html with corresponding headlines and leave space for me to write a one-to-two-sentence caption for each image.