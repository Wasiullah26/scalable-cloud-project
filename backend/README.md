# Text-to-Multiple-Languages API

Backend for the scalable cloud assignment: translates input text into multiple languages using a public translation API.

## Run locally

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

- **API docs:** http://localhost:8000/docs  
- **Health:** http://localhost:8000/health  
- **POST /translate:** send JSON `{"text": "Hello world"}` (optional: `source_lang`, `target_languages`). Response includes `id`; the translation is stored for CRUD.
- **GET /translate/{id}:** read a saved translation.
- **PUT /translate/{id}:** update (body: `{"text": "New text"}`; re-translates and updates).
- **DELETE /translate/{id}:** delete a saved translation.
- **GET /translations:** list all saved translations (summary).

**Storage (DynamoDB only):** All data is stored in DynamoDB only; there is no in-memory fallback. Deploy creates two tables: `translations` (saved notes) and `users` (auth). For **local** development, set AWS credentials in `.env` and run `python deploy.py` once (or create the tables in AWS) so the same tables exist; then run `uvicorn app:app --reload --port 8000`. If you use `LAMBDA_ROLE_ARN` (e.g. Learner Lab), add a policy to that role for DynamoDB access on both `translations` and `users` tables (and `users` index `user_id-index`).

**Auth:** JWT login/signup (SettleUp-style): `POST /auth/signup`, `POST /auth/login`, `GET /auth/verify` (Bearer token). Users are stored in the DynamoDB `users` table. Set `JWT_SECRET` in `.env` for production.

## Example

```bash
curl -X POST http://localhost:8000/translate \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world"}'
```

Response: `{"original_text":"Hello world","source_lang":"en","translations":{"es":"...","fr":"...",...}}`

## Deploy to AWS (Lambda + API Gateway)

Deployment is done via a Python script using boto3 (no SAM/Serverless CLI). Works with AWS Learner Lab.

1. **Create a `.env` file** in the `backend/` folder (so you don’t have to export credentials every time):
   ```bash
   cd backend
   cp .env.example .env
   ```
   Edit `.env` and add your AWS credentials (e.g. from Learner Lab):
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   - `AWS_SESSION_TOKEN` (if using temporary/session credentials)
   - `AWS_REGION` (optional, default `us-east-1`)
   - **Learner Lab (no IAM create):** set `LAMBDA_ROLE_ARN` to an existing role ARN (see below).

2. **Run the deploy script** (from the `backend/` folder):
   ```bash
   # Create and activate venv if you haven't already
   python3 -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate

   # Install deps: use -r (required when installing from a file)
   pip install -r requirements.txt

   python deploy.py
   ```
   If `pip` is not found, use: `python3 -m pip install -r requirements.txt` then `python3 deploy.py`. The script loads credentials from `backend/.env` automatically.

3. The script will:
   - Package the app and dependencies into a zip
   - Create or reuse an IAM role for Lambda
   - Create or update the Lambda function
   - Create or reuse an HTTP API in API Gateway and connect it to the Lambda
   - Print the public API URL (e.g. `https://xxx.execute-api.region.amazonaws.com`)

4. **Optional:** You can also set `LAMBDA_FUNCTION_NAME`, `API_NAME`, `LAMBDA_ROLE_NAME` in `.env` to override defaults.

### Using an existing IAM role (e.g. Learner Lab)

If your account cannot create IAM roles, add your existing role ARN to `.env`:

```env
LAMBDA_ROLE_ARN=arn:aws:iam::478098186215:role/YourRoleName
```

**Where to find the role ARN:**
1. In **AWS Console** go to **IAM** → **Roles**.
2. Open the role you use for Lambda (e.g. a lab role or a role you created earlier).
3. At the top of the role page, copy the **Role ARN** (e.g. `arn:aws:iam::123456789012:role/LabRole`).
4. Paste that value into `.env` as `LAMBDA_ROLE_ARN=...`.

The role must allow Lambda to assume it (trust policy: `lambda.amazonaws.com`) and should have at least `AWSLambdaBasicExecutionRole` (or equivalent) for CloudWatch logs.
