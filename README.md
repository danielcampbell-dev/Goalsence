# GoalSense — hosted website deployment

This repository is ready to deploy to Streamlit Community Cloud. It contains the Streamlit app, data download functions, model, requirements, and theme settings.

## Publish it
1. Create or sign in to a GitHub account and create a new repository (e.g. `goalsense`).
2. Upload all files from this folder to the **root** of the repository, including the `.streamlit/config.toml` file. Do not upload the enclosing folder instead.
3. Visit https://share.streamlit.io/ and sign in with GitHub.
4. Choose **Create app**, select the repository, branch `main`, and entrypoint `app.py`.
5. Choose an available subdomain and deploy. The service will install `requirements.txt` and launch the site.
6. Test rankings and backtesting. If the data provider fails or has no fixtures, the app displays a warning rather than inventing predictions.

Public Community Cloud deployments may expose source code and have usage/resource limits. Hosting, data availability, and the chosen subdomain are subject to the provider. This package does not itself publish the website; deployment requires authorization through your GitHub/Streamlit account.

## Data and model
Historical football-data.co.uk CSV feeds and upcoming fixtures are downloaded when the app runs and cached for 1 hour / 30 minutes respectively. The app ranks fixtures by estimated Over 0.5 goal probability and performs walk-forward historical backtesting. Predictions are unverified statistical estimates, not guaranteed outcomes.
