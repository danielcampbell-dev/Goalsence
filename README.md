# GoalSense 3 — Paper Betting

This is the GoalSense 2 Streamlit app plus a **simulation-only** paper betting tab. It does **not** connect to Betfair, access live exchange odds, accept Betfair credentials, or place real bets.

## Deploy update

Upload/replace `app.py`, `paper.py`, `model.py`, `data.py`, `requirements.txt` and `.streamlit/config.toml` in the root of the existing GitHub repository. Commit changes. Streamlit Community Cloud should redeploy the same site URL. Keep `app.py` as the main file path.

## Workflow

1. Open **Paper betting** after the fixture predictions load.
2. Choose a match and manually enter decimal Over 0.5 odds and a virtual stake.
3. Review model probability, simplified break-even probability, and model-based expected profit.
4. Record the simulated bet. Once the game finishes, enter the actual full-time goals to settle it.
5. Export the ledger CSV regularly and restore it later when needed.

The virtual bankroll starts at £1,000. Stakes are capped at £100 per bet. One paper bet per fixture is supported. Session state is **not persistent** and can reset after refresh or sleep; the CSV is your backup. Commission is illustrative, and actual exchange pricing/fees may differ. Match outcomes are not automatically verified. There is no evidence yet that this strategy makes a profit.

## Local run

`pip install -r requirements.txt`

`streamlit run app.py`
