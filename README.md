# GoalSense 3.3 — UEFA club competitions

Adds UEFA Champions League, Europa League and Conference League to the existing GoalSense 3.2 app. Keeps domestic competitions, Supabase paper ledger, and read-only Betfair tab.

## Installation
1. Extract this ZIP and upload the **contents** of `GoalSense_3_3` to the same GitHub directory as the existing `app.py`. Replace `app.py`, and add `cups.py`. Commit changes. Keep existing Supabase secrets and database; no schema migration.
2. Register with API-Football (API-Sports) at https://www.api-football.com/ and check whether your plan covers the three UEFA competitions, historical seasons, and upcoming fixtures. Plan limits and availability vary. Obtain your API key.
3. In Streamlit Community Cloud > app > Settings > Secrets, append this TOML setting to your existing settings:

```toml
API_FOOTBALL_KEY = "YOUR_API_FOOTBALL_KEY"
```

Never commit your key or `.streamlit/secrets.toml` to GitHub. Reboot if needed.
4. Open GoalSense; use the **UEFA cup competitions** sidebar filter to select competitions. Select no domestic leagues to view UEFA only.

## Notes
- Data provider: API-Football `fixtures` endpoint; league IDs 2 (Champions League), 3 (Europa League), 848 (Conference League). Requires API key and plan coverage; **not** automatically available from football-data.co.uk domestic CSV feeds.
- Uses historical UEFA match results within each competition for goal estimates, and walk-forward backtesting. A team needs at least three historical home or away games in that competition; insufficient-data fixtures are omitted rather than assigned invented probabilities. Cup-only historical samples can be sparse, especially for new entrants. No cross-league strength adjustment is applied.
- 90-minute results are used for AET/PEN fixtures when available. Matches are labelled with UTC calendar dates; no real betting actions.
- No automatic matching to Betfair odds, and no evidence of calibrated predictive accuracy is claimed. Paper bets remain simulated.
- API-Football has rate limits; cache is 1 hour. Availability of the current season depends on provider updates.
