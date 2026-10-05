CAMPUS CUSTOMS — hw4

SETUP
1. From the hw4 root, create and activate a Python environment if desired.
2. Install backend dependencies:

   python -m pip install -r requirements.txt

3. Copy .env.example to .env and set PORTKEY_API_KEY. Never commit or expose .env.
4. Install frontend dependencies:

   cd frontend
   npm install

RUN THE APP

Terminal 1, from hw4/backend:

   python -m uvicorn main:app --reload --port 8000

Terminal 2, from hw4/frontend:

   npm run dev

Open http://localhost:5173.

The API health check is http://localhost:8000/api/health.
The SQLite database is data/campus_customs.db and product images are served from data/products/.
