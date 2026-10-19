"""Read-only Betfair Exchange market snapshot. No order-placement methods exist."""
import requests
import streamlit as st
import pandas as pd
from paper import settings as paper_settings, authenticated as paper_authenticated

BASE = 'https://api.betfair.com/exchange/betting/rest/v1.0/'


def config():
    try:
        app_key = str(st.secrets.get('BETFAIR_APP_KEY', '')).strip()
        session = str(st.secrets.get('BETFAIR_SESSION_TOKEN', '')).strip()
        return (app_key, session) if app_key and session else None
    except (FileNotFoundError, KeyError):
        return None


def api(method, params, creds):
    if method not in ('listMarketCatalogue', 'listMarketBook'):
        raise ValueError('Only read-only Betfair endpoints are permitted')
    app_key, session = creds
    response = requests.post(BASE + method + '/', headers={
        'X-Application': app_key, 'X-Authentication': session,
        'Content-Type': 'application/json', 'Accept': 'application/json'
    }, json=params, timeout=20)
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict) and payload.get('faultcode'):
        raise RuntimeError('Betfair API rejected the request')
    return payload


def fetch_odds(creds, days=7):
    """Find MATCH_ODDS? No: Over/Under 0.5 goals is marketTypeCode OVER_UNDER_05."""
    now = pd.Timestamp.now(tz='UTC')
    until = now + pd.Timedelta(days=days)
    cats = api('listMarketCatalogue', {
        'filter': {'eventTypeIds': ['1'], 'marketTypeCodes': ['OVER_UNDER_05'],
                   'marketStartTime': {'from': now.isoformat(), 'to': until.isoformat()}},
        'marketProjection': ['EVENT', 'MARKET_START_TIME', 'RUNNER_DESCRIPTION'],
        'sort': 'FIRST_TO_START', 'maxResults': '200'
    }, creds)
    if not cats:
        return pd.DataFrame()
    ids = [m['marketId'] for m in cats]
    books = {}
    for start in range(0, len(ids), 40):
        for book in api('listMarketBook', {'marketIds': ids[start:start+40],
                      'priceProjection': {'priceData': ['EX_BEST_OFFERS']}}, creds):
            books[book['marketId']] = book
    rows = []
    for m in cats:
        book = books.get(m['marketId'], {})
        runner_prices = {r['selectionId']: r for r in book.get('runners', [])}
        for runner in m.get('runners', []):
            if 'over 0.5' not in runner.get('runnerName', '').lower():
                continue
            offer = runner_prices.get(runner['selectionId'], {}).get('ex', {}).get('availableToBack', [])
            if not offer:
                continue
            event = m.get('event', {})
            rows.append({'Event': event.get('name', ''), 'Start (UTC)': m.get('marketStartTime', ''),
                         'Market ID': m['marketId'], 'Selection ID': runner['selectionId'],
                         'Back odds': float(offer[0]['price']), 'Available (£)': float(offer[0]['size'])})
    return pd.DataFrame(rows)


def render():
    st.subheader('📡 Betfair odds — read-only')
    st.info('Paper betting only. This page retrieves market prices but cannot place real bets. Your Betfair credentials remain in private Streamlit Secrets.')
    owner_cfg = paper_settings()
    if owner_cfg is None or paper_authenticated(owner_cfg) is None:
        st.warning('Sign in to your private Paper Betting account first to access Betfair market data.')
        return
    creds = config()
    if not creds:
        st.warning('Add BETFAIR_APP_KEY and BETFAIR_SESSION_TOKEN to Streamlit Secrets to enable read-only odds. Session tokens expire and require renewal.')
        st.caption('Do not use your Betfair username/password in Streamlit Secrets. Obtain an approved API key and session token through Betfair developer authentication. API access may have fees or restrictions.')
        return
    days = st.slider('Days ahead', 1, 14, 7)
    if st.button('Retrieve Betfair Over 0.5 odds', type='primary'):
        try:
            st.session_state['bf_prices'] = fetch_odds(creds, days)
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            st.error(f'Unable to retrieve Betfair markets: {str(exc)[:180]}')
    prices = st.session_state.get('bf_prices')
    if prices is None:
        return
    if prices.empty:
        st.warning('No Over 0.5 markets with available back prices were returned. Market availability and API permissions vary.')
        return
    st.dataframe(prices, hide_index=True, use_container_width=True)
    st.download_button('Download Betfair odds snapshot', prices.to_csv(index=False), 'betfair_over05_snapshot.csv', 'text/csv')
    st.caption('Prices are snapshots, not executable guarantees. Market names are not automatically matched to GoalSense fixtures. Verify event, kickoff, and market before using odds in the paper ledger. No automatic bets are created.')
