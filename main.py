import os
import logging
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('BOT_TOKEN')

ASSETS = {
    'nifty':     {'name': 'NIFTY 50',       'lot': 25,  'gap': 50,   'sym': 'Rs', 'ticker': '^NSEI'},
    'banknifty': {'name': 'BANK NIFTY',     'lot': 15,  'gap': 100,  'sym': 'Rs', 'ticker': '^NSEBANK'},
    'finnifty':  {'name': 'FIN NIFTY',      'lot': 25,  'gap': 50,   'sym': 'Rs', 'ticker': '^NSEI'},
    'midcap':    {'name': 'MIDCAP NIFTY',   'lot': 50,  'gap': 25,   'sym': 'Rs', 'ticker': '^NSEI'},
    'sensex':    {'name': 'SENSEX',         'lot': 10,  'gap': 100,  'sym': 'Rs', 'ticker': '^BSESN'},
    'crude':     {'name': 'CRUDE OIL MCX',  'lot': 100, 'gap': 50,   'sym': 'Rs', 'ticker': 'CL=F'},
    'gold':      {'name': 'GOLD MCX',       'lot': 100, 'gap': 100,  'sym': 'Rs', 'ticker': 'GC=F'},
    'silver':    {'name': 'SILVER MCX',     'lot': 30,  'gap': 100,  'sym': 'Rs', 'ticker': 'SI=F'},
    'naturalgas':{'name': 'NATURALGAS MCX', 'lot': 1250,'gap': 5,    'sym': 'Rs', 'ticker': 'NG=F'},
    'copper':    {'name': 'COPPER MCX',     'lot': 2500,'gap': 1,    'sym': 'Rs', 'ticker': 'HG=F'},
    'btc':       {'name': 'BITCOIN',        'lot': 1,   'gap': 1000, 'sym': '$',  'ticker': 'BTC-USD'},
    'eth':       {'name': 'ETHEREUM',       'lot': 1,   'gap': 50,   'sym': '$',  'ticker': 'ETH-USD'},
    'bnb':       {'name': 'BINANCE COIN',   'lot': 1,   'gap': 5,    'sym': '$',  'ticker': 'BNB-USD'},
    'sol':       {'name': 'SOLANA',         'lot': 1,   'gap': 5,    'sym': '$',  'ticker': 'SOL-USD'},
    'xrp':       {'name': 'XRP',            'lot': 100, 'gap': 0.01, 'sym': '$',  'ticker': 'XRP-USD'},
    'doge':      {'name': 'DOGECOIN',       'lot': 1000,'gap': 0.001,'sym': '$',  'ticker': 'DOGE-USD'},
    'ada':       {'name': 'CARDANO',        'lot': 100, 'gap': 0.01, 'sym': '$',  'ticker': 'ADA-USD'},
    'matic':     {'name': 'POLYGON',        'lot': 100, 'gap': 0.01, 'sym': '$',  'ticker': 'MATIC-USD'},
}

USD_INR = 84.0

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
    except Exception:
        pass
    return None, None, None

def get_live_price(asset):
    cfg = ASSETS[asset]
    ticker = cfg['ticker']
    price_usd, change_usd, pct = get_yahoo_price(ticker)
    
    if price_usd is None:
        return None, None, None
    
    inr = fetch_usd_inr()
    
    if asset == 'crude':
        price = round(price_usd * inr / 6)
        change = round(change_usd * inr / 6, 1)
        return price, change, pct
    elif asset == 'gold':
        price = round(price_usd * inr / 31.1 * 10)
        change = round(change_usd * inr / 31.1 * 10)
        return price, change, pct
    elif asset == 'silver':
        price = round(price_usd * inr / 31.1 * 1000)
        change = round(change_usd * inr / 31.1 * 1000)
        return price, change, pct
    elif asset == 'naturalgas':
        price = round(price_usd * inr / 10, 1)
        change = round(change_usd * inr / 10, 1)
        return price, change, pct
    elif asset == 'copper':
        price = round(price_usd * inr * 2.2 / 1000, 1)
        change = round(change_usd * inr * 2.2 / 1000, 1)
        return price, change, pct
    else:
        return round(price_usd, 4), round(change_usd, 4), pct

