# Image → Text → Translate Webapp

React app for the Scalable Cloud assignment. It uses:

1. **Our API** – Text to multiple languages + CRUD (POST/GET/PUT/DELETE /translate, GET /translations, /health, /languages)
2. **Classmate's API** – Image to text / OCR (POST /ocr with image)
3. **Public API** – Language Tool (grammar/spell check)
4. **Public API** – Free Dictionary API (definitions, examples)
5. **Our API** – Email/password auth (JWT via `/auth/signup`, `/auth/login`, `/auth/verify`)

## Setup

```bash
cd webapp
cp .env.example .env
# Edit .env: set VITE_IMAGE_TO_TEXT_API_URL to your classmate's API base URL
npm install
```

## Run locally

```bash
npm run dev
```

Open http://localhost:5173. Upload an image to extract text (if classmate's API URL is set), or paste text and click Translate.

## Build for production

```bash
npm run build
```

Output is in `dist/`. Deploy that folder to GitHub Pages, Netlify, Vercel, or S3.

## Environment variables

| Variable | Description |
|----------|-------------|
| `VITE_TRANSLATE_API_URL` | Our API base URL (default: Lambda URL) |
| `VITE_IMAGE_TO_TEXT_API_URL` | Classmate's Image-to-Text API base URL (default in code) |

Auth is optional: you can use translate features without logging in; saved notes and account features use JWT from our API.

---

## Deploy to GitHub Pages

The build is set up to work on GitHub Pages (assets use relative paths, so it works when the site is served from `https://username.github.io/repo-name/`).

### 1. Build with your API URLs

The API URLs are **baked in at build time** from your `.env`. So before building:

```bash
cp .env.example .env
# Edit .env: set VITE_TRANSLATE_API_URL and VITE_IMAGE_TO_TEXT_API_URL
npm run build
```

### 2. Push the built site to GitHub

**Option A – Push `dist/` to the `gh-pages` branch**

```bash
# From the repo root (not inside webapp)
cd webapp && npm run build && cd ..
git subtree push --prefix webapp/dist origin gh-pages
# Or: copy dist contents into a branch and push (see Option B)
```

Then in the repo: **Settings → Pages → Source**: choose **Deploy from a branch**, branch **gh-pages**, folder **/ (root)**. The site will be at `https://<username>.github.io/<repo-name>/`.

**Option B – Use GitHub Actions (recommended)**

Create `.github/workflows/deploy-pages.yml` in your repo with the workflow below. It will build the webapp (with env vars you set in the repo’s Secrets) and deploy `dist/` to GitHub Pages so you don’t push built files by hand.

```yaml
name: Deploy to GitHub Pages
on:
  push:
    branches: [main]
permissions:
  contents: read
  pages: write
  id-token: write
concurrency: group: pages
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
      - name: Install and build
        working-directory: webapp
        env:
          VITE_TRANSLATE_API_URL: ${{ secrets.VITE_TRANSLATE_API_URL }}
          VITE_IMAGE_TO_TEXT_API_URL: ${{ secrets.VITE_IMAGE_TO_TEXT_API_URL }}
        run: |
          npm install
          npm run build
      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: webapp/dist
  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment: github-pages
    steps:
      - name: Deploy to GitHub Pages
        uses: actions/deploy-pages@v4
```

Add the env vars as **Secrets** (repo **Settings → Secrets and variables → Actions**): `VITE_TRANSLATE_API_URL` and `VITE_IMAGE_TO_TEXT_API_URL`. Then push to `main`; the workflow will build and deploy. Enable Pages in **Settings → Pages**: Source = **GitHub Actions**.

### 3. After deploy

Your app will be at `https://<username>.github.io/<repo-name>/`. It will call your translate API and the classmate’s API from the browser; make sure those URLs are correct in `.env` (or in Secrets if using Actions).
