"""UEFA results: API-Football accessible history + keyless Open Matchday current CSVs.

Read-only; does not interact with Betfair or Supabase.
"""
from datetime import datetime, timezone
from io import StringIO
import pandas as pd
import requests
import streamlit as st
from model import estimate, backtest, clean_matches

CUPS = {'UEFA Champions League': 2, 'UEFA Europa League': 3, 'UEFA Conference League': 848}
API_URL = 'https://v3.football.api-sports.io/fixtures'
GITHUB_API = 'https://api.github.com/repos/oladeeayo/open-matchday/git/trees/main?recursive=1'
RAW_ROOT = 'https://raw.githubusercontent.com/oladeeayo/open-matchday/main/'
SLUGS = {'UEFA Champions League': ('champions',), 'UEFA Europa League': ('europa',),
         'UEFA Conference League': ('conference',)}

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_history(league_id, season, api_key):
    r = requests.get(API_URL, params={'league':league_id,'season':season},
                     headers={'x-apisports-key':api_key}, timeout=25)
    r.raise_for_status()
    payload = r.json()
    if payload.get('errors'):
        raise ValueError(str(payload['errors'])[:200])
    return payload.get('response', [])

def parse_api_history(items):
    rows = []
    for item in items:
        try:
            status = item['fixture']['status']['short']
            score = item.get('score', {}).get('fulltime') or {}
            if status not in ('FT','AET','PEN') or score.get('home') is None or score.get('away') is None:
                continue
            rows.append({'Date':pd.to_datetime(item['fixture']['date'],utc=True).tz_localize(None).normalize(),
                         'HomeTeam':item['teams']['home']['name'], 'AwayTeam':item['teams']['away']['name'],
                         'FTHG':score['home'], 'FTAG':score['away']})
        except (KeyError, TypeError, ValueError):
            continue
    return rows

@st.cache_data(ttl=21600, show_spinner=False)
def discover_csv_paths():
    r = requests.get(GITHUB_API, timeout=25, headers={'Accept':'application/vnd.github+json'})
    r.raise_for_status()
    data = r.json()
    if data.get('truncated'):
        raise ValueError('GitHub repository file listing was truncated')
    return [x['path'] for x in data.get('tree', []) if x.get('type') == 'blob' and x['path'].lower().endswith('.csv')]

@st.cache_data(ttl=3600, show_spinner=False)
def read_public_csv(path):
    r = requests.get(RAW_ROOT + path, timeout=25)
    r.raise_for_status()
    return pd.read_csv(StringIO(r.text))

def get_current_csvs(name, season):
    paths = discover_csv_paths()
    season_suffix = f'{season % 100:02d}{(season+1) % 100:02d}'
    matching = [p for p in paths if p.lower().startswith('data/') and
                any(word in p.lower().split('/')[1] for word in SLUGS[name]) and
                p.lower().endswith(f'_{season_suffix}.csv')]
    # Never silently substitute another competition or season.
    result = {}
    for kind in ('results', 'fixtures'):
        candidates = [p for p in matching if p.split('/')[-1].startswith(kind+'_')]
        if not candidates:
            raise ValueError(f'No {kind} CSV found for {name}, {season}/{season+1}')
        result[kind] = read_public_csv(sorted(candidates)[0])
    return result

def csv_rows(df, completed):
    rows=[]
    required = ['date','home','away'] + (['ft_home','ft_away'] if completed else [])
    if not set(required).issubset(df.columns):
        raise ValueError('Open Matchday CSV schema changed; missing: '+', '.join(set(required)-set(df.columns)))
    for _,g in df.iterrows():
        try:
            date = pd.to_datetime(g['date'], utc=True).tz_localize(None).normalize()
            if not isinstance(g['home'],str) or not isinstance(g['away'],str): continue
            row = {'Date':date,'HomeTeam':g['home'].strip(),'AwayTeam':g['away'].strip()}
            if completed:
                row.update(FTHG=int(g['ft_home']),FTAG=int(g['ft_away']))
                if row['FTHG']<0 or row['FTAG']<0: continue
            rows.append(row)
        except (TypeError,ValueError,OverflowError):
            continue
    return rows

def get_cup_predictions(selected, seasons, recent, horizon, max_test, api_key):
    ranks, tests, warnings = [], [], []
    now = pd.Timestamp.now(tz='UTC').tz_localize(None).normalize()
    season = now.year if now.month >= 7 else now.year-1
    for name in selected:
        hist_rows, upcoming_rows = [], []
        if api_key:
            for y in range(season-seasons+1, season):
                try:
                    hist_rows.extend(parse_api_history(fetch_history(CUPS[name],y,api_key)))
                except Exception as exc:
                    warnings.append(f'{name} historical {y}/{y+1}: {exc}')
        else:
            warnings.append(f'{name}: API_FOOTBALL_KEY not set; using only current free CSV data.')
        try:
            csvs = get_current_csvs(name, season)
            hist_rows.extend(csv_rows(csvs['results'], True))
            upcoming_rows.extend(csv_rows(csvs['fixtures'], False))
        except Exception as exc:
            warnings.append(f'{name} current free fixtures/results: {exc}')
        if not hist_rows:
            warnings.append(f'{name}: no usable historical results available.')
            continue
        hist = clean_matches(pd.DataFrame(hist_rows)).drop_duplicates(['Date','HomeTeam','AwayTeam','FTHG','FTAG'])
        # Provider spellings can differ. Current-season team names are canonical for prediction.
        # Never merge similarly named teams using fuzzy matching without verification.
        for row in upcoming_rows:
            if not (now <= row['Date'] <= now + pd.Timedelta(days=horizon)):
                continue
            prior = hist[hist.Date < row['Date']]
            p = estimate(prior,row['HomeTeam'],row['AwayTeam'],recent=recent)
            if p:
                ranks.append({'Date':row['Date'].date(),'League':name,'Home':row['HomeTeam'],
                              'Away':row['AwayTeam'],'Over 0.5 probability':p['prob'],
                              '0–0 probability':1-p['prob'],'Home xG':p['home_xg'],
                              'Away xG':p['away_xg'],'Home sample':p['home_games'],
                              'Away sample':p['away_games']})
        try:
            bt = backtest(hist,recent=recent,max_matches=max_test)
            if not bt.empty:
                bt['League']=name
                tests.append(bt)
        except Exception as exc:
            warnings.append(f'{name} backtest: {exc}')
        if not any(r['League']==name for r in ranks):
            warnings.append(f'{name}: no qualifying predictions; sparse UEFA-only team history or differing provider team names. Fixtures may exist but are not assigned fabricated probabilities.')
    return ranks, tests, warnings
