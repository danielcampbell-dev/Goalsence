# GoalSense 3.1 — public predictions, private paper ledger

## Install on existing Streamlit app
Upload `app.py`, `paper.py`, `data.py`, `model.py`, `requirements.txt`, `.gitignore`, and `.streamlit/config.toml` to the **same GitHub folder** where your deployed `app.py` lives. Keep `supabase_schema.sql` for setup; it can be committed because it contains no secrets.

## Create private Supabase database
1. Create a Supabase project at https://supabase.com/dashboard and wait for it to be ready.
2. Open **SQL Editor**, paste `supabase_schema.sql`, and run it once.
3. In **Authentication > Users**, create/invite **your own email** (confirm it as required). Disable public signups in Auth settings if only you should access the ledger. Set a strong password; enable MFA where available.
4. Find your project URL and **publishable/anon** key in **Project Settings > API Keys**. NEVER use the `service_role`/secret key in the app.
5. In Streamlit Community Cloud > your app > **Settings > Secrets**, enter:

```toml
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_ANON_KEY = "YOUR_PUBLISHABLE_OR_ANON_KEY"
PAPER_OWNER_EMAIL = "YOUR_OWN_EMAIL"
```

Do not commit real secrets to GitHub. Deploy/reboot the Streamlit app. The public rankings/backtesting tabs do not require sign-in; the paper ledger does.

## Verify
1. In a private browser tab, public rankings should work without signing in. Paper tab should require your login.
2. Sign in with your Supabase user and save a £10 virtual bet at odds 1.50 and 2% illustrative commission.
3. Refresh/reboot and sign back in: the record must remain.
4. Settle as 1–0: net paper profit £4.90, bankroll £1,004.90. For 0–0, loss £10 and bankroll £990.
5. Sign out: paper records must not be visible. A different Supabase user must not access your bets; email allowlist and row-level security both apply.

## Limitations and safety
- NO Betfair login, odds feed or order placement. Paper-only simulation.
- This is a single-owner prototype; public users can see predictions but not the ledger.
- Historical data feed and model behavior are unchanged from GoalSense 3.
- Paper bets and manually entered settlement scores persist in Supabase. There is no automatic settlement or official-score verification.
- Starting bankroll is fixed at £1,000. Balances are derived from settled P/L and open stakes, not stored separately.
- Database-level unique fixture key prevents duplicate records. Multiple concurrent sessions could still overspend virtual funds because bankroll checks occur in app code rather than a database transaction.
- Owner can modify own database rows directly with SQL; this is not a tamper-proof audit ledger.
- For production-grade multi-user access, add stricter DB-side state transitions, immutable settlement audit and server-side bankroll enforcement.
