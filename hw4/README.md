# Campus Customs — hw4

## Run locally

Backend:

```powershell
cd backend
python -m pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

The backend reads `../data/campus_customs.db` and serves product images from `../data/products/`. Keep `PORTKEY_API_KEY` in the project environment; never place it in frontend code. The API’s product search and structured results are database-backed, with category and color normalization performed in memory.

## Main API routes

- `GET /api/products` — normalized catalogue and inventory filters.
- `GET /api/products/{product_id}` — database-backed item detail.
- `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me` — account and bearer-session auth.
- `GET /api/chat/history`, `POST /api/chat` — per-user conversation history and structured product results.
