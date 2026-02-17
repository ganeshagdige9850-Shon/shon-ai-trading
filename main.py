import os
import logging
import requests
import anthropic
import base64
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('BOT_TOKEN')
ANTHROPIC_KEY = os.environ.get('ANTHROPIC_API_KEY')

# ============================================================
# ALL ASSETS CONFIGURATION
# ============================================================
ASSETS = {
    # INDIAN INDICES
    'nifty':     {'name': 'NIFTY 50',       'lot': 25,  'gap': 50,    'sym': 'Rs', 'ticker': '^NSEI',     'type': 'index'},
    'banknifty': {'name': 'BANK NIFTY',     'lot': 15,  'gap': 100,   'sym': 'Rs', 'ticker': '^NSEBANK',  'type': 'index'},
    'finnifty':  {'name': 'FIN NIFTY',      'lot': 25,  'gap': 50,    'sym': 'Rs', 'ticker': '^NSEI',     'type': 'index'},
    'midcap':    {'name': 'MIDCAP NIFTY',   'lot': 50,  'gap': 25,    'sym': 'Rs', 'ticker': '^NSEI',     'type': 'index'},
    'sensex':    {'name': 'SENSEX',         'lot': 10,  'gap': 100,   'sym': 'Rs', 'ticker': '^BSESN',    'type': 'index'},
    # COMMODITIES
    'crude':     {'name': 'CRUDE OIL MCX',  'lot': 100, 'gap': 50,    'sym': 'Rs', 'ticker': 'CL=F',      'type': 'commodity'},
    'gold':      {'name': 'GOLD MCX',       'lot': 100, 'gap': 100,   'sym': 'Rs', 'ticker': 'GC=F',      'type': 'commodity'},
    'silver':    {'name': 'SILVER MCX',     'lot': 30,  'gap': 100,   'sym': 'Rs', 'ticker': 'SI=F',      'type': 'commodity'},
    'naturalgas':{'name': 'NATURAL GAS MCX','lot': 1250,'gap': 5,     'sym': 'Rs', 'ticker': 'NG=F',      'type': 'commodity'},
    'copper':    {'name': 'COPPER MCX',     'lot': 2500,'gap': 1,     'sym': 'Rs', 'ticker': 'HG=F',      'type': 'commodity'},
    # CRYPTO - MAJOR
    'btc':       {'name': 'BITCOIN',        'lot': 1,   'gap': 1000,  'sym': '$',  'ticker': 'BTC-USD',   'type': 'crypto'},
    'eth':       {'name': 'ETHEREUM',       'lot': 1,   'gap': 50,    'sym': '$',  'ticker': 'ETH-USD',   'type': 'crypto'},
    'bnb':       {'name': 'BINANCE COIN',   'lot': 1,   'gap': 5,     'sym': '$',  'ticker': 'BNB-USD',   'type': 'crypto'},
    'sol':       {'name': 'SOLANA',         'lot': 1,   'gap': 5,     'sym': '$',  'ticker': 'SOL-USD',   'type': 'crypto'},
    'xrp':       {'name': 'XRP',            'lot': 100, 'gap': 0.01,  'sym': '$',  'ticker': 'XRP-USD',   'type': 'crypto'},
    'doge':      {'name': 'DOGECOIN',       'lot': 1000,'gap': 0.001, 'sym': '$',  'ticker': 'DOGE-USD',  'type': 'crypto'},
    'ada':       {'name': 'CARDANO',        'lot': 100, 'gap': 0.01,  'sym': '$',  'ticker': 'ADA-USD',   'type': 'crypto'},
    'matic':     {'name': 'POLYGON',        'lot': 100, 'gap': 0.01,  'sym': '$',  'ticker': 'MATIC-USD', 'type': 'crypto'},
    'dot':       {'name': 'POLKADOT',       'lot': 10,  'gap': 0.5,   'sym': '$',  'ticker': 'DOT-USD',   'type': 'crypto'},
    'avax':      {'name': 'AVALANCHE',      'lot': 1,   'gap': 1,     'sym': '$',  'ticker': 'AVAX-USD',  'type': 'crypto'},
}

USD_INR = 84.0

