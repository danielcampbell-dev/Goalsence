"""Public football-data.co.uk downloads; no API key required. Network access required."""
from datetime import datetime
from io import BytesIO
import pandas as pd
import requests
from model import clean_matches

BASE = 'https://www.football-data.co.uk'
HEADERS = {'User-Agent': 'GoalSense/2.0 (historical football statistics research)'}


def get_csv(url):
    response = requests.get(url, timeout=22, headers=HEADERS)
    response.raise_for_status()
    df = pd.read_csv(BytesIO(response.content), on_bad_lines='skip', low_memory=False)
    if df.empty:
        raise ValueError('Empty CSV returned')
    return df


def season_codes(years=4):
    now = datetime.now()
    start = now.year if now.month >= 7 else now.year - 1
    return [f'{(start-i)%100:02d}{(start-i+1)%100:02d}' for i in range(years)]


def download_results(league_code, seasons=4):
    frames, warnings = [], []
    for season in season_codes(seasons):
        url = f'{BASE}/mmz4281/{season}/{league_code}.csv'
        try:
            raw = get_csv(url)
            cleaned = clean_matches(raw)
            if len(cleaned):
                frames.append(cleaned)
            else:
                warnings.append(f'{season}: no completed results')
        except Exception as exc:
            warnings.append(f'{season}: {type(exc).__name__} downloading results')
    if not frames:
        raise RuntimeError('No historical results could be downloaded. Check network access and source availability.')
    return pd.concat(frames, ignore_index=True).drop_duplicates().sort_values('Date').reset_index(drop=True), warnings


def download_fixtures(league_code):
    raw = get_csv(f'{BASE}/fixtures.csv')
    required = {'Div', 'Date', 'HomeTeam', 'AwayTeam'}
    if not required.issubset(raw.columns):
        raise ValueError('Fixture feed is missing expected columns')
    d = raw[raw.Div.astype(str).eq(league_code)].copy()
    d['Date'] = pd.to_datetime(d.Date, dayfirst=True, errors='coerce')
    today = pd.Timestamp.now().normalize()
    d = d[d.Date.notna() & (d.Date >= today)].copy()
    if 'FTHG' in d.columns and 'FTAG' in d.columns:
        d = d[d.FTHG.isna() | d.FTAG.isna()]
    return d.sort_values('Date').drop_duplicates(['Date','HomeTeam','AwayTeam'])
