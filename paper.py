"""Private paper ledger backed by Supabase Auth + RLS-protected PostgREST.
No betting API calls, no real orders. Never use service-role keys here.
"""
import uuid
import requests
import pandas as pd
import streamlit as st

TIMEOUT = 15
START_BALANCE = 1000.0

def settings():
    try:
        url = str(st.secrets['SUPABASE_URL']).rstrip('/')
        key = str(st.secrets['SUPABASE_ANON_KEY'])
        email = str(st.secrets['PAPER_OWNER_EMAIL']).strip().lower()
        if not (url.startswith('https://') and key and email):
            raise ValueError('Invalid Supabase configuration')
        return url, key, email
    except (KeyError, FileNotFoundError, ValueError):
        return None

def request(method, path, cfg, token=None, json=None, params=None):
    url, key, _ = cfg
    headers = {'apikey': key, 'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    if method in ('POST', 'PATCH') and path.startswith('/rest/'):
        headers['Prefer'] = 'return=representation'
    r = requests.request(method, url + path, headers=headers, json=json, params=params, timeout=TIMEOUT)
    if not r.ok:
        raise RuntimeError(f'Supabase returned HTTP {r.status_code}: {r.text[:240]}')
    return r.json() if r.content else None

def authenticated(cfg):
    session = st.session_state.get('gs_auth')
    if not session:
        return None
    try:
        # Validate identity with Supabase on each rerun. Refresh if access token has expired.
        try:
            me = request('GET', '/auth/v1/user', cfg, session['access_token'])
        except RuntimeError:
            refreshed = request('POST', '/auth/v1/token?grant_type=refresh_token', cfg,
                                json={'refresh_token': session['refresh_token']})
            st.session_state['gs_auth'] = refreshed
            session = refreshed
            me = request('GET', '/auth/v1/user', cfg, session['access_token'])
        if me.get('email', '').lower() != cfg[2]:
            st.session_state.pop('gs_auth', None)
            st.error('This account is not authorised for the private paper ledger.')
            return None
        return me
    except (RuntimeError, KeyError, requests.RequestException) as exc:
        st.session_state.pop('gs_auth', None)
        st.error(f'Your session expired or authentication failed: {exc}')
        return None

def money(value):
    return f'£{value:,.2f}'

def render(rank):
    st.subheader('🔒 GoalSense 3.1 — Private paper betting')
    st.info('Simulation only. This app never sends bets to Betfair or any betting service.')
    cfg = settings()
    if cfg is None:
        st.warning('Private paper betting is not configured yet. Add SUPABASE_URL, SUPABASE_ANON_KEY and PAPER_OWNER_EMAIL in Streamlit app secrets. The public predictions remain available.')
        return
    if st.button('Sign out of paper betting'):
        st.session_state.pop('gs_auth', None)
        st.rerun()
    me = authenticated(cfg)
    if me is None:
        with st.form('paper_login'):
            email = st.text_input('Supabase account email')
            password = st.text_input('Password', type='password')
            submitted = st.form_submit_button('Sign in to private paper ledger')
        if submitted:
            if email.strip().lower() != cfg[2]:
                st.error('This account is not authorised.')
            else:
                try:
                    session = request('POST', '/auth/v1/token?grant_type=password', cfg,
                                      json={'email': email.strip(), 'password': password})
                    st.session_state['gs_auth'] = session
                    st.rerun()
                except (RuntimeError, requests.RequestException):
                    st.error('Sign-in failed. Check your email/password and Supabase settings.')
        return
    token = st.session_state['gs_auth']['access_token']
    uid = me['id']
    st.caption(f'Private ledger signed in as {me["email"]}. Records are saved to Supabase and protected by row-level security.')
    try:
        records = request('GET', '/rest/v1/paper_bets', cfg, token,
                          params={'select': '*', 'user_id': f'eq.{uid}', 'order': 'created_at.desc'}) or []
    except (RuntimeError, requests.RequestException) as exc:
        st.error(f'Unable to load saved paper bets: {exc}')
        return
    df = pd.DataFrame(records)
    settled = df[df.status.eq('Settled')] if not df.empty else df
    open_bets = df[df.status.eq('Open')] if not df.empty else df
    pnl = float(settled['profit'].fillna(0).sum()) if not settled.empty else 0.0
    exposure = float(open_bets['stake'].sum()) if not open_bets.empty else 0.0
    available = START_BALANCE + pnl - exposure
    cols = st.columns(4)
    for c, (label, value) in zip(cols, [('Starting bankroll', START_BALANCE), ('Realised P/L', pnl), ('Open stakes', exposure), ('Available funds', available)]):
        c.metric(label, money(value))
    st.markdown('#### Record a simulated bet')
    if rank.empty:
        st.warning('No upcoming fixtures available. Try a different league or date range.')
    else:
        r = rank.reset_index(drop=True)
        with st.form('new_paper_bet'):
            i = st.selectbox('Match', range(len(r)), format_func=lambda n: f"{r.iloc[n]['Date']} · {r.iloc[n]['Home']} v {r.iloc[n]['Away']} ({r.iloc[n]['League']})")
            odds = st.number_input('Decimal odds (entered manually)', 1.01, 100.0, 1.50, 0.01)
            stake = st.number_input('Virtual stake (£)', 1.0, 100.0, 5.0, 1.0)
            commission = st.number_input('Illustrative commission on winnings (%)', 0.0, 10.0, 2.0, 0.5)
            submitted = st.form_submit_button('Save PAPER bet')
        game = r.iloc[i]
        probability = float(game['Over 0.5 probability'])
        net_win = stake * (odds - 1) * (1 - commission / 100)
        ev = probability * net_win - (1 - probability) * stake
        st.caption(f'Estimated goal probability {probability:.1%} · Model expected P/L {money(ev)}. Estimates are not guaranteed or calibrated to market prices.')
        if submitted:
            fixture_date = str(game['Date'])[:10]
            duplicate = any(str(b['fixture_date']) == fixture_date and b['league'] == str(game['League']) and b['home'] == str(game['Home']) and b['away'] == str(game['Away']) for b in records)
            if duplicate:
                st.error('A paper bet on this fixture already exists.')
            elif stake > available:
                st.error('Insufficient virtual funds.')
            else:
                payload = {'user_id': uid, 'fixture_date': fixture_date, 'league': str(game['League']),
                           'home': str(game['Home']), 'away': str(game['Away']), 'probability': probability,
                           'odds': float(odds), 'stake': float(stake), 'commission_pct': float(commission),
                           'status': 'Open'}
                try:
                    request('POST', '/rest/v1/paper_bets', cfg, token, json=payload)
                    st.rerun()
                except (RuntimeError, requests.RequestException) as exc:
                    st.error(f'Unable to save bet: {exc}')
    st.markdown('#### Saved paper bets')
    if df.empty:
        st.info('No simulated bets saved yet.')
        return
    visible = ['fixture_date','league','home','away','probability','odds','stake','commission_pct','status','home_goals','away_goals','profit']
    st.dataframe(df[visible], hide_index=True, use_container_width=True)
    st.download_button('Export my paper bets (CSV)', df[visible].to_csv(index=False).encode(), 'goalsense_paper_bets.csv', 'text/csv')
    if not open_bets.empty:
        st.markdown('#### Settle a paper bet')
        with st.form('settle_paper'):
            bet_id = st.selectbox('Open bet', open_bets.id.tolist(), format_func=lambda bid: next(f"{b['home']} v {b['away']} · {b['fixture_date']}" for b in records if b['id'] == bid))
            hg = st.number_input('Final home goals', 0, 30, 0)
            ag = st.number_input('Final away goals', 0, 30, 0)
            settle = st.form_submit_button('Save final score and settle')
        if settle:
            bet = next(b for b in records if b['id'] == bet_id)
            profit = float(bet['stake']) * (float(bet['odds']) - 1) * (1 - float(bet['commission_pct']) / 100) if hg + ag > 0 else -float(bet['stake'])
            try:
                # Atomic conditional update: only Open bets can be settled.
                request('PATCH', '/rest/v1/paper_bets', cfg, token,
                        params={'id': f'eq.{bet_id}', 'user_id': f'eq.{uid}', 'status': 'eq.Open'},
                        json={'status': 'Settled', 'home_goals': int(hg), 'away_goals': int(ag), 'profit': round(profit, 2)})
                st.rerun()
            except (RuntimeError, requests.RequestException) as exc:
                st.error(f'Unable to settle bet: {exc}')
    st.caption('Settlement scores are manually entered, not verified against official results. Voids, abandoned matches, slippage and other fees are not modelled.')
