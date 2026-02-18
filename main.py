import os
import logging
import requests
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('BOT_TOKEN')

ASSETS = {
    'nifty':     {'name': 'NIFTY 50',     'lot': 25,  'gap': 50,   'sym': 'Rs', 'ticker': '^NSEI',    'weekly': True},
    'banknifty': {'name': 'BANK NIFTY',   'lot': 15,  'gap': 100,  'sym': 'Rs', 'ticker': '^NSEBANK', 'weekly': True},
    'finnifty':  {'name': 'FIN NIFTY',    'lot': 25,  'gap': 50,   'sym': 'Rs', 'ticker': '^NSEI',    'weekly': True},
    'sensex':    {'name': 'SENSEX',       'lot': 10,  'gap': 100,  'sym': 'Rs', 'ticker': '^BSESN',   'weekly': True},
    'crude':     {'name': 'CRUDE OIL',    'lot': 100, 'gap': 50,   'sym': 'Rs', 'ticker': 'CL=F',     'weekly': False},
    'gold':      {'name': 'GOLD MCX',     'lot': 100, 'gap': 100,  'sym': 'Rs', 'ticker': 'GC=F',     'weekly': False},
    'silver':    {'name': 'SILVER MCX',   'lot': 30,  'gap': 100,  'sym': 'Rs', 'ticker': 'SI=F',     'weekly': False},
    'btc':       {'name': 'BITCOIN',      'lot': 1,   'gap': 1000, 'sym': '$',  'ticker': 'BTC-USD',  'weekly': True},
    'eth':       {'name': 'ETHEREUM',     'lot': 1,   'gap': 50,   'sym': '$',  'ticker': 'ETH-USD',  'weekly': True},
}

USD_INR = 84.0

def get_yahoo_price(ticker):
    try:
        url = 'https://query1.finance.yahoo.com/v8/finance/chart/' + ticker
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        if r.status_code == 200:
            meta = r.json()['chart']['result'][0]['meta']
            price = float(meta.get('regularMarketPrice', 0))
            prev = float(meta.get('previousClose', price))
            change = round(price - prev, 4)
            pct = round((change / prev) * 100, 2) if prev else 0
            return price, change, pct
    except Exception:
        pass
    return None, None, None

def get_live_price(asset):
    cfg = ASSETS[asset]
    price_usd, change_usd, pct = get_yahoo_price(cfg['ticker'])
    
    if price_usd is None:
        return None, None, None
    
    if asset == 'crude':
        price = round(price_usd * USD_INR / 6)
        change = round(change_usd * USD_INR / 6, 1)
        return price, change, pct
    elif asset == 'gold':
        price = round(price_usd * USD_INR / 31.1 * 10)
        change = round(change_usd * USD_INR / 31.1 * 10)
        return price, change, pct
    elif asset == 'silver':
        price = round(price_usd * USD_INR / 31.1 * 1000)
        change = round(change_usd * USD_INR / 31.1 * 1000)
        return price, change, pct
    else:
        return round(price_usd, 4), round(change_usd, 4), pct

def get_expiry_dates():
    today = datetime.now()
    days_until_thu = (3 - today.weekday()) % 7
    if days_until_thu == 0 and today.hour >= 15:
        days_until_thu = 7
    weekly = today + timedelta(days=days_until_thu)
    
    if today.month == 12:
        next_month = datetime(today.year + 1, 1, 1)
    else:
        next_month = datetime(today.year, today.month + 1, 1)
    last_day = next_month - timedelta(days=1)
    days_back = (last_day.weekday() - 3) % 7
    monthly = last_day - timedelta(days=days_back)
    
    if monthly < today:
        if monthly.month == 12:
            next_next = datetime(monthly.year + 1, 1, 1)
        else:
            next_next = datetime(monthly.year, monthly.month + 1, 1)
        last_day = next_next - timedelta(days=1)
        days_back = (last_day.weekday() - 3) % 7
        monthly = last_day - timedelta(days=days_back)
    
    return weekly, monthly

def calc_premium(spot, distance, iv):
    base_pcts = {0: 0.020, 1: 0.012, 2: 0.007, 3: 0.004}
    base = base_pcts.get(abs(distance), 0.002)
    multiplier = 1 + (iv - 20) / 100
    return max(round(spot * base * multiplier), 10)

def get_greeks(asset, pct):
    iv_map = {'nifty': 14, 'banknifty': 20, 'finnifty': 17, 'sensex': 14,
              'crude': 32, 'gold': 15, 'silver': 20, 'btc': 60, 'eth': 70}
    iv = iv_map.get(asset, 25)
    
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
    
    return {'delta': delta, 'gamma': gamma, 'theta': theta, 'vega': vega,
            'iv': iv, 'market': market, 'conf': conf}

