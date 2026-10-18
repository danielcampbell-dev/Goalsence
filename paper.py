"""Simulation only. No Betfair authentication or order endpoints."""
import io
import pandas as pd
import streamlit as st

COLUMNS = ['Date','League','Home','Away','Probability','Odds','Stake','Status','Home goals','Away goals','Profit']

def start_ledger():
    if 'gs_paper_ledger' not in st.session_state:
        st.session_state.gs_paper_ledger = pd.DataFrame(columns=COLUMNS)

def render(rank):
    st.subheader('🧪 GoalSense 3 — Paper betting')
    st.warning('SIMULATION ONLY — no connection to Betfair and no real-money orders. Odds must be entered manually or imported. No credentials are needed.')
    st.caption('Your ledger is held in this browser session only. Download it regularly; it may disappear on refresh, server restart or app sleep. You can restore it using CSV.')
    start_ledger()
    ledger = st.session_state.gs_paper_ledger
    with st.expander('Restore a saved paper ledger'):
        restored = st.file_uploader('Upload previously exported ledger CSV', type='csv', key='paper_restore')
        if restored is not None and st.button('Restore ledger'):
            try:
                imported = pd.read_csv(restored)
                if not set(COLUMNS).issubset(imported.columns):
                    st.error('CSV does not contain all required ledger columns.')
                else:
                    st.session_state.gs_paper_ledger = imported[COLUMNS].copy()
                    st.rerun()
            except Exception as e:
                st.error(f'Cannot restore file: {e}')
    ledger = st.session_state.gs_paper_ledger
    settled = ledger[ledger.Status.eq('Settled')] if not ledger.empty else ledger
    pnl = pd.to_numeric(settled.Profit, errors='coerce').fillna(0).sum() if not settled.empty else 0.0
    pending = ledger[ledger.Status.eq('Open')] if not ledger.empty else ledger
    exposure = pd.to_numeric(pending.Stake, errors='coerce').fillna(0).sum() if not pending.empty else 0.0
    a,b,c,d = st.columns(4)
    a.metric('Starting virtual bankroll', '£1,000')
    b.metric('Realised paper P/L', f'£{pnl:,.2f}')
    c.metric('Open paper stakes', f'£{exposure:,.2f}')
    d.metric('Available virtual funds', f'£{1000+pnl-exposure:,.2f}')
    st.markdown('#### Add a simulated bet')
    if rank.empty:
        st.info('No upcoming ranked fixtures loaded. Try other leagues or a longer fixture window.')
    else:
        r = rank.reset_index(drop=True)
        choice = st.selectbox('Fixture', range(len(r)), format_func=lambda i: f"{r.iloc[i]['Date']} · {r.iloc[i]['Home']} v {r.iloc[i]['Away']} ({r.iloc[i]['League']})")
        fixture = r.iloc[choice]
        probability = float(fixture['Over 0.5 probability'])
        x,y = st.columns(2)
        odds = x.number_input('Decimal Over 0.5 odds (manual)', min_value=1.01, max_value=100.0, value=1.20, step=.01, format='%.2f')
        stake = y.number_input('Virtual stake (£)', min_value=1.0, max_value=100.0, value=5.0, step=1.0)
        fee = st.slider('Illustrative commission on net winnings (%)', 0.0, 10.0, 2.0, 0.5)
        break_even = 1 / (1 + (odds-1)*(1-fee/100))
        net_win = stake * (odds-1) * (1-fee/100)
        ev = probability * net_win - (1-probability)*stake
        st.write(f'Model probability: **{probability:.1%}** · Break-even probability after illustrative commission: **{break_even:.1%}** · Model-based expected P/L: **£{ev:+.2f}**')
        st.caption('These estimates are not verified against Betfair prices. Exchange commission rules vary; this simplified model excludes other fees and slippage. Expected P/L depends on model calibration.')
        if st.button('Record PAPER bet', type='primary'):
            key = (str(fixture['Date']), str(fixture['League']), str(fixture['Home']), str(fixture['Away']))
            duplicate = any(tuple(map(str, row)) == key for row in ledger[['Date','League','Home','Away']].itertuples(index=False, name=None)) if not ledger.empty else False
            if duplicate:
                st.error('A paper bet for this fixture is already recorded.')
            elif stake > 1000 + pnl - exposure:
                st.error('Insufficient virtual funds.')
            else:
                entry = dict(zip(COLUMNS, [*key, probability, odds, stake, 'Open', None, None, None]))
                st.session_state.gs_paper_ledger = pd.concat([ledger, pd.DataFrame([entry])], ignore_index=True)
                st.rerun()
    ledger = st.session_state.gs_paper_ledger
    st.markdown('#### Paper ledger and settlement')
    if ledger.empty:
        st.info('No simulated bets recorded yet.')
    else:
        st.dataframe(ledger, hide_index=True, use_container_width=True)
        open_ids = ledger.index[ledger.Status.eq('Open')].tolist()
        if open_ids:
            idx = st.selectbox('Settle a completed match', open_ids, format_func=lambda i: f"#{i+1}: {ledger.loc[i,'Home']} v {ledger.loc[i,'Away']}")
            u,v = st.columns(2)
            hg = u.number_input('Actual home goals', 0, 30, 0, 1)
            ag = v.number_input('Actual away goals', 0, 30, 0, 1)
            if st.button('Settle selected PAPER bet'):
                odds = float(ledger.loc[idx,'Odds']); stake = float(ledger.loc[idx,'Stake'])
                # Apply illustrative commission at settlement using the rate stored below.
                commission = st.session_state.get('gs_settle_commission', 2.0)
                profit = stake * (odds-1) * (1-commission/100) if hg+ag>0 else -stake
                for col, val in [('Home goals',hg),('Away goals',ag),('Profit',round(profit,2)),('Status','Settled')]:
                    st.session_state.gs_paper_ledger.loc[idx,col] = val
                st.rerun()
            st.number_input('Settlement commission assumption (%)', min_value=0.0, max_value=10.0, value=2.0, step=.5, key='gs_settle_commission')
        st.download_button('Download paper ledger (CSV)', ledger.to_csv(index=False).encode('utf-8'), 'goalsense_paper_ledger.csv', 'text/csv')
        if st.button('Clear all simulated bets'):
            st.session_state.gs_paper_ledger = pd.DataFrame(columns=COLUMNS)
            st.rerun()
    st.caption('Settle only after checking the official full-time score. The app does not verify scores or automatically reconcile markets. Check void/abandoned match rules separately.')
