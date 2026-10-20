import pandas as pd
import streamlit as st
from model import LEAGUES, estimate, backtest, metrics
from data import download_results, download_fixtures
from paper import render as render_paper
from betfair import render as render_betfair
from cups import CUPS, get_cup_predictions

st.set_page_config(page_title='GoalSense 3.4 | Goal Predictor', page_icon='⚽', layout='wide')
st.markdown('''<style>.stApp{background:#0b1524;color:#edf3fa}div[data-testid="stMetric"]{background:#15283d;border:1px solid #29415a;border-radius:12px;padding:16px}</style>''', unsafe_allow_html=True)
st.title('⚽ GoalSense 3.4')
st.caption('European football • Over 0.5 total goals • Historical Poisson estimates • Walk-forward backtesting')

with st.sidebar:
    st.header('Settings')
    chosen = st.multiselect('Domestic leagues', list(LEAGUES), default=list(LEAGUES)[:5])
    chosen_cups = st.multiselect('UEFA cup competitions', list(CUPS), default=[])
    seasons = st.slider('Historical seasons to download', 2, 7, 4)
    recent = st.slider('Recent home/away matches per team', 5, 25, 12)
    horizon = st.slider('Upcoming days', 3, 30, 14)
    max_test = st.slider('Backtest sample per league', 100, 1200, 450, step=50)
    refresh = st.button('Refresh downloaded data', use_container_width=True)
    st.caption('Data: football-data.co.uk. Downloads require internet. Match dates use the feed’s calendar dates.')

@st.cache_data(ttl=3600, show_spinner=False)
def results(code, n):
    return download_results(code, n)

@st.cache_data(ttl=1800, show_spinner=False)
def fixtures(code):
    return download_fixtures(code)

if refresh:
    results.clear(); fixtures.clear()
    from cups import fetch_history, discover_csv_paths, read_public_csv
    fetch_history.clear(); discover_csv_paths.clear(); read_public_csv.clear()
if not chosen and not chosen_cups:
    st.info('Choose at least one domestic league or UEFA competition in the sidebar.')
    st.stop()

rankings, bt_frames, notes = [], [], []
progress = st.progress(0, text='Downloading domestic results and upcoming fixtures…') if chosen else None
for i, name in enumerate(chosen):
    code = LEAGUES[name]
    try:
        hist, warnings = results(code, seasons)
        for warning in warnings: notes.append(f'{name}: {warning}')
    except Exception as exc:
        notes.append(f'{name}: results unavailable — {exc}')
        progress.progress((i+1)/len(chosen))
        continue
    try:
        upcoming = fixtures(code)
        until = pd.Timestamp.now().normalize() + pd.Timedelta(days=horizon)
        upcoming = upcoming[upcoming.Date <= until]
        for _, game in upcoming.iterrows():
            # Only use matches before the upcoming fixture, excluding same-day results.
            prior = hist[hist.Date < game.Date]
            p = estimate(prior, game.HomeTeam, game.AwayTeam, recent=recent)
            if p:
                rankings.append({'Date':game.Date.date(), 'League':name,
                    'Home':game.HomeTeam,'Away':game.AwayTeam,
                    'Over 0.5 probability':p['prob'], '0–0 probability':1-p['prob'],
                    'Home xG':p['home_xg'], 'Away xG':p['away_xg'],
                    'Home sample':p['home_games'],'Away sample':p['away_games']})
    except Exception as exc:
        notes.append(f'{name}: fixtures unavailable — {exc}')
    try:
        bt = backtest(hist, recent=recent, max_matches=max_test)
        if not bt.empty:
            bt['League'] = name
            bt_frames.append(bt)
    except Exception as exc:
        notes.append(f'{name}: backtest unavailable — {exc}')
    progress.progress((i+1)/len(chosen))
if progress is not None:
    progress.empty()

if chosen_cups:
    cup_key = st.secrets.get("API_FOOTBALL_KEY", "")
    with st.spinner("Downloading UEFA historical data and free current fixtures…"):
        cup_rank, cup_bt, cup_notes = get_cup_predictions(chosen_cups, seasons, recent, horizon, max_test, cup_key)
        rankings.extend(cup_rank)
        bt_frames.extend(cup_bt)
        notes.extend(cup_notes)

rank = pd.DataFrame(rankings)
bt = pd.concat(bt_frames, ignore_index=True) if bt_frames else pd.DataFrame()