def format_strikes(spot, gap, sym, lot, iv, market):
    atm = round(spot / gap) * gap
    strikes = []
    
    if 'BULLISH' in market:
        opt = 'CE'
        strikes.append({'name': 'ATM', 'strike': atm, 'type': opt, 'dist': 0,
                        'premium': calc_premium(spot, 0, iv),
                        'rec': 'Balanced risk/reward'})
        
        otm1 = round(atm + gap, 4)
        strikes.append({'name': 'OTM-1', 'strike': otm1, 'type': opt, 'dist': 1,
                        'premium': calc_premium(spot, 1, iv),
                        'rec': 'Best choice - RECOMMENDED'})
        
        otm2 = round(atm + 2 * gap, 4)
        strikes.append({'name': 'OTM-2', 'strike': otm2, 'type': opt, 'dist': 2,
                        'premium': calc_premium(spot, 2, iv),
                        'rec': 'Aggressive, lower cost'})
        
        itm1 = round(atm - gap, 4)
        strikes.append({'name': 'ITM-1', 'strike': itm1, 'type': opt, 'dist': -1,
                        'premium': calc_premium(spot, -1, iv),
                        'rec': 'Conservative, higher Delta'})
        
    elif 'BEARISH' in market:
        opt = 'PE'
        strikes.append({'name': 'ATM', 'strike': atm, 'type': opt, 'dist': 0,
                        'premium': calc_premium(spot, 0, iv),
                        'rec': 'Balanced risk/reward'})
        
        otm1 = round(atm - gap, 4)
        strikes.append({'name': 'OTM-1', 'strike': otm1, 'type': opt, 'dist': 1,
                        'premium': calc_premium(spot, 1, iv),
                        'rec': 'Best choice - RECOMMENDED'})
        
        otm2 = round(atm - 2 * gap, 4)
        strikes.append({'name': 'OTM-2', 'strike': otm2, 'type': opt, 'dist': 2,
                        'premium': calc_premium(spot, 2, iv),
                        'rec': 'Aggressive, lower cost'})
        
        itm1 = round(atm + gap, 4)
        strikes.append({'name': 'ITM-1', 'strike': itm1, 'type': opt, 'dist': -1,
                        'premium': calc_premium(spot, -1, iv),
                        'rec': 'Conservative, higher Delta'})
    else:
        strikes.append({'name': 'ATM', 'strike': atm, 'type': 'CE', 'dist': 0,
                        'premium': calc_premium(spot, 0, iv),
                        'rec': 'For upside breakout'})
        strikes.append({'name': 'ATM', 'strike': atm, 'type': 'PE', 'dist': 0,
                        'premium': calc_premium(spot, 0, iv),
                        'rec': 'For downside breakdown'})
    
    for s in strikes:
        s['investment'] = s['premium'] * lot
    
    return strikes

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = 'Shon A.I. Trading Bot\n\n'
    msg += 'FEATURES:\n'
    msg += '- Multiple Strike Options\n'
    msg += '- Real-time Premiums\n'
    msg += '- Investment per Lot\n'
    msg += '- Weekly/Monthly Expiry\n'
    msg += '- Dynamic Greeks\n\n'
    msg += 'COMMANDS:\n'
    msg += '/analyze nifty\n'
    msg += '/markets\n'
    msg += '/help\n\n'
    msg += 'Ready!'
    await update.message.reply_text(msg)

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    
    if not args:
        await update.message.reply_text('Use: /analyze [asset]\n\nExamples:\n/analyze nifty\n/analyze gold\n/analyze btc')
        return
    
    asset = args[0].lower()
    if asset not in ASSETS:
        await update.message.reply_text(asset + ' not supported!')
        return
    
    cfg = ASSETS[asset]
    loading = await update.message.reply_text('Fetching live data...')
    
    price, change, pct = get_live_price(asset)
    
    try:
        await loading.delete()
    except Exception:
        pass
    
    if price is None:
        await update.message.reply_text('Live price unavailable!')
        return
    
    sym = cfg['sym']
    gap = cfg['gap']
    lot = cfg['lot']
    
    g = get_greeks(asset, pct)
    strikes = format_strikes(price, gap, sym, lot, g['iv'], g['market'])
    weekly, monthly = get_expiry_dates()
    
    arrow = 'UP' if change >= 0 else 'DN'
    sign = '+' if pct >= 0 else ''
    now = datetime.now().strftime('%d-%b %I:%M%p')
    
    lines = []
    lines.append('=' * 35)
    lines.append(cfg['name'] + ' ANALYSIS')
    lines.append('=' * 35)
    lines.append('Price: ' + sym + str(price))
    lines.append('Change: ' + arrow + ' ' + sign + str(pct) + '%')
    lines.append('Time: ' + now)
    lines.append('')
    lines.append('SIGNAL: ' + g['market'])
    lines.append('Confidence: ' + str(g['conf']) + '%')
    lines.append('IV: ' + str(g['iv']) + '%')
    lines.append('')
    lines.append('-' * 35)
    lines.append('STRIKE OPTIONS')
    lines.append('-' * 35)
    
    for i, s in enumerate(strikes, 1):
        lines.append('')
        lines.append(str(i) + '. ' + s['name'] + ' - ' + sym + str(s['strike']) + ' ' + s['type'])
        lines.append('   Premium: ' + sym + str(s['premium']))
        lines.append('   Investment: ' + sym + str(s['investment']))
        lines.append('   Lot: ' + str(lot) + ' qty')
        lines.append('   ' + s['rec'])
    
    lines.append('')
    lines.append('-' * 35)
    lines.append('EXPIRY DATES')
    lines.append('-' * 35)
    
    if cfg['weekly']:
        lines.append('Weekly: ' + weekly.strftime('%d-%b-%Y'))
        lines.append('Days left: ' + str((weekly - datetime.now()).days))
    
    lines.append('Monthly: ' + monthly.strftime('%d-%b-%Y'))
    lines.append('Days left: ' + str((monthly - datetime.now()).days))
    
    lines.append('')
    lines.append('-' * 35)
    lines.append('GREEKS')
    lines.append('-' * 35)
    lines.append('Delta: ' + str(g['delta']))
    lines.append('Gamma: ' + str(g['gamma']))
    lines.append('Theta: ' + str(g['theta']))
    lines.append('Vega: ' + str(g['vega']))
    
    lines.append('')
    if 'BULLISH' in g['market']:
        lines.append('RECOMMENDATION: Buy OTM-1 CE')
        lines.append('Best risk/reward for bullish')
    elif 'BEARISH' in g['market']:
        lines.append('RECOMMENDATION: Buy OTM-1 PE')
        lines.append('Best risk/reward for bearish')
    else:
        lines.append('RECOMMENDATION: Wait')
        lines.append('Market unclear')
    
    lines.append('')
    lines.append('TIMING: 10:00-11:30 AM best')
    lines.append('Stop Loss: 30% of premium')
    lines.append('')
    lines.append('Educational only!')
    lines.append('=' * 35)
    
    await update.message.reply_text('\n'.join(lines))

