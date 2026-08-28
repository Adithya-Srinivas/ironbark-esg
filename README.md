How to Run Everything

Option 1: Docker (recommended)
Prerequisites: Docker Desktop installed and running.

git clone  < this repo >
cd ironbark-esg
cp backend/.env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
docker compose up --build
Then in a separate terminal, load the data:

docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py ingest_data
docker compose exec backend python manage.py run_ai_classification

Dashboard: http://localhost:3000
API: http://localhost:8000/api/

Option 2: Local
Backend

cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env

# Edit .env with your database credentials and ANTHROPIC_API_KEY

python manage.py migrate
python manage.py ingest_data
python manage.py run_ai_classification
python manage.py runserver
Frontend

cd frontend
npm install
npm run dev
Dashboard: http://localhost:5173

Running tests

cd backend
python manage.py test ingestion api
