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
from model import estimate_cup, backtest, clean_matches, LEAGUES
from data import download_results

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
    'brighton': 'brighton and hove albion',
    'brighton and hove albion': 'brighton and hove albion',
    'man city': 'manchester city',
    'manchester city': 'manchester city',
    'tottenham': 'tottenham hotspur',
    'tottenham hotspur': 'tottenham hotspur',
    'newcastle': 'newcastle united',
    'newcastle united': 'newcastle united',
    'west ham': 'west ham united',
    'west ham united': 'west ham united',
    'wolves': 'wolverhampton wanderers',
    'wolverhampton': 'wolverhampton wanderers',
    'wolverhampton wanderers': 'wolverhampton wanderers',
    'ath madrid': 'atletico madrid',
    'ath bilbao': 'athletic bilbao',
    'athletic club': 'athletic bilbao',
    'betis': 'real betis',
    'sociedad': 'real sociedad',
    'hearts': 'heart of midlothian',
    'copenhagen': 'fc copenhagen',
    'psv': 'psv eindhoven',
    'leverkusen': 'bayer leverkusen',
    'b monchengladbach': 'borussia monchengladbach',
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

def estimate_cross_cup(history, home, away, recent=12):
    """Conservative cross-UEFA fallback, strictly using pre-fixture results.

    Requires two games for each team across UEFA competitions. A one-game
    estimate is not sufficiently stable to publish as a team prediction.
    """
    p = estimate_cup(history, home, away, recent=recent)
    if p:
        p = dict(p)
        p['method'] = 'cross-UEFA fallback'
        p['data_quality'] = 'limited (cross-competition)'
    return p



@st.cache_data(ttl=3600, show_spinner=False)
def domestic_fallback_data(seasons):
    """Load supported domestic leagues, retaining competition boundaries."""
    frames, errors = [], []
    for league, code in LEAGUES.items():
        try:
            df, _ = download_results(code, seasons=min(int(seasons), 3))
            if df.empty:
                continue
            df = df.copy()
            df['HomeTeam'] = df['HomeTeam'].map(canonical_team)
            df['AwayTeam'] = df['AwayTeam'].map(canonical_team)
            df['DomesticLeague'] = code
            frames.append(df)
        except Exception as exc:
            errors.append(f'{league}: {type(exc).__name__}')
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(), errors)


def estimate_domestic_fallback(uefa_prior, domestic, home, away, fixture_date, recent=12):
    """Experimental fallback using within-league relative team strengths.

    All data is strictly earlier than fixture_date. Each team must have at
    least 3 domestic games in a single league; never pool scoring baselines
    from different domestic competitions.
    """
    import math
    import numpy as np
    if domestic.empty or len(uefa_prior) < 20:
        return None
    past = domestic[domestic.Date < fixture_date]
    strengths = []
    for team in (home, away):
        team_rows = past[(past.HomeTeam == team) | (past.AwayTeam == team)]
        if team_rows.empty:
            return None
        # Prefer the domestic competition with most available matches.
        league = team_rows.DomesticLeague.value_counts().index[0]
        league_rows = past[past.DomesticLeague == league]
        games = team_rows[team_rows.DomesticLeague == league].tail(recent)
        if len(games) < 3 or len(league_rows) < 20:
            return None
        is_home = games.HomeTeam.eq(team).to_numpy()
        scored = np.where(is_home, games.FTHG, games.FTAG).astype(float)
        conceded = np.where(is_home, games.FTAG, games.FTHG).astype(float)
        average = max(float((league_rows.FTHG.mean() + league_rows.FTAG.mean()) / 2), .2)
        shrink = 12
        attack = (float(scored.sum()) + shrink * average) / (len(games) + shrink) / average
        defence = (float(conceded.sum()) + shrink * average) / (len(games) + shrink) / average
        strengths.append((attack, defence, len(games)))
    (ha, hd, hn), (aa, ad, an) = strengths
    # Anchor to UEFA scoring rates, not the domestic leagues' raw goal rates.
    base_h = max(float(uefa_prior.FTHG.mean()), .2)
    base_a = max(float(uefa_prior.FTAG.mean()), .2)
    lam_h = float(np.clip(base_h * ha * ad, .15, 4.5))
    lam_a = float(np.clip(base_a * aa * hd, .15, 4.5))
    return {'prob': 1 - math.exp(-(lam_h + lam_a)),
            'home_xg': lam_h, 'away_xg': lam_a,
            'home_games': hn, 'away_games': an,
            'method': 'experimental domestic-league fallback',
            'data_quality': 'experimental / not backtested'}


