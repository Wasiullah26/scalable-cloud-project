Scalable Cloud Programming (H9SCPRO1) - Project
=================================================

This ZIP contains a React front-end (webapp/) and a FastAPI back-end (backend/)
deployed to AWS Lambda + API Gateway HTTP API with DynamoDB.

Prerequisites
-------------
- Node.js 18+ and npm (for the web app)
- Python 3.9+ (for the API locally and for deploy.py)
- An AWS account with credentials if you deploy or use DynamoDB locally (see backend/.env.example)


1) Back-end API (local)
-----------------------
  cd backend
  python -m venv venv

  Windows:
    venv\Scripts\activate
  macOS / Linux:
    source venv/bin/activate

  pip install -r requirements.txt
  cp .env.example .env
  Edit .env: add AWS credentials and JWT_SECRET if you use auth and DynamoDB.

  uvicorn app:app --reload --port 8000

  Open API docs: http://localhost:8000/docs
  Health check:   http://localhost:8000/health

  Notes:
  - Saved translations and users live in DynamoDB. Create tables by running
    deploy.py once in AWS, or create the tables manually as in deploy.py.
  - Protected routes need a JWT from POST /auth/login after POST /auth/signup.


2) Front-end (local)
--------------------
  cd webapp
  cp .env.example .env
  Optional: set VITE_TRANSLATE_API_URL to your API base URL (no trailing slash).
  Optional: set VITE_IMAGE_TO_TEXT_API_URL for the classmate OCR API base.

  npm install
  npm run dev

  Browser: http://localhost:5173 (Vite default port)


3) Production build (front-end, local test)
--------------------------------------------
  cd webapp
  npm run build

  Output: webapp/dist/  (upload these files to any static host, or use Amplify
  below.)


4) Deploy back-end to AWS (Lambda + API Gateway)
------------------------------------------------
  From backend/, with AWS credentials in the environment or in backend/.env:

  pip install -r requirements.txt boto3 python-dotenv
  python deploy.py

  Copy the printed API base URL (e.g. https://xxxx.execute-api.us-east-1.amazonaws.com).
  You need it for the next step (VITE_TRANSLATE_API_URL).


5) Deploy front-end to AWS (Amplify Hosting) — recommended
----------------------------------------------------------
  The repo includes amplify.yml at the project root so Amplify knows how to
  build from the webapp/ folder.

  Steps (AWS Console):
  a) Deploy the back-end first (section 4) so you have your API URL.
  b) Amplify → Host web app → Connect repository (GitHub/GitLab/Bitbucket).
  c) Pick the branch; Amplify should detect amplify.yml automatically.
  d) App settings → Environment variables (add BEFORE or after first build;
     changing them requires a new build):
       VITE_TRANSLATE_API_URL = your Lambda API base URL (no trailing slash)
       VITE_IMAGE_TO_TEXT_API_URL = classmate OCR base (e.g. .../prod) if needed
  e) Save and deploy. Open the Amplify URL when the build finishes.

  CORS: app.py allows specific Amplify URLs, localhost for dev, and a regex for
  *.amplifyapp.com preview branches. JWT is sent via Authorization header (not
  cookies). If your Amplify URL is different, add it to allow_origins in backend/app.py
  and redeploy (python deploy.py).

  Alternatives (same idea: upload webapp/dist or connect repo):
  - Netlify / Vercel: set the same VITE_* variables in the project settings.
  - S3 static website + CloudFront: upload dist/; set env at build time on your
    machine then upload dist/.


6) Continuous integration
-------------------------
  If you use GitHub, pushing to the repository runs .github/workflows/ci.yml:
  it installs Python and Node dependencies and checks that the API imports and
  the web app builds. This is optional for local work; it supports the project
  report section on CI/CD.


7) What each part calls
------------------------
  - Our API: translate, auth, saved notes (REST).
  - Classmate API: image to text (OCR).
  - Public APIs: Language Tool (grammar), Free Dictionary (definitions).
  - Back-end uses MyMemory for translation (server-side only).


8) Folder layout
----------------
  backend/      FastAPI app, deploy.py, requirements.txt
  webapp/         React + Vite + TypeScript
  amplify.yml     Amplify build (npm --prefix webapp; output webapp/dist)
  .github/        CI workflow (if using GitHub)