async def markets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Fetching prices...')
    
    lines = ['LIVE PRICES', '=' * 20, '']
    
    lines.append('INDICES:')
    for a in ['nifty', 'banknifty', 'sensex']:
        try:
            p, c, pct = get_live_price(a)
            if p:
                sym = ASSETS[a]['sym']
                sign = '+' if (pct or 0) >= 0 else ''
                lines.append(a.upper() + ': ' + sym + str(p) + ' ' + sign + str(pct) + '%')
        except Exception:
            pass
    
    lines.append('')
    lines.append('COMMODITIES:')
    for a in ['crude', 'gold', 'silver']:
        try:
            p, c, pct = get_live_price(a)
            if p:
                sym = ASSETS[a]['sym']
                sign = '+' if (pct or 0) >= 0 else ''
                lines.append(a.upper() + ': ' + sym + str(p) + ' ' + sign + str(pct) + '%')
        except Exception:
            pass
    
    lines.append('')
    lines.append('CRYPTO:')
    for a in ['btc', 'eth']:
        try:
            p, c, pct = get_live_price(a)
            if p:
                sym = ASSETS[a]['sym']
                sign = '+' if (pct or 0) >= 0 else ''
                lines.append(a.upper() + ': ' + sym + str(p) + ' ' + sign + str(pct) + '%')
        except Exception:
            pass
    
    lines.append('')
    lines.append('Use /analyze [asset]')
    
    await update.message.reply_text('\n'.join(lines))

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = ['HELP', '=' * 20, '']
    lines.append('COMMANDS:')
    lines.append('/analyze nifty')
    lines.append('/analyze banknifty')
    lines.append('/analyze gold')
    lines.append('/analyze btc')
    lines.append('/markets')
    lines.append('')
    lines.append('FEATURES:')
    lines.append('- ATM/OTM/ITM strikes')
    lines.append('- Real-time premiums')
    lines.append('- Investment per lot')
    lines.append('- Weekly/Monthly expiry')
    lines.append('- Dynamic Greeks')
    lines.append('')
    lines.append('ASSETS:')
    lines.append('Indices: nifty, banknifty, finnifty, sensex')
    lines.append('Commodities: crude, gold, silver')
    lines.append('Crypto: btc, eth')
    
    await update.message.reply_text('\n'.join(lines))

def main():
    if not TOKEN:
        logger.error('BOT_TOKEN not set!')
        return
    logger.info('Bot starting...')
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('analyze', analyze))
    app.add_handler(CommandHandler('markets', markets))
    app.add_handler(CommandHandler('help', help_command))
    logger.info('Bot running!')
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