tab1, tab2, tab3, tab4, tab5 = st.tabs(['📅 Upcoming rankings', '📊 Historical accuracy', 'ℹ️ Method and sources', '🧪 Paper betting', '📡 Betfair odds'])
with tab1:
    st.subheader('Upcoming matches ranked by probability of at least one goal')
    if chosen_cups:
        st.caption('UEFA fixtures: free Open Matchday CSV feed; historical UEFA results: API-Football where your plan allows. Only fixtures with sufficient matching history receive predictions.')
    if rank.empty:
        st.warning('No qualifying upcoming fixtures were returned. The public fixture feed may be empty, unavailable, or missing your selected leagues. Try a longer horizon or refresh.')
    else:
        rank = rank.sort_values(['Over 0.5 probability','Date'], ascending=[False,True])
        c1,c2,c3 = st.columns(3)
        c1.metric('Ranked fixtures', len(rank))
        c2.metric('Highest estimate', f'{rank["Over 0.5 probability"].max():.1%}')
        c3.metric('Average estimate', f'{rank["Over 0.5 probability"].mean():.1%}')
        threshold = st.slider('Minimum estimated probability', 0.50, 0.99, 0.75, 0.01)
        view = rank[rank['Over 0.5 probability'] >= threshold].copy()
        st.dataframe(view, hide_index=True, use_container_width=True, column_config={
            'Over 0.5 probability':st.column_config.ProgressColumn('Over 0.5 probability',min_value=0,max_value=1,format='percent'),
            '0–0 probability':st.column_config.NumberColumn('0–0 probability',format='%.1%%'),
            'Home xG':st.column_config.NumberColumn('Home xG',format='%.2f'),
            'Away xG':st.column_config.NumberColumn('Away xG',format='%.2f')})
        st.download_button('Download ranked fixtures (CSV)',view.to_csv(index=False).encode(), 'goalsense_rankings.csv','text/csv')
        st.caption('Estimates are model outputs, not guaranteed outcomes or calibrated betting probabilities.')
with tab2:
    st.subheader('Walk-forward historical backtest')
    if bt.empty:
        st.warning('Insufficient historical results for backtesting.')
    else:
        m = metrics(bt)
        a,b,c,d = st.columns(4)
        a.metric('Test matches',f'{m["n"]:,}')
        b.metric('Observed ≥1 goal',f'{m["base_rate"]:.1%}')
        c.metric('Average predicted',f'{m["mean_pred"]:.1%}')
        d.metric('Brier score ↓',f'{m["brier"]:.4f}')
        st.caption('Lower Brier score is better (0 is perfect). Compare to a constant-rate baseline; no model is guaranteed to beat it.')
        baseline = float(((bt.Actual - m['base_rate'])**2).mean())
        st.write(f'Constant historical-rate baseline Brier: **{baseline:.4f}** · Model log loss: **{m["logloss"]:.4f}**')
        temp = bt.copy()
        temp['Probability bucket'] = pd.cut(temp.Probability,bins=[0,.5,.6,.7,.8,.9,1.00001],labels=['≤50%','50–60%','60–70%','70–80%','80–90%','90–100%'],include_lowest=True)
        calibration = temp.groupby('Probability bucket',observed=False).agg(Predicted=('Probability','mean'),Observed=('Actual','mean'),Matches=('Actual','size')).dropna()
        st.write('**Calibration by prediction band**')
        st.dataframe(calibration.style.format({'Predicted':'{:.1%}','Observed':'{:.1%}'}),use_container_width=True)
        st.bar_chart(calibration[['Predicted','Observed']])
        st.write('**Most recent evaluated fixtures**')
        st.dataframe(bt.sort_values('Date',ascending=False).head(100),hide_index=True,use_container_width=True,
                     column_config={'Probability':st.column_config.NumberColumn(format='%.1f%%')})
        st.download_button('Download backtest (CSV)',bt.to_csv(index=False).encode(),'goalsense_backtest.csv','text/csv')
        st.caption('Only past matches strictly before each match date are used. The model and settings were not tuned on this holdout; testing is retrospective and may still have selection bias.')
with tab3:
    st.markdown('''**Data:** Historical results are downloaded from `football-data.co.uk/mmz4281/{season}/{league}.csv`; upcoming fixtures from `football-data.co.uk/fixtures.csv`. Availability and coverage vary by league and season. No API key is required. The provider is independent of this app.\n\n**Model:** Shrunk, recent home-only and away-only attack/defence strengths are compared with league scoring averages to estimate expected goals for each team. Independent Poisson goal counts imply `P(at least one goal) = 1 − exp(−(home xG + away xG))`.\n\n**Limitations:** No injuries, starting XI, red cards, odds, match context, or live updates. League strength, promoted teams and schedule effects may reduce reliability. Fixture feeds can change or fail. No profit claims. Historical results do not guarantee future performance.\n\n**Backtest:** Chronological walk-forward predictions, with only matches dated earlier than the tested fixture available to the model. Brier score and calibration reveal whether predicted percentages resemble actual frequencies.''')
with tab4:
    render_paper(rank)

with tab5:
    render_betfair()

if notes:
    with st.expander(f'Download / coverage notes ({len(notes)})'):
        for note in notes: st.write('•',note)