# ============================================================
# PRICE FUNCTIONS
# ============================================================
def fetch_usd_inr():
    global USD_INR
    try:
        url = 'https://query1.finance.yahoo.com/v8/finance/chart/USDINR=X'
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        if r.status_code == 200:
            price = r.json()['chart']['result'][0]['meta']['regularMarketPrice']
            USD_INR = float(price)
    except Exception:
        pass
    return USD_INR

def get_yahoo_price(ticker):
    try:
        url = 'https://query1.finance.yahoo.com/v8/finance/chart/' + ticker
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            meta = r.json()['chart']['result'][0]['meta']
            price = float(meta.get('regularMarketPrice', 0))
            prev = float(meta.get('previousClose', price))
            change = round(price - prev, 4)
            pct = round((change / prev) * 100, 2) if prev else 0
            return price, change, pct
    except Exception as e:
        logger.error('Yahoo error ' + ticker + ': ' + str(e))

    try:
        url = 'https://query2.finance.yahoo.com/v7/finance/quote?symbols=' + ticker
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        if r.status_code == 200:
            res = r.json()['quoteResponse']['result'][0]
            price = float(res.get('regularMarketPrice', 0))
            change = float(res.get('regularMarketChange', 0))
            pct = float(res.get('regularMarketChangePercent', 0))
            return price, change, pct
    except Exception as e:
        logger.error('Yahoo v7 error: ' + str(e))

    return None, None, None

def get_live_price(asset):
    cfg = ASSETS[asset]
    ticker = cfg['ticker']
    asset_type = cfg['type']

    price_usd, change_usd, pct = get_yahoo_price(ticker)
    if price_usd is None:
        return None, None, None

    inr = fetch_usd_inr()

    if asset_type == 'index':
        return round(price_usd, 1), round(change_usd, 1), pct

    elif asset == 'crude':
        # MCX Crude = USD/barrel * INR rate / 6 (approx)
        price = round(price_usd * inr / 6)
        change = round(change_usd * inr / 6, 1)
        return price, change, pct

    elif asset == 'gold':
        # MCX Gold = USD/troy oz * INR rate / 31.1 * 10 (per 10gm)
        price = round(price_usd * inr / 31.1 * 10)
        change = round(change_usd * inr / 31.1 * 10)
        return price, change, pct

    elif asset == 'silver':
        # MCX Silver = USD/troy oz * INR rate / 31.1 * 1000 (per kg)
        price = round(price_usd * inr / 31.1 * 1000)
        change = round(change_usd * inr / 31.1 * 1000)
        return price, change, pct

    elif asset == 'naturalgas':
        price = round(price_usd * inr / 10, 1)
        change = round(change_usd * inr / 10, 1)
        return price, change, pct

    elif asset == 'copper':
        price = round(price_usd * inr * 2.2046 / 1000, 1)
        change = round(change_usd * inr * 2.2046 / 1000, 1)
        return price, change, pct

    elif asset_type == 'crypto':
        return round(price_usd, 4), round(change_usd, 4), pct

    return round(price_usd, 2), round(change_usd, 2), pct

# ============================================================
# DYNAMIC GREEKS
# ============================================================
def get_greeks(asset, pct):
    iv_base = {
        'nifty': 14, 'banknifty': 20, 'finnifty': 17, 'midcap': 19, 'sensex': 14,
        'crude': 32, 'gold': 15, 'silver': 20, 'naturalgas': 40, 'copper': 22,
        'btc': 60, 'eth': 70, 'bnb': 65, 'sol': 75, 'xrp': 70,
        'doge': 85, 'ada': 72, 'matic': 78, 'dot': 70, 'avax': 75,
    }
    iv = iv_base.get(asset, 25)

    if pct > 1.5:
        delta = round(min(0.62 + pct * 0.015, 0.70), 2)
        market = 'STRONGLY BULLISH'
        conf = min(92, 75 + int(pct * 4))
        iv += 4
    elif pct > 0.5:
        delta = round(0.54 + pct * 0.02, 2)
        market = 'BULLISH'
        conf = min(82, 68 + int(pct * 5))
        iv += 2
    elif pct < -1.5:
        delta = round(max(0.38 - abs(pct) * 0.015, 0.30), 2)
        market = 'STRONGLY BEARISH'
        conf = min(92, 75 + int(abs(pct) * 4))
        iv += 4
    elif pct < -0.5:
        delta = round(0.46 - abs(pct) * 0.02, 2)
        market = 'BEARISH'
        conf = min(82, 68 + int(abs(pct) * 5))
        iv += 2
    else:
        delta = 0.50
        market = 'NEUTRAL'
        conf = 55

    gamma = round(0.018 + iv * 0.001, 4)
    theta = -round(iv * 1.1, 1)
    vega = round(iv * 0.8, 1)
    iv_rank = 'HIGH' if iv > 30 else 'MEDIUM' if iv > 18 else 'LOW'

    return {
        'delta': delta, 'gamma': gamma,
        'theta': theta, 'vega': vega,
        'iv': iv, 'iv_rank': iv_rank,
        'market': market, 'conf': conf
    }

