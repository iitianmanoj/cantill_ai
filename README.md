# Corvo Procurement Hub — Cantill.ai Full-stack Intern Task

Python FastAPI backend + React frontend. Policy rules are stored as versioned JSON in SQLite. Includes batch CSV processing, buyer workspace, decision export, supplier export, chat intake, policy preview/approval, and audit actions.

## Windows local setup

Requires Python 3.12 and Node.js 20+.

Terminal 1:

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload
```

Terminal 2:

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 and http://localhost:8000/docs.

## Private task data

The provided sample data are NOT included in this public-repo-ready ZIP because the task forbids putting task data on public GitHub. Extract your supplied Cantill task kit locally and copy the `master_data`, `contracts` and `pr_batches` folders into `backend/private_data/`. The sample batch can then be uploaded in the UI. For deployment, provision these private data files securely on the backend host; do not commit them.

## API

- `POST /api/process-batch` — multipart field `file` (CSV)
- `GET /api/export/{batch_id}` — decision CSV
- `GET /api/preferred-export?as_of=2026-11-19` — supplier CSV
- `GET /api/decisions`, `POST /api/decisions/{id}/action`
- `GET /api/policy`, `POST /api/policies/preview`, `POST /api/policies`, `POST /api/policies/{id}/approve`
- `POST /api/chat`, `POST /api/chat/create`
- `POST /api/contracts` — manually add contract metadata (contract lines still need to be added to the local CSV)

## Deployment

Backend: deploy `backend` on Render as Python web service; build `pip install -r requirements.txt`, start `uvicorn main:app --host 0.0.0.0 --port $PORT`. Provide private data via persistent storage/secure provisioning. SQLite on ephemeral storage resets on redeploy, so attach a persistent volume or migrate to Postgres for reliable hosted evaluation.

Frontend: deploy `frontend` to Vercel with Vite framework, env `VITE_API_URL=https://YOUR-BACKEND.onrender.com`. Build `npm run build`, output `dist`.

## Limitations

This is an MVP, not a fully verified blind-test solution. Policy upload currently accepts JSON in the UI (not PDF amendments or natural-language updates). Chat is heuristic and does not robustly parse relative dates. Signed PDF-only contracts require manual register and line entry. The policy's effective-date scheduling and per-requirement consumption across separate batches need further hardening. See DECISIONS.md.

## AI Assistance

OpenAI ChatGPT (GPT-6) was used for coding assistance,
debugging, architecture guidance, and documentation.

The procurement decision engine is rule-based and does
not require an external AI model at runtime.

For details, see [APPROACH.md](APPROACH.md).

## Project Links

- GitHub Repository: Add link after pushing
- Live Demo: Add link after deployment