# GoalSense 3.2 — Read-only Betfair odds + persistent private paper ledger

This version retains the public predictions, historical backtesting, and Supabase-backed private paper ledger from GoalSense 3.1, and adds a **read-only Betfair odds tab**.

## Update your existing Streamlit site

1. Extract this ZIP. Upload `app.py`, `betfair.py`, `paper.py`, `model.py`, `data.py`, `requirements.txt`, and `.streamlit/config.toml` to the same GitHub folder containing your deployed `app.py`. Commit the changes. **Do not upload secrets**.
2. Keep your existing Supabase Streamlit Secrets (`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `PAPER_OWNER_EMAIL`) unchanged. Do not rerun the database schema: there are no database changes.
3. In Streamlit Community Cloud > app > Settings > Secrets, optionally add:

```toml
BETFAIR_APP_KEY = "YOUR_BETFAIR_APPLICATION_KEY"
BETFAIR_SESSION_TOKEN = "YOUR_TEMPORARY_BETFAIR_SESSION_TOKEN"
```

These credentials must be obtained through Betfair's developer API and approved authentication methods. Betfair API access, fees, and permissions depend on account status and current Betfair policies. A session token expires and must be refreshed or replaced. **Never share these credentials, commit them to GitHub, or paste your Betfair password into the app.**
4. Reboot Streamlit if required. Check the new **Betfair odds** tab. The tab should show configuration guidance until valid credentials are provided.

## What it does

- Queries Betfair Exchange **football (eventTypeId 1), OVER_UNDER_05** markets for up to 14 days ahead.
- Retrieves the best currently available *back* offer for the **Over 0.5 Goals** selection.
- Shows an odds snapshot and lets you export it as CSV.
- Uses only Betfair's `listMarketCatalogue` and `listMarketBook` endpoints. **No `placeOrders`, betting execution, or account-funds endpoints are implemented.**
- Keeps the existing private paper ledger and manual odds entry. This deliberately avoids unsafe automatic matching of Betfair events to football-data.co.uk fixture names.

## Known limitations

- **Not an automated value-betting engine yet.** Matching two providers' fixtures requires reliable event identifiers and validation of home/away, kickoff time, and market/selection. A name-only join can lead to incorrect matches.
- Betfair odds retrieval requires the existing private Supabase owner login; public visitors cannot trigger the API calls. Never show tokens in the UI.
- Odds may be delayed, stale, missing, or unavailable depending on key entitlements and liquidity. API throttling and Betfair terms apply.
- Existing paper ledger settlement remains manual. The Supabase balance persists between restarts.
- This app is a research/paper-trading prototype. Probabilities are not proven to be calibrated and there is no claim of betting profitability.