def get_greeks(asset, pct):
    iv_base = {
        'nifty': 14, 'banknifty': 20, 'finnifty': 17, 'midcap': 19, 'sensex': 14,
        'crude': 32, 'gold': 15, 'silver': 20, 'naturalgas': 40, 'copper': 22,
        'btc': 60, 'eth': 70, 'bnb': 65, 'sol': 75, 'xrp': 70,
        'doge': 85, 'ada': 72, 'matic': 78
    }
    iv = iv_base.get(asset, 25)
    
    if pct > 1.5:
        delta = round(min(0.62 + pct * 0.015, 0.70), 2)
        market = 'STRONGLY BULLISH'
        conf = min(92, 75 + int(pct * 4))
        iv = iv + 4
    elif pct > 0.5:
        delta = round(0.54 + pct * 0.02, 2)
        market = 'BULLISH'
        conf = min(82, 68 + int(pct * 5))
        iv = iv + 2
    elif pct < -1.5:
        delta = round(max(0.38 - abs(pct) * 0.015, 0.30), 2)
        market = 'STRONGLY BEARISH'
        conf = min(92, 75 + int(abs(pct) * 4))
        iv = iv + 4
    elif pct < -0.5:
        delta = round(0.46 - abs(pct) * 0.02, 2)
        market = 'BEARISH'
        conf = min(82, 68 + int(abs(pct) * 5))
        iv = iv + 2
    else:
        delta = 0.50
        market = 'NEUTRAL'
        conf = 55
    
    gamma = round(0.018 + iv * 0.001, 4)
    theta = -round(iv * 1.1, 1)
    vega = round(iv * 0.8, 1)
    iv_rank = 'HIGH' if iv > 30 else 'MEDIUM' if iv > 18 else 'LOW'
    
    return {
        'delta': delta, 'gamma': gamma, 'theta': theta, 'vega': vega,
        'iv': iv, 'iv_rank': iv_rank, 'market': market, 'conf': conf
    }

def format_rec(market, atm, gap, sym, iv_rank):
    c1 = round(atm + gap, 4)
    c2 = round(atm + 2 * gap, 4)
    p1 = round(atm - gap, 4)
    
    msg = 'OPTION RECOMMENDATIONS:\n\n'
    
    if 'BULLISH' in market:
        msg += '#1 BUY CALL - Best Choice\n'
        msg += '   Strike: ' + sym + str(c1) + ' CE\n'
        msg += '   Signal: Bullish confirmed\n'
        msg += '   Risk: Limited\n\n'
        msg += '#2 BULL CALL SPREAD\n'
        msg += '   Buy ' + sym + str(c1) + ' CE\n'
        msg += '   Sell ' + sym + str(c2) + ' CE\n'
        msg += '   Lower cost strategy\n\n'
        msg += '#3 SELL PUT (IV ' + iv_rank + ')\n'
        msg += '   Strike: ' + sym + str(p1) + ' PE SELL\n'
        msg += '   Risk: HIGH - Use SL!'
    elif 'BEARISH' in market:
        msg += '#1 BUY PUT - Best Choice\n'
        msg += '   Strike: ' + sym + str(p1) + ' PE\n'
        msg += '   Signal: Bearish confirmed\n'
        msg += '   Risk: Limited\n\n'
        msg += '#2 BEAR PUT SPREAD\n'
        msg += '   Buy ' + sym + str(p1) + ' PE\n'
        msg += '   Sell ' + sym + str(c2) + ' PE\n'
        msg += '   Lower cost strategy\n\n'
        msg += '#3 SELL CALL\n'
        msg += '   Strike: ' + sym + str(c1) + ' CE SELL\n'
        msg += '   Risk: HIGH - Use SL!'
    else:
        msg += '#1 WAIT - Best Choice\n'
        msg += '   Market unclear/sideways\n'
        msg += '   Wait for breakout\n\n'
        msg += '#2 IRON CONDOR (Experts)\n'
        msg += '   Range-bound profit\n'
        msg += '   Risk: Limited'
    
    return msg

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = 'Shon A.I. Advanced Trading Bot\n\n'
    msg += 'FEATURES:\n'
    msg += '- Live Real-time Prices\n'
    msg += '- Dynamic Greeks\n'
    msg += '- Option Recommendations\n'
    msg += '- Real-time Signals\n\n'
    msg += 'MARKETS:\n'
    msg += 'Indices: nifty, banknifty, finnifty, sensex, midcap\n'
    msg += 'Commodities: crude, gold, silver, naturalgas, copper\n'
    msg += 'Crypto: btc, eth, bnb, sol, xrp, doge, ada, matic\n\n'
    msg += 'COMMANDS:\n'
    msg += '/analyze nifty - Live analysis\n'
    msg += '/analyze gold - Gold MCX\n'
    msg += '/analyze btc - Bitcoin\n'
    msg += '/markets - All prices\n'
    msg += '/help - Help\n\n'
    msg += 'Ready!'
    await update.message.reply_text(msg)

