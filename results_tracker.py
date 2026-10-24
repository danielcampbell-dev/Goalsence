"""GoalSense results tracker: retrospective scores and saved forecast reconciliation."""
from io import BytesIO
import pandas as pd
import streamlit as st
from model import LEAGUES
from cups import CUPS, canonical_team, get_current_csvs, csv_rows, fetch_history, parse_api_history

SNAPSHOT_COLS = ['Date','League','Home','Away','Over 0.5 probability','Home xG','Away xG']

def snapshot(rank):
    if rank.empty:
        return pd.DataFrame(columns=SNAPSHOT_COLS)
    return rank.reindex(columns=SNAPSHOT_COLS).copy()

def _key(league, date, home, away):
    return (str(league), pd.Timestamp(date).normalize(),
            canonical_team(home), canonical_team(away))

def reconcile(saved, domestic_results, api_key=''):
    """Only match completed results by competition, date and canonical teams."""
    matches = {}
    for league, df in domestic_results.items():
        for _, r in df.iterrows():
            matches[_key(league, r.Date, r.HomeTeam, r.AwayTeam)] = (int(r.FTHG), int(r.FTAG))
    for league in set(saved.League).intersection(CUPS):
        now = pd.Timestamp.now(tz='UTC').tz_localize(None)
        season = now.year if now.month >= 7 else now.year-1
        rows = []
        try:
            rows.extend(csv_rows(get_current_csvs(league, season)['results'], True))
        except Exception as exc:
            st.warning(f'{league}: free current result feed unavailable ({exc}).')
        if api_key:
            # API history can fill gaps for past seasons, subject to the API plan.
            for year in sorted(set(pd.to_datetime(saved.loc[saved.League.eq(league),'Date']).dt.year)):
                for start in (year-1, year):
                    try:
                        rows.extend(parse_api_history(fetch_history(CUPS[league], start, api_key)))
                    except Exception:
                        pass
        for r in rows:
            matches[_key(league,r['Date'],r['HomeTeam'],r['AwayTeam'])] = (int(r['FTHG']),int(r['FTAG']))
    out = saved.copy()
    out['Date'] = pd.to_datetime(out.Date, errors='coerce').dt.normalize()
    actual, outcomes = [], []
    for _, r in out.iterrows():
        score = matches.get(_key(r.League,r.Date,r.Home,r.Away)) if pd.notna(r.Date) else None
        actual.append(f'{score[0]}–{score[1]}' if score else 'Pending / unavailable')
        if not score:
            outcomes.append('Pending')
        else:
            predicted_over = float(r['Over 0.5 probability']) >= 0.5
            actual_over = sum(score)>0
            outcomes.append('Correct' if predicted_over==actual_over else 'Incorrect')
    out['Actual score'] = actual
    out['Over 0.5 result'] = outcomes
    return out

def render(rank, bt, domestic_results, api_key=''):
    st.subheader('Results Tracker — predicted vs actual')
    st.caption('Historical backtests are retrospective. Saved upcoming predictions are a separate, forward-looking check.')
    st.markdown('**Historical match scorelines**')
    if bt.empty:
        st.info('No historical backtest results are available for the selected leagues.')
    else:
        hist = bt.copy().sort_values('Date',ascending=False)
        hist['Predicted over 0.5'] = hist.Probability.ge(.5)
        hist['Correct'] = hist['Predicted over 0.5'].eq(hist.Actual.eq(1))
        a,b,c=st.columns(3)
        a.metric('Backtested matches',len(hist))
        b.metric('Correct over 0.5 calls',int(hist.Correct.sum()))
        c.metric('Outcome accuracy',f'{hist.Correct.mean():.1%}')
        leagues=sorted(hist.League.dropna().unique()) if 'League' in hist else []
        selected=st.multiselect('Filter historical leagues',leagues,default=leagues,key='tracker_hist_leagues')
        if selected:
            hist=hist[hist.League.isin(selected)]
        display=hist.rename(columns={'Score':'Actual score','Probability':'Over 0.5 probability'})
        st.dataframe(display[['Date','League','Home','Away','Over 0.5 probability','Actual score','Correct']],
                     hide_index=True,use_container_width=True,
                     column_config={'Over 0.5 probability':st.column_config.NumberColumn(format='%.1f%%')})
        st.download_button('Download historical results',display.to_csv(index=False).encode(),
                           'goalsense_historical_scores.csv','text/csv')
    st.divider()
    st.markdown('**Track actual results of upcoming predictions**')
    st.info('Download a prediction snapshot BEFORE the games kick off. Upload that same CSV here after the matches finish to compare it with published final scores. This avoids changing forecasts after the fact.')
    snap=snapshot(rank)
    if not snap.empty:
        st.download_button('Save current predictions (CSV)',snap.to_csv(index=False).encode(),
                           'goalsense_saved_predictions.csv','text/csv')
    else:
        st.caption('No current predictions to save. Previously downloaded snapshots can still be uploaded.')
    uploaded=st.file_uploader('Upload a previously saved GoalSense prediction CSV',type=['csv'],key='tracker_snapshot')
    if uploaded is None:
        return
    try:
        saved=pd.read_csv(BytesIO(uploaded.getvalue()))
        required={'Date','League','Home','Away','Over 0.5 probability'}
        if not required.issubset(saved.columns):
            raise ValueError('Missing columns: '+', '.join(sorted(required-set(saved.columns))))
        if len(saved)>10000:
            raise ValueError('Maximum 10,000 saved matches per upload.')
        saved['Over 0.5 probability']=pd.to_numeric(saved['Over 0.5 probability'],errors='coerce')
        saved=saved.dropna(subset=['Date','League','Home','Away','Over 0.5 probability'])
        saved=saved[saved['Over 0.5 probability'].between(0,1)]
        checked=reconcile(saved,domestic_results,api_key)
        finished=checked[checked['Over 0.5 result'].ne('Pending')]
        a,b,c=st.columns(3)
        a.metric('Matched final scores',len(finished))
        b.metric('Still pending / unmatched',len(checked)-len(finished))
        c.metric('Over 0.5 accuracy',f"{finished['Over 0.5 result'].eq('Correct').mean():.1%}" if len(finished) else '—')
        st.dataframe(checked[['Date','League','Home','Away','Over 0.5 probability','Actual score','Over 0.5 result']],
                     hide_index=True,use_container_width=True,
                     column_config={'Over 0.5 probability':st.column_config.NumberColumn(format='%.1f%%')})
        st.download_button('Download matched results',checked.to_csv(index=False).encode(),
                           'goalsense_matched_results.csv','text/csv')
        st.caption('Pending / unavailable means no matching final result was found, not necessarily that the match has not finished. Exact-score accuracy is not reported because GoalSense does not predict exact scorelines.')
    except Exception as exc:
        st.error(f'Could not read saved predictions: {exc}')
