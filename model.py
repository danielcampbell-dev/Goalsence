"""Leakage-safe, transparent Poisson goal prediction utilities."""
import math
import numpy as np
import pandas as pd

LEAGUES = {
    'Premier League (England)': 'E0',
    'Championship (England)': 'E1',
    'La Liga (Spain)': 'SP1',
    'Bundesliga (Germany)': 'D1',
    'Serie A (Italy)': 'I1',
    'Ligue 1 (France)': 'F1',
    'Primeira Liga (Portugal)': 'P1',
    'Eredivisie (Netherlands)': 'N1',
    'Scottish Premiership (Scotland)': 'SC0',
}

def clean_matches(df):
    required = ['Date', 'HomeTeam', 'AwayTeam', 'FTHG', 'FTAG']
    if not set(required).issubset(df.columns):
        raise ValueError('Results CSV is missing one of: ' + ', '.join(required))
    d = df[required].copy()
    d['Date'] = pd.to_datetime(d['Date'], dayfirst=True, errors='coerce')
    for c in ['FTHG', 'FTAG']:
        d[c] = pd.to_numeric(d[c], errors='coerce')
    d = d.dropna(subset=required).copy()
    d = d[(d.FTHG >= 0) & (d.FTAG >= 0)]
    d = d.sort_values(['Date', 'HomeTeam', 'AwayTeam']).reset_index(drop=True)
    return d

def estimate(history, home, away, recent=12, shrink=6):
    """Existing domestic-league estimator; only use pre-fixture history."""
    if len(history) < 20:
        return None
    h = history[history.HomeTeam.eq(home)].tail(recent)
    a = history[history.AwayTeam.eq(away)].tail(recent)
    if len(h) < 3 or len(a) < 3:
        return None
    lg_home = max(float(history.FTHG.mean()), 0.2)
    lg_away = max(float(history.FTAG.mean()), 0.2)
    def blended(total, n, prior):
        return (total + shrink * prior) / (n + shrink)
    h_attack = blended(h.FTHG.sum(), len(h), lg_home) / lg_home
    h_defence = blended(h.FTAG.sum(), len(h), lg_away) / lg_away
    a_attack = blended(a.FTAG.sum(), len(a), lg_away) / lg_away
    a_defence = blended(a.FTHG.sum(), len(a), lg_home) / lg_home
    lam_h = float(np.clip(lg_home * h_attack * a_defence, 0.15, 4.5))
    lam_a = float(np.clip(lg_away * a_attack * h_defence, 0.15, 4.5))
    return {'prob': 1 - math.exp(-(lam_h + lam_a)), 'home_xg': lam_h,
            'away_xg': lam_a, 'home_games': len(h), 'away_games': len(a)}

def estimate_cup(history, home, away, recent=12, shrink=8, min_team_games=2):
    """UEFA-only estimator using both home and away form when venue-specific data is sparse.

    Never fabricates a team-specific probability when either team has no history.
    All supplied history must predate the fixture.
    """
    if len(history) < 20:
        return None
    home_all = history[(history.HomeTeam == home) | (history.AwayTeam == home)].tail(recent)
    away_all = history[(history.HomeTeam == away) | (history.AwayTeam == away)].tail(recent)
    if len(home_all) < min_team_games or len(away_all) < min_team_games:
        return None
    hh = history[history.HomeTeam.eq(home)].tail(recent)
    aa = history[history.AwayTeam.eq(away)].tail(recent)
    lg_h = max(float(history.FTHG.mean()), .2)
    lg_a = max(float(history.FTAG.mean()), .2)
    league_avg = (lg_h + lg_a) / 2

    def form(team_matches, team):
        home_mask = team_matches.HomeTeam.eq(team)
        scored = np.where(home_mask, team_matches.FTHG, team_matches.FTAG)
        conceded = np.where(home_mask, team_matches.FTAG, team_matches.FTHG)
        n = len(team_matches)
        return ((float(scored.sum()) + shrink * league_avg) / (n + shrink) / league_avg,
                (float(conceded.sum()) + shrink * league_avg) / (n + shrink) / league_avg)

    h_attack, h_defence = form(home_all, home)
    a_attack, a_defence = form(away_all, away)
    lam_h = float(np.clip(lg_h * h_attack * a_defence, .15, 4.5))
    lam_a = float(np.clip(lg_a * a_attack * h_defence, .15, 4.5))
    venue_ready = len(hh) >= 3 and len(aa) >= 3
    if venue_ready:
        full = estimate(history, home, away, recent=recent)
        if full:
            full['method'] = 'venue-specific'
            full['data_quality'] = 'higher'
            return full
    return {'prob': 1 - math.exp(-(lam_h + lam_a)), 'home_xg': lam_h,
            'away_xg': lam_a, 'home_games': len(home_all),
            'away_games': len(away_all), 'method': 'all-venue fallback',
            'data_quality': 'medium' if min(len(home_all), len(away_all)) >= 6 else 'limited'}

def backtest(matches, recent=12, max_matches=450, min_history=100, estimator=estimate):
    """Walk-forward: all inputs are from dates strictly before fixture date."""
    d = clean_matches(matches)
    out = []
    if len(d) < min_history + 10:
        return pd.DataFrame()
    dates = d.Date.drop_duplicates().sort_values()
    for date in dates:
        past = d[d.Date < date]
        if len(past) < min_history:
            continue
        today = d[d.Date == date]
        for _, row in today.iterrows():
            p = estimator(past, row.HomeTeam, row.AwayTeam, recent=recent)
            if p:
                out.append({'Date': date, 'Home': row.HomeTeam, 'Away': row.AwayTeam,
                            'Probability': p['prob'], 'Actual': int(row.FTHG + row.FTAG > 0),
                            'Score': f'{int(row.FTHG)}–{int(row.FTAG)}'})
    return pd.DataFrame(out[-max_matches:])

def metrics(bt):
    if bt.empty:
        return {}
    p = bt.Probability.to_numpy()
    y = bt.Actual.to_numpy()
    return {'n': len(bt), 'brier': float(np.mean((p-y)**2)),
            'logloss': float(np.mean(-y*np.log(np.clip(p,1e-9,1))-(1-y)*np.log(np.clip(1-p,1e-9,1)))),
            'base_rate': float(y.mean()), 'mean_pred': float(p.mean())}