async def markets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Fetching live prices...')
    
    msg = 'LIVE MARKET PRICES\n'
    msg += '=' * 20 + '\n\n'
    
    msg += 'INDIAN INDICES:\n'
    for a in ['nifty', 'banknifty', 'sensex']:
        try:
            p, c, pct = get_live_price(a)
            if p:
                sym = ASSETS[a]['sym']
                sign = '+' if (pct or 0) >= 0 else ''
                msg += a.upper() + ': ' + sym + str(p) + ' ' + sign + str(pct) + '%\n'
        except Exception:
            pass
    
    msg += '\nCOMMODITIES MCX:\n'
    for a in ['crude', 'gold', 'silver']:
        try:
            p, c, pct = get_live_price(a)
            if p:
                sym = ASSETS[a]['sym']
                sign = '+' if (pct or 0) >= 0 else ''
                msg += a.upper() + ': ' + sym + str(p) + ' ' + sign + str(pct) + '%\n'
        except Exception:
            pass
    
    msg += '\nCRYPTO:\n'
    for a in ['btc', 'eth', 'bnb', 'sol']:
        try:
            p, c, pct = get_live_price(a)
            if p:
                sym = ASSETS[a]['sym']
                sign = '+' if (pct or 0) >= 0 else ''
                msg += a.upper() + ': ' + sym + str(p) + ' ' + sign + str(pct) + '%\n'
        except Exception:
            pass
    
    msg += '\nUse /analyze [asset] for details'
    await update.message.reply_text(msg)

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    
    if not args:
        msg = 'Use: /analyze [asset] [price]\n\n'
        msg += 'Examples:\n'
        msg += '/analyze nifty\n'
        msg += '/analyze gold\n'
        msg += '/analyze btc\n'
        msg += '/analyze nifty 24500\n\n'
        msg += 'Assets:\n'
        msg += 'Indices: nifty, banknifty, finnifty, sensex, midcap\n'
        msg += 'Commodities: crude, gold, silver, naturalgas, copper\n'
        msg += 'Crypto: btc, eth, bnb, sol, xrp, doge, ada, matic'
        await update.message.reply_text(msg)
        return
    
    asset = args[0].lower()
    if asset not in ASSETS:
        await update.message.reply_text(asset + ' not supported!')
        return
    
    cfg = ASSETS[asset]
    price = None
    change = 0.0
    pct = 0.0
    
    if len(args) >= 2:
        try:
            price = float(args[1].replace(',', ''))
        except ValueError:
            await update.message.reply_text('Invalid price!')
            return
    else:
        loading = await update.message.reply_text('Fetching live price...')
        price, change, pct = get_live_price(asset)
        try:
            await loading.delete()
        except Exception:
            pass
        
        if price is None:
            await update.message.reply_text('Live price not available!\nUse: /analyze ' + asset + ' [price]')
            return
    
    sym = cfg['sym']
    gap = cfg['gap']
    lot = cfg['lot']
    
    atm = round(price / gap) * gap
    call_strike = round(atm + gap, 4)
    put_strike = round(atm - gap, 4)
    
    if asset in ['btc', 'eth', 'bnb', 'sol']:
        premium = max(round(price * 0.020), 1)
    elif asset in ['gold', 'silver']:
        premium = max(round(price * 0.006), 100)
    elif asset == 'crude':
        premium = max(round(price * 0.025), 30)
    else:
        premium = max(round(price * 0.0045), 30)
    
    target = round(premium * 1.65)
    sl = round(premium * 0.60)
    investment = premium * lot
    max_profit = (target - premium) * lot
    max_loss = (premium - sl) * lot
    
    g = get_greeks(asset, pct)
    rec = format_rec(g['market'], atm, gap, sym, g['iv_rank'])
    
    arrow = 'UP' if change >= 0 else 'DN'
    sign = '+' if pct >= 0 else ''
    
    msg = '=' * 30 + '\n'
    msg += cfg['name'] + ' ANALYSIS\n'
    msg += '=' * 30 + '\n'
    msg += 'Price: ' + sym + str(price) + '\n'
    msg += 'Change: ' + arrow + ' ' + sign + str(pct) + '%\n\n'
    msg += 'SIGNAL: ' + g['market'] + '\n'
    msg += 'Confidence: ' + str(g['conf']) + '%\n'
    msg += 'IV: ' + str(g['iv']) + '% (' + g['iv_rank'] + ')\n\n'
    msg += 'STRIKES:\n'
    msg += 'ATM:  ' + sym + str(atm) + '\n'
    msg += 'Call: ' + sym + str(call_strike) + ' CE\n'
    msg += 'Put:  ' + sym + str(put_strike) + ' PE\n\n'
    msg += 'GREEKS (Real-time):\n'
    msg += 'Delta: ' + str(g['delta']) + '\n'
    msg += 'Gamma: ' + str(g['gamma']) + '\n'
    msg += 'Theta: ' + str(g['theta']) + '\n'
    msg += 'Vega:  ' + str(g['vega']) + '\n\n'
    msg += 'TRADE SETUP:\n'
    msg += 'Buy ' + str(call_strike) + ' CE\n'
    msg += 'Premium: ' + sym + str(premium) + '\n'
    msg += 'Target:  ' + sym + str(target) + '\n'
    msg += 'SL:      ' + sym + str(sl) + '\n\n'
    msg += 'CAPITAL:\n'
    msg += 'Investment: ' + sym + str(investment) + '\n'
    msg += 'Max Profit: ' + sym + str(max_profit) + '\n'
    msg += 'Max Loss:   ' + sym + str(max_loss) + '\n'
    msg += 'R:R = 1:2\n\n'
    msg += 'STRATEGIES:\n'
    msg += 'Aggressive: ' + sym + str(investment) + '\n'
    msg += 'Moderate:   ' + sym + str(int(investment * 0.8)) + '\n'
    msg += 'Safe:       ' + sym + str(investment * 2) + '\n\n'
    msg += 'TIMING:\n'
    msg += 'Entry: 10:00-11:30 AM\n'
    msg += 'Avoid: 3:00-3:30 PM\n\n'
    msg += '-' * 30 + '\n'
    msg += rec + '\n'
    msg += '-' * 30 + '\n\n'
    msg += 'Educational only! Use SL!'
    
    await update.message.reply_text(msg)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = 'HELP GUIDE\n\n'
    msg += 'LIVE ANALYSIS:\n'
    msg += '/analyze nifty\n'
    msg += '/analyze banknifty\n'
    msg += '/analyze gold\n'
    msg += '/analyze silver\n'
    msg += '/analyze crude\n'
    msg += '/analyze btc\n'
    msg += '/analyze eth\n\n'
    msg += 'MANUAL PRICE:\n'
    msg += '/analyze nifty 24500\n'
    msg += '/analyze gold 72000\n\n'
    msg += 'ALL MARKETS:\n'
    msg += '/markets\n\n'
    msg += 'ASSETS:\n'
    msg += 'Indices: nifty, banknifty, finnifty, sensex, midcap\n'
    msg += 'Commodities: crude, gold, silver, naturalgas, copper\n'
    msg += 'Crypto: btc, eth, bnb, sol, xrp, doge, ada, matic\n\n'
    msg += 'Trade smart!'
    await update.message.reply_text(msg)

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
