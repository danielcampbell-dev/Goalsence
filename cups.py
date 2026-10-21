"""UEFA results: API-Football history + competition-specific Open Matchday CSVs.
Read-only; does not interact with Betfair or Supabase.
"""
from io import StringIO
import re
import unicodedata
from urllib.parse import quote
import pandas as pd
import requests
import streamlit as st
from model import estimate_cup, backtest, clean_matches

CUPS = {'UEFA Champions League': 2, 'UEFA Europa League': 3, 'UEFA Conference League': 848}
API_URL = 'https://v3.football.api-sports.io/fixtures'
GITHUB_API = 'https://api.github.com/repos/oladeeayo/open-matchday/git/trees/master?recursive=1'
RAW_ROOT = 'https://raw.githubusercontent.com/oladeeayo/open-matchday/master/'
FREE_HISTORY_SEASONS = (2022, 2023, 2024)
SLUGS = {
    'UEFA Champions League': ('UEFA_1_champions-league',),
    'UEFA Europa League': ('UEFA_1_europa-league',),
    'UEFA Conference League': ('UEFA_1_conference-league',),
}

# Only known-equivalent names should be merged. Expand after reviewing diagnostics.
TEAM_ALIASES = {
    'bayern munchen': 'bayern munich',
    'fc bayern munchen': 'bayern munich',
    'bayern munich': 'bayern munich',
    'paris saint germain': 'paris saint germain',
    'paris sg': 'paris saint germain',
    'psg': 'paris saint germain',
    'inter milan': 'inter milan',
    'internazionale': 'inter milan',
    'inter': 'inter milan',
    'manchester utd': 'manchester united',
    'man utd': 'manchester united',
    'manchester united': 'manchester united',
    'sporting lisbon': 'sporting cp',
    'sporting cp': 'sporting cp',
    'borussia dortmund': 'borussia dortmund',
    'b dortmund': 'borussia dortmund',
    'atletico de madrid': 'atletico madrid',
    'atletico madrid': 'atletico madrid',
    'shakhtar donetsk': 'shakhtar donetsk',
    'shakhtar': 'shakhtar donetsk',
}

def canonical_team(name):
    s = unicodedata.normalize('NFKD', str(name)).encode('ascii', 'ignore').decode('ascii').lower()
    s = s.replace('&', ' and ')
    s = re.sub(r'[^a-z0-9]+', ' ', s).strip()
    return TEAM_ALIASES.get(s, s)

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_history(league_id, season, api_key):
    r = requests.get(API_URL, params={'league': league_id, 'season': season},
                     headers={'x-apisports-key': api_key}, timeout=25)
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
            if status not in ('FT', 'AET', 'PEN') or score.get('home') is None or score.get('away') is None:
                continue
            rows.append({'Date': pd.to_datetime(item['fixture']['date'], utc=True).tz_localize(None).normalize(),
                         'HomeTeam': canonical_team(item['teams']['home']['name']),
                         'AwayTeam': canonical_team(item['teams']['away']['name']),
                         'FTHG': score['home'], 'FTAG': score['away']})
        except (KeyError, TypeError, ValueError):
            continue
    return rows

@st.cache_data(ttl=21600, show_spinner=False)
def discover_csv_paths():
    r = requests.get(GITHUB_API, timeout=25, headers={'Accept': 'application/vnd.github+json'})
    r.raise_for_status()
    data = r.json()
    if data.get('truncated'):
        raise ValueError('GitHub repository file listing was truncated')
    return [x['path'] for x in data.get('tree', []) if x.get('type') == 'blob' and x['path'].lower().endswith('.csv')]

@st.cache_data(ttl=3600, show_spinner=False)
def read_public_csv(path):
    r = requests.get(RAW_ROOT + quote(path, safe='/'), timeout=25)
    r.raise_for_status()
    return pd.read_csv(StringIO(r.text))

def get_current_csvs(name, season):
    paths = discover_csv_paths()
    season_suffix = f'{season % 100:02d}{(season+1) % 100:02d}'
    matching = [p for p in paths if p.lower().startswith('data/') and
                any(p.lower().split('/')[1] == slug.lower() for slug in SLUGS[name]) and
                p.lower().endswith(f'_{season_suffix}.csv')]
    if not matching:
        raise ValueError(f'No matching CSV paths for {name} {season}/{season+1}; repository returned {len(paths)} CSV files; UEFA folder candidates: {[p for p in paths if p.startswith('data/UEFA_')][:12]}.')
    result = {}
    for kind in ('results', 'fixtures'):
        candidates = [p for p in matching if p.split('/')[-1].lower().startswith(kind + '_')]
        if len(candidates) != 1:
            raise ValueError(f'Expected one {kind} CSV for {name}, {season}/{season+1}; found {len(candidates)}: {candidates[:5]}')
        result[kind] = read_public_csv(candidates[0])
    return result

