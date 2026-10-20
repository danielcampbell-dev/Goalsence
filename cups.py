"""Optional API-Football integration for UEFA club competitions (read-only)."""
from datetime import datetime, timedelta, timezone
import pandas as pd
import requests
import streamlit as st
from model import estimate, backtest, clean_matches

CUPS = {'UEFA Champions League': 2, 'UEFA Europa League': 3, 'UEFA Conference League': 848}
URL = 'https://v3.football.api-sports.io/fixtures'

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_cup(league_id, season, api_key):
    r = requests.get(URL, params={'league': league_id, 'season': season},
                     headers={'x-apisports-key': api_key}, timeout=35)
    r.raise_for_status()
    payload = r.json()
    if payload.get('errors'):
        raise RuntimeError('Data provider error: ' + str(payload['errors'])[:240])
    if not isinstance(payload.get('response'), list):
        raise RuntimeError('Unexpected data provider response')
    return payload['response']

def parse_games(items):
    historical, upcoming = [], []
    for game in items:
        try:
            date = pd.to_datetime(game['fixture']['date'], utc=True).tz_convert(None).normalize()
            home = game['teams']['home']['name']
            away = game['teams']['away']['name']
            status = game['fixture']['status']['short']
            hg, ag = game['goals']['home'], game['goals']['away']
            # Exclude extra time / penalties: model predicts regulation-time total goals.
            score = game.get('score', {}).get('fulltime', {}) or {}
            if status in ('FT', 'AET', 'PEN') and score.get('home') is not None and score.get('away') is not None:
                historical.append({'Date': date, 'HomeTeam':home, 'AwayTeam':away,
                                   'FTHG':score['home'], 'FTAG':score['away']})
            elif status in ('NS', 'TBD') and date >= pd.Timestamp.now(tz='UTC').tz_localize(None).normalize():
                upcoming.append({'Date':date,'HomeTeam':home,'AwayTeam':away})
        except (KeyError, TypeError, ValueError):
            continue
    return historical, upcoming

def get_cup_predictions(selected, seasons, recent, horizon, max_test, api_key):
    ranks, tests, warnings = [], [], []
    year = datetime.now(timezone.utc).year
    current_season = year if datetime.now(timezone.utc).month >= 7 else year-1
    for name in selected:
        all_hist, all_next = [], []
        for season in range(current_season - seasons + 1, current_season + 1):
            try:
                h, f = parse_games(fetch_cup(CUPS[name], season, api_key))
                all_hist.extend(h)
                all_next.extend(f)
            except Exception as exc:
                warnings.append(f'{name} ({season}): {exc}')
        if not all_hist:
            warnings.append(f'{name}: no completed matches returned; check API plan coverage.')
            continue
        hist = clean_matches(pd.DataFrame(all_hist)).drop_duplicates(['Date','HomeTeam','AwayTeam'])
        fixtures = pd.DataFrame(all_next)
        if not fixtures.empty:
            fixtures = fixtures.drop_duplicates(['Date','HomeTeam','AwayTeam'])
            cutoff = pd.Timestamp.now().normalize() + pd.Timedelta(days=horizon)
            fixtures = fixtures[fixtures.Date <= cutoff]
            for _, game in fixtures.iterrows():
                prior = hist[hist.Date < game.Date]
                p = estimate(prior, game.HomeTeam, game.AwayTeam, recent=recent)
                if p:
                    ranks.append({'Date':game.Date.date(),'League':name,'Home':game.HomeTeam,
                                  'Away':game.AwayTeam,'Over 0.5 probability':p['prob'],
                                  '0–0 probability':1-p['prob'],'Home xG':p['home_xg'],
                                  'Away xG':p['away_xg'],'Home sample':p['home_games'],
                                  'Away sample':p['away_games']})
        try:
            test = backtest(hist, recent=recent, max_matches=max_test)
            if not test.empty:
                test['League'] = name
                tests.append(test)
        except Exception as exc:
            warnings.append(f'{name}: backtest failed ({exc})')
    return ranks, tests, warnings
