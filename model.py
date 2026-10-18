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
    """Compute expected goals using home/away-specific attack and defence with prior shrinkage.

    Historical matches supplied must be strictly before the target fixture date.
    """
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


def backtest(matches, recent=12, max_matches=450, min_history=100):
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
            p = estimate(past, row.HomeTeam, row.AwayTeam, recent=recent)
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