def csv_rows(df, completed):
    rows = []
    required = ['date', 'home', 'away'] + (['ft_home', 'ft_away'] if completed else [])
    if not set(required).issubset(df.columns):
        raise ValueError('Open Matchday CSV schema changed; missing: ' + ', '.join(sorted(set(required)-set(df.columns))))
    for _, g in df.iterrows():
        try:
            date = pd.to_datetime(g['date'], utc=True).tz_localize(None).normalize()
            if not isinstance(g['home'], str) or not isinstance(g['away'], str):
                continue
            if not g['home'].strip() or not g['away'].strip():
                continue
            row = {'Date': date, 'HomeTeam': canonical_team(g['home']), 'AwayTeam': canonical_team(g['away']),
                   'DisplayHome': g['home'].strip(), 'DisplayAway': g['away'].strip()}
            if completed:
                row.update(FTHG=int(g['ft_home']), FTAG=int(g['ft_away']))
                if row['FTHG'] < 0 or row['FTAG'] < 0:
                    continue
            rows.append(row)
        except (TypeError, ValueError, OverflowError):
            continue
    return rows

def get_cup_predictions(selected, seasons, recent, horizon, max_test, api_key):
    ranks, tests, warnings = [], [], []
    now = pd.Timestamp.now(tz='UTC').tz_localize(None).normalize()
    season = now.year if now.month >= 7 else now.year - 1
    for name in selected:
        hist_rows, upcoming_rows = [], []
        api_counts, csv_counts = {}, {}
        if api_key:
            for y in FREE_HISTORY_SEASONS[-max(1, min(int(seasons), len(FREE_HISTORY_SEASONS))):]:
                try:
                    parsed = parse_api_history(fetch_history(CUPS[name], y, api_key))
                    api_counts[y] = len(parsed)
                    hist_rows.extend(parsed)
                except Exception as exc:
                    warnings.append(f'{name} historical {y}/{y+1}: {exc}')
        else:
            warnings.append(f'{name}: API_FOOTBALL_KEY not set; using only current free CSV data.')
        try:
            csvs = get_current_csvs(name, season)
            current_results = csv_rows(csvs['results'], True)
            upcoming_rows = csv_rows(csvs['fixtures'], False)
            hist_rows.extend(current_results)
            csv_counts = {'results': len(current_results), 'fixtures': len(upcoming_rows)}
        except Exception as exc:
            warnings.append(f'{name} current free fixtures/results: {exc}')
        in_window = [r for r in upcoming_rows if now <= r['Date'] <= now + pd.Timedelta(days=horizon)]
        warnings.append(f'{name} diagnostics: historical API matches by season={api_counts}; current CSV rows={csv_counts}; total historical rows={len(hist_rows)}; current fixture rows={len(upcoming_rows)}.')
        warnings.append(f'{name} diagnostics: {len(in_window)} fixtures in the next {horizon} days (including fixtures without model predictions).')
        if not hist_rows:
            warnings.append(f'{name}: no usable historical results available; prediction rows cannot be calculated.')
            continue
        hist = clean_matches(pd.DataFrame(hist_rows)).drop_duplicates(['Date', 'HomeTeam', 'AwayTeam', 'FTHG', 'FTAG'])
        missing, sparse, predicted = [], [], 0
        for row in in_window:
            prior = hist[hist.Date < row['Date']]
            home_count = int(((prior.HomeTeam == row['HomeTeam']) | (prior.AwayTeam == row['HomeTeam'])).sum())
            away_count = int(((prior.HomeTeam == row['AwayTeam']) | (prior.AwayTeam == row['AwayTeam'])).sum())
            p = estimate_cup(prior, row['HomeTeam'], row['AwayTeam'], recent=recent)
            if not p:
                detail = f"{row['DisplayHome']} vs {row['DisplayAway']} ({home_count}/{away_count} prior matches)"
                (missing if min(home_count, away_count) == 0 else sparse).append(detail)
                continue
            predicted += 1
            ranks.append({'Date': row['Date'].date(), 'League': name,
                          'Home': row['DisplayHome'], 'Away': row['DisplayAway'],
                          'Over 0.5 probability': p['prob'], '0–0 probability': 1-p['prob'],
                          'Home xG': p['home_xg'], 'Away xG': p['away_xg'],
                          'Home sample': p['home_games'], 'Away sample': p['away_games'],
                          'Data quality': p['data_quality'], 'Prediction method': p['method']})
        try:
            bt = backtest(hist, recent=recent, max_matches=max_test, estimator=estimate_cup)
            if not bt.empty:
                bt['League'] = name
                tests.append(bt)
        except Exception as exc:
            warnings.append(f'{name} backtest: {exc}')
        warnings.append(f'{name} diagnostics: {predicted}/{len(in_window)} predictions calculated; {len(missing)} fixtures with a team having no matching history; {len(sparse)} fixtures with insufficient history.')
        if missing:
            warnings.append(f'{name} unmatched teams (first 8): ' + '; '.join(missing[:8]))
        if sparse:
            warnings.append(f'{name} sparse history (first 8): ' + '; '.join(sparse[:8]))
    return ranks, tests, warnings