def get_cup_predictions(selected, seasons, recent, horizon, max_test, api_key):
    ranks, tests, warnings = [], [], []
    now = pd.Timestamp.now(tz='UTC').tz_localize(None).normalize()
    season = now.year if now.month >= 7 else now.year - 1
    # Pool UEFA histories only when Conference League needs a fallback.
    # Cache/API functions ensure this does not duplicate downloads unnecessarily.
    cross_rows = []
    domestic = pd.DataFrame()
    if 'UEFA Conference League' in selected:
        domestic, domestic_errors = domestic_fallback_data(seasons)
        warnings.append(f'Conference League domestic fallback: {len(domestic)} results from supported domestic leagues; {len(domestic_errors)} league download failures.')
    if 'UEFA Conference League' in selected:
        for other in ('UEFA Champions League', 'UEFA Europa League'):
            if api_key:
                for y in FREE_HISTORY_SEASONS[-max(1, min(int(seasons), len(FREE_HISTORY_SEASONS))):]:
                    try:
                        cross_rows.extend(parse_api_history(fetch_history(CUPS[other], y, api_key)))
                    except Exception as exc:
                        warnings.append(f'{other} cross-UEFA fallback history {y}: {exc}')
            try:
                other_csvs = get_current_csvs(other, season)
                cross_rows.extend(csv_rows(other_csvs['results'], True))
            except Exception as exc:
                warnings.append(f'{other} cross-UEFA fallback current results: {exc}')
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
        cross_hist = hist
        if name == 'UEFA Conference League' and cross_rows:
            cross_hist = clean_matches(pd.DataFrame(hist_rows + cross_rows)).drop_duplicates(
                ['Date', 'HomeTeam', 'AwayTeam', 'FTHG', 'FTAG'])
        missing, sparse, predicted, cross_predicted, domestic_predicted = [], [], 0, 0, 0
        for row in in_window:
            prior = hist[hist.Date < row['Date']]
            home_count = int(((prior.HomeTeam == row['HomeTeam']) | (prior.AwayTeam == row['HomeTeam'])).sum())
            away_count = int(((prior.HomeTeam == row['AwayTeam']) | (prior.AwayTeam == row['AwayTeam'])).sum())
            p = estimate_cup(prior, row['HomeTeam'], row['AwayTeam'], recent=recent)
            if not p and name == 'UEFA Conference League':
                cross_prior = cross_hist[cross_hist.Date < row['Date']]
                p = estimate_cross_cup(cross_prior, row['HomeTeam'], row['AwayTeam'], recent=recent)
                if p:
                    cross_predicted += 1
                else:
                    p = estimate_domestic_fallback(prior, domestic, row['HomeTeam'], row['AwayTeam'], row['Date'], recent=recent)
                    if p:
                        domestic_predicted += 1
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
        if name == 'UEFA Conference League':
            warnings.append(f'{name} diagnostics: {cross_predicted} cross-UEFA and {domestic_predicted} experimental domestic fallback predictions; fallback estimates are not separately backtested.')
        if missing:
            warnings.append(f'{name} unmatched teams (first 8): ' + '; '.join(missing[:8]))
        if sparse:
            warnings.append(f'{name} sparse history (first 8): ' + '; '.join(sparse[:8]))
    return ranks, tests, warnings
