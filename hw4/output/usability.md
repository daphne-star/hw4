Improvements to site

Frontend

- I added a cart feature. The feature allows consumers to add items into a shopping cart and also remove them. This should help consumers keep track of what they're shopping for.

- The chatbot send button isn't disabled while busy, so you can queue duplicate turns against a chatbot. There's also no way to clear the conversation. Fixing this issue  stops the user from spamming the chatbot and the chatbot being swarmed with requests. it also allows the user to use the bot more efficiently by clearing away conversations that aren't useful.

Backend/Agent

- I added more precision in searching. Currently, a quarter-zip tagged "fleece" still ranks for "cheapest fleece," the exact wrong answer in the seeded chat history in the database. To fix this, I made category an exact-match when the user names a garment type.

- I changed the agent so that it recommends what's in stock. Right now, the agent can still confidently suggest a sold-out size. Requiring a stock check before any size-specific recommendation better serves the users' needs.