# GoalSense 3.4 — Hybrid UEFA data

## Installation
Upload the individual files in this folder to the root of your existing GitHub GoalSense app repository (replace app.py and cups.py, retain paper.py, betfair.py, etc.). Keep your existing Streamlit Secrets and Supabase schema. No migration or Betfair changes.

## Sources
- Domestic leagues: unchanged football-data.co.uk feeds.
- UEFA history: API-Football `fixtures` for past seasons allowed by `API_FOOTBALL_KEY`.
- UEFA current fixtures and results: open-matchday public CSV repository, discovered through its GitHub public tree API, no new key required. https://github.com/oladeeayo/open-matchday
- UEFA source updates are not live; the upstream project describes approximately daily/two-day refreshes. This integration is not verified against the live source from this environment. If CSV folder names, season naming or schema differ, open the GoalSense "Download / coverage notes" expander.

## Important limitations
- This does NOT guarantee UEFA predictions: teams may have insufficient home/away history, and API-Football team names may not match the free source. The model deliberately omits such fixtures rather than invent probabilities. A follow-on step is explicit verified team-name alias mapping and optional domestic-to-European model training.
- API-Football free plans may deny some/all historical seasons. Those errors are shown as coverage notes; free current CSV results may still work.
- Public source may be delayed, change its paths, or have missing matches; validate its license/terms for your intended use. The app does not place real bets.
- Refresh downloaded data clears both domestic and UEFA caches. GitHub's unauthenticated API has request limits; cached tree listing lasts 6 hours.

## Secrets
Keep existing SUPABASE_URL, SUPABASE_ANON_KEY, PAPER_OWNER_EMAIL, and Betfair secrets. `API_FOOTBALL_KEY` is optional for current CSVs, required for API-Football historical requests.

## Testing
1. Select UEFA Champions League and unselect domestic leagues; expand Download / coverage notes.
2. Repeat for Europa League and Conference League.
3. If no predictions appear, check whether history was denied or names differed; a blank ranking is not proof fixtures are missing.
4. Confirm Supabase paper betting and Betfair tabs still load; no credentials are stored in the ZIP.