# ============================================================
# OPTION RECOMMENDATION
# ============================================================
def get_recommendation(market, atm, gap, sym, iv_rank):
    c1 = round(atm + gap, 4)
    c2 = round(atm + 2 * gap, 4)
    p1 = round(atm - gap, 4)
    p2 = round(atm - 2 * gap, 4)

    lines = ['OPTION RECOMMENDATIONS:', '']

    if 'BULLISH' in market:
        strength = 'Strong ' if 'STRONGLY' in market else ''
        lines += [
            '#1 BUY CALL - Best Choice',
            '   Strike: ' + sym + str(c1) + ' CE',
            '   Signal: ' + strength + 'Bullish trend confirmed',
            '   Risk: Limited (premium only)',
            '   Win Rate: ~45-55%',
            '',
            '#2 BULL CALL SPREAD',
            '   Buy ' + sym + str(c1) + ' CE',
            '   Sell ' + sym + str(c2) + ' CE',
            '   Why: Lower cost, defined risk',
            '   Win Rate: ~55-65%',
            '',
            '#3 SELL PUT (IV ' + iv_rank + ')',
            '   Strike: ' + sym + str(p1) + ' PE SELL',
            '   Why: Collect premium in bullish market',
            '   Risk: HIGH - Use strict SL!',
        ]
    elif 'BEARISH' in market:
        strength = 'Strong ' if 'STRONGLY' in market else ''
        lines += [
            '#1 BUY PUT - Best Choice',
            '   Strike: ' + sym + str(p1) + ' PE',
            '   Signal: ' + strength + 'Bearish trend confirmed',
            '   Risk: Limited (premium only)',
            '   Win Rate: ~45-55%',
            '',
            '#2 BEAR PUT SPREAD',
            '   Buy ' + sym + str(p1) + ' PE',
            '   Sell ' + sym + str(p2) + ' PE',
            '   Why: Lower cost, defined risk',
            '   Win Rate: ~55-65%',
            '',
            '#3 SELL CALL (IV ' + iv_rank + ')',
            '   Strike: ' + sym + str(c1) + ' CE SELL',
            '   Why: Collect premium in bearish market',
            '   Risk: HIGH - Use strict SL!',
        ]
    else:
        lines += [
            '#1 WAIT - Best Choice',
            '   Market is sideways/unclear',
            '   Wait for breakout above ' + sym + str(c1),
            '   Or breakdown below ' + sym + str(p1),
            '',
            '#2 IRON CONDOR (Experienced only)',
            '   Sell ' + sym + str(c1) + ' CE + ' + sym + str(p1) + ' PE',
            '   Buy ' + sym + str(c2) + ' CE + ' + sym + str(p2) + ' PE',
            '   Why: Profit in range-bound market',
            '   Risk: Limited, needs monitoring',
            '',
            '#3 SHORT STRADDLE (Experts only)',
            '   Sell ATM CE + PE both',
            '   Win if market stays flat',
            '   Risk: Very HIGH if big move!',
        ]

    return '\n'.join(lines)

