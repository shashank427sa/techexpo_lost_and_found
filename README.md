# Fast Find AI — Enhanced Starter

A responsive Flask + SQLite lost-and-found application with private reports, text/photo similarity suggestions, account login, claims, and an admin review center.

## Included features
- Account registration/login with password hashing and logout
- Private lost/found reports (no public directory of found items)
- Image uploads (PNG/JPG/JPEG/WEBP, 5 MB maximum)
- Matching suggestions using TF-IDF/string similarity, category, colour, and perceptual photo hashes
- Match list visible only to owners of either report
- Private ownership claim submission and finder review
- Admin review center for reports, users, and pending claims
- Responsive redesigned UI

## Windows setup (PowerShell)

Install Python 3.11 or 3.12 and Node.js is **not required** for this Flask project. Open PowerShell in the extracted `FastFindAI` folder (the folder containing `app.py` and `requirements.txt`).

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000. If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, then activate again.

If `python` is not recognized, install Python from https://www.python.org/downloads/ and enable **Add Python to PATH**. `py` is optional; commands use `python`.

## Configure an admin account

Before launching the app, set an email that should receive the admin role. Register that exact email in the app.

```powershell
$env:ADMIN_EMAIL = "your-admin-email@example.com"
$env:SECRET_KEY = "replace-with-a-long-random-secret"
python app.py
```

The admin role is assigned when a matching email registers. The admin page is at `/admin`. Do not publish your secret key. For a fresh local test database, stop the app and delete `instance/fastfind.db` before restarting; this removes local test data.

## Try the matching flow
1. Register user A and report a lost item.
2. In another browser/private window, register user B and report a similar found item.
3. Sign in as user A, open Matches, and submit a specific ownership detail as a claim.
4. Sign in as user B and review the claim from Claims.
5. If configured, the admin account can also inspect reports and review claims at `/admin`.

## Important limitations and safety
- Photo comparison uses perceptual hashes (pHash), not a deep-learning semantic vision model. Text comparison uses TF-IDF and string similarity. These are baseline similarity signals, not proof of ownership.
- Claims are manually reviewed. Never expose passwords, full identity documents, or sensitive identifying details in item descriptions.
- Before public deployment, add CSRF protection, rate limiting, email verification, malware/image validation, secure production hosting, HTTPS, a production database, and private object storage. The built-in Flask server is for local development only.
- The app uses SQLite and creates its tables automatically on first run. This starter does not include an external AI API or production-grade identity verification.