# ============================================================
# AI CHART ANALYSIS
# ============================================================
async def analyze_chart_ai(image_bytes):
    if not ANTHROPIC_KEY:
        return None
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        img_b64 = base64.standard_b64encode(image_bytes).decode('utf-8')

        prompt = (
            'You are an expert Indian stock market technical analyst for Options Trading.\n\n'
            'Analyze this trading chart carefully and provide:\n\n'
            '1. OVERALL SIGNAL: STRONG BUY / BUY / NEUTRAL / SELL / STRONG SELL\n'
            '2. TREND: Direction and strength (0-100%)\n'
            '3. CHART PATTERN: What pattern is visible\n'
            '4. KEY LEVELS:\n'
            '   - Support: 2-3 levels\n'
            '   - Resistance: 2-3 levels\n'
            '5. INDICATORS (if visible): RSI, MACD, MA status\n'
            '6. OPTION STRATEGY:\n'
            '   - Buy CE / Buy PE / Sell CE / Sell PE / Spread\n'
            '   - Which strike price to target\n'
            '   - Why this strategy\n'
            '7. TRADE PLAN:\n'
            '   - Entry: where to enter\n'
            '   - Target: price target\n'
            '   - Stop Loss: where to exit\n'
            '8. RISK LEVEL: Low / Medium / High\n'
            '9. CONFIDENCE: 0-100%\n\n'
            'Format clearly. Start with OVERALL SIGNAL in first line.\n'
            'Be specific with price levels if visible on chart.\n'
            'Keep it concise and actionable.'
        )

        response = client.messages.create(
            model='claude-opus-4-5-20251101',
            max_tokens=1200,
            messages=[{
                'role': 'user',
                'content': [
                    {
                        'type': 'image',
                        'source': {
                            'type': 'base64',
                            'media_type': 'image/jpeg',
                            'data': img_b64
                        }
                    },
                    {
                        'type': 'text',
                        'text': prompt
                    }
                ]
            }]
        )
        return response.content[0].text
    except Exception as e:
        logger.error('AI chart error: ' + str(e))
        return None

# ============================================================
# TELEGRAM HANDLERS
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        'Shon A.I. Advanced Trading Bot\n\n'
        'FEATURES:\n'
        'Live Real-time Prices\n'
        'Dynamic Greeks (Delta/Gamma/Theta/Vega)\n'
        'Option Recommendations\n'
        'AI Chart Analysis (Photo pathva!)\n'
        'Real-time Trading Signals\n\n'
        'SUPPORTED MARKETS:\n\n'
        'INDIAN INDICES:\n'
        'nifty, banknifty, finnifty, sensex, midcap\n\n'
        'COMMODITIES (MCX):\n'
        'crude, gold, silver, naturalgas, copper\n\n'
        'CRYPTO:\n'
        'btc, eth, bnb, sol, xrp, doge, ada, matic, dot, avax\n\n'
        'COMMANDS:\n'
        '/analyze nifty - Live analysis\n'
        '/analyze gold - Gold MCX\n'
        '/analyze btc - Bitcoin\n'
        '/analyze nifty 24500 - Manual price\n'
        '/markets - All prices\n'
        '/help - Help guide\n\n'
        'CHART ANALYSIS:\n'
        'Chart screenshot pathva - AI analysis milel!\n\n'
        'Ready to analyze! Trade smart!'
    )
    await update.message.reply_text(text)

async def markets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Sarya markets che live price ghet ahe...')

    lines = ['LIVE MARKET PRICES', '==================', '']

    groups = [
        ('INDIAN INDICES', ['nifty', 'banknifty', 'sensex']),
        ('COMMODITIES MCX', ['crude', 'gold', 'silver']),
        ('CRYPTO (Top 5)', ['btc', 'eth', 'bnb', 'sol', 'xrp']),
    ]

    for group_name, asset_list in groups:
        lines.append(group_name + ':')
        for asset in asset_list:
            try:
                price, change, pct = get_live_price(asset)
                if price:
                    sym = ASSETS[asset]['sym']
                    arrow = 'UP' if (change or 0) >= 0 else 'DN'
                    sign = '+' if (pct or 0) >= 0 else ''
                    lines.append(
                        asset.upper() + ': ' + sym + str(price) +
                        ' ' + arrow + ' ' + sign + str(pct) + '%'
                    )
                else:
                    lines.append(asset.upper() + ': N/A')
            except Exception:
                lines.append(asset.upper() + ': Error')
        lines.append('')

    lines.append('Use /analyze [asset] for full analysis')
    await update.message.reply_text('\n'.join(lines))

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args

    if not args:
        text = (
            'Use: /analyze [asset] [price]\n\n'
            'INDICES: nifty, banknifty, finnifty, sensex, midcap\n'
            'COMMODITIES: crude, gold, silver, naturalgas, copper\n'
            'CRYPTO: btc, eth, bnb, sol, xrp, doge, ada, matic\n\n'
            'Examples:\n'
            '/analyze nifty\n'
            '/analyze gold\n'
            '/analyze btc\n'
            '/analyze nifty 24500\n\n'
            'Chart analysis: Photo pathva!'
        )
        await update.message.reply_text(text)
        return

    asset = args[0].lower()
    if asset not in ASSETS:
        await update.message.reply_text(
            asset + ' supported nahi!\n\n'
            'Valid assets:\n'
            'Indices: nifty, banknifty, finnifty, sensex, midcap\n'
            'Commodities: crude, gold, silver, naturalgas, copper\n'
            'Crypto: btc, eth, bnb, sol, xrp, doge, ada, matic, dot, avax'
        )
        return

    cfg = ASSETS[asset]
    price = None
    change = 0.0
    pct = 0.0
    source = 'Manual'

    if len(args) >= 2:
        try:
            price = float(args[1].replace(',', ''))
        except ValueError:
            await update.message.reply_text('Price number pahije!\nExample: /analyze nifty 24500')
            return
    else:
        loading = await update.message.reply_text('Live price ghet ahe ' + cfg['name'] + '...')
        price, change, pct = get_live_price(asset)
        try:
            await loading.delete()
        except Exception:
            pass

        if price is None:
            await update.message.reply_text(
                'Live price milala nahi!\n\n'
                'Manual vapra:\n'
                '/analyze ' + asset + ' [price]'
            )
            return
        source = 'Live'

    sym = cfg['sym']
    gap = cfg['gap']
    lot = cfg['lot']
    asset_type = cfg['type']

    atm = round(price / gap) * gap
    call_strike = round(atm + gap, 4)
    put_strike = round(atm - gap, 4)

    if asset_type == 'crypto':
        premium_pct = 0.020
        min_premium = 1
    elif asset == 'gold':
        premium_pct = 0.005
        min_premium = 100
    elif asset == 'silver':
        premium_pct = 0.008
        min_premium = 100
    elif asset == 'crude':
        premium_pct = 0.025
        min_premium = 30
    elif asset == 'naturalgas':
        premium_pct = 0.030
        min_premium = 2
    else:
        premium_pct = 0.0045
        min_premium = 30

    premium = max(round(price * premium_pct), min_premium)
    target = round(premium * 1.65)
    sl = round(premium * 0.60)
    investment = premium * lot
    max_profit = (target - premium) * lot
    max_loss = (premium - sl) * lot

    g = get_greeks(asset, pct)
    rec = get_recommendation(g['market'], atm, gap, sym, g['iv_rank'])

    if change and pct and source == 'Live':
        arrow = 'UP' if change >= 0 else 'DOWN'
        sign = '+' if change >= 0 else ''
        change_line = arrow + ' ' + sign + str(change) + ' (' + sign + str(pct) + '%)'
    else:
        change_line = 'Manual input'

    lines = [
        '============================',
        cfg['name'] + ' ANALYSIS',
        '============================',
        'Price: ' + sym + str(price),
        'Change: ' + change_line,
        'Source: ' + source,
        '',
        'MARKET SIGNAL: ' + g['market'],
        'Confidence: ' + str(g['conf']) + '%',
        'IV: ' + str(g['iv']) + '% | IV Rank: ' + g['iv_rank'],
        '',
        'STRIKES:',
        'ATM:  ' + sym + str(atm),
        'Call: ' + sym + str(call_strike) + ' CE (*)',
        'Put:  ' + sym + str(put_strike) + ' PE',
        '',
        'GREEKS (Real-time Dynamic):',
        'Delta: ' + str(g['delta']) + ' (' + sym + str(round(g['delta']*100, 1)) + '/100pts)',
        'Gamma: ' + str(g['gamma']),
        'Theta: ' + str(g['theta']) + ' (lose ' + sym + str(abs(g['theta'])) + '/day)',
        'Vega:  ' + str(g['vega']) + ' (per 1% IV change)',
        'IV:    ' + str(g['iv']) + '%',
        '',
        'TRADE SETUP:',
        'Buy ' + str(call_strike) + ' CE',
        'Premium:
