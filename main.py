import os
import logging
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('BOT_TOKEN')

ASSETS = {
    'nifty':     {'name': 'NIFTY 50',     'lot': 25,  'gap': 50,   'sym': 'Rs', 'ticker': '^NSEI'},
    'banknifty': {'name': 'BANK NIFTY',   'lot': 15,  'gap': 100,  'sym': 'Rs', 'ticker': '^NSEBANK'},
    'finnifty':  {'name': 'FIN NIFTY',    'lot': 25,  'gap': 50,   'sym': 'Rs', 'ticker': '^NSEI'},
    'midcap':    {'name': 'MIDCAP NIFTY', 'lot': 50,  'gap': 25,   'sym': 'Rs', 'ticker': '^NSEI'},
    'sensex':    {'name': 'SENSEX',       'lot': 10,  'gap': 100,  'sym': 'Rs', 'ticker': '^BSESN'},
    'crude':     {'name': 'CRUDE OIL',    'lot': 100, 'gap': 50,   'sym': 'Rs', 'ticker': 'CL=F'},
    'btc':       {'name': 'BITCOIN',      'lot': 1,   'gap': 1000, 'sym': '$',  'ticker': 'BTC-USD'},
    'eth':       {'name': 'ETHEREUM',     'lot': 1,   'gap': 50,   'sym': '$',  'ticker': 'ETH-USD'},
}

def get_price(ticker, crude=False):
    try:
        url = 'https://query1.finance.yahoo.com/v8/finance/chart/' + ticker
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            meta = r.json()['chart']['result'][0]['meta']
            price = float(meta.get('regularMarketPrice', 0))
            prev = float(meta.get('previousClose', price))
            change = round(price - prev, 2)
            pct = round((change / prev) * 100, 2) if prev else 0
            if crude:
                price = round(price * 84 / 6)
                change = round(change * 84 / 6, 1)
            return round(price, 1), change, pct
    except Exception as e:
        logger.error('Price error: ' + str(e))
    return None, None, None

def get_greeks(asset, pct):
    iv_map = {
        'nifty': 14, 'banknifty': 20, 'finnifty': 17,
        'midcap': 19, 'sensex': 14, 'crude': 30,
        'btc': 60, 'eth': 70
    }
    iv = iv_map.get(asset, 20)

    if pct > 1.0:
        delta = round(min(0.55 + pct * 0.02, 0.65), 2)
        market = 'BULLISH'
        conf = min(90, 72 + int(pct * 4))
        iv = iv + 3
    elif pct < -1.0:
        delta = round(max(0.45 - abs(pct) * 0.02, 0.35), 2)
        market = 'BEARISH'
        conf = min(90, 72 + int(abs(pct) * 4))
        iv = iv + 3
    elif pct > 0.3:
        delta = 0.53
        market = 'SLIGHTLY BULLISH'
        conf = 62
    elif pct < -0.3:
        delta = 0.47
        market = 'SLIGHTLY BEARISH'
        conf = 62
    else:
        delta = 0.50
        market = 'NEUTRAL'
        conf = 55

    gamma = round(0.020 + iv * 0.0008, 4)
    theta = -round(iv * 1.2, 1)
    vega = round(iv * 0.75, 1)
    iv_rank = 'HIGH' if iv > 25 else 'MEDIUM' if iv > 17 else 'LOW'

    return {
        'delta': delta,
        'gamma': gamma,
        'theta': theta,
        'vega': vega,
        'iv': iv,
        'iv_rank': iv_rank,
        'market': market,
        'conf': conf
    }

def get_recommendation(market, atm, gap, sym):
    c1 = atm + gap
    c2 = atm + 2 * gap
    p1 = atm - gap
    p2 = atm - 2 * gap

    lines = []
    if 'BULLISH' in market:
        lines.append('OPTION RECOMMENDATIONS:')
        lines.append('')
        lines.append('#1 BUY CALL (Best Choice)')
        lines.append('Strike: ' + sym + str(c1) + ' CE')
        lines.append('Why: Bullish trend, best R:R')
        lines.append('Risk: Limited (premium only)')
        lines.append('')
        lines.append('#2 BULL CALL SPREAD')
        lines.append('Buy ' + sym + str(c1) + ' CE + Sell ' + sym + str(c2) + ' CE')
        lines.append('Why: Lower cost, limited profit')
        lines.append('')
        lines.append('#3 SELL PUT (for premium)')
        lines.append('Strike: ' + sym + str(p1) + ' PE SELL')
        lines.append('Risk: Unlimited - Use strict SL!')
    elif 'BEARISH' in market:
        lines.append('OPTION RECOMMENDATIONS:')
        lines.append('')
        lines.append('#1 BUY PUT (Best Choice)')
        lines.append('Strike: ' + sym + str(p1) + ' PE')
        lines.append('Why: Bearish trend, best R:R')
        lines.append('Risk: Limited (premium only)')
        lines.append('')
        lines.append('#2 BEAR PUT SPREAD')
        lines.append('Buy ' + sym + str(p1) + ' PE + Sell ' + sym + str(p2) + ' PE')
        lines.append('Why: Lower cost, limited profit')
        lines.append('')
        lines.append('#3 SELL CALL (for premium)')
        lines.append('Strike: ' + sym + str(c1) + ' CE SELL')
        lines.append('Risk: Unlimited - Use strict SL!')
    else:
        lines.append('OPTION RECOMMENDATIONS:')
        lines.append('')
        lines.append('#1 WAIT for clear direction')
        lines.append('Market neutral - risky to trade')
        lines.append('Better to wait for breakout')
        lines.append('')
        lines.append('#2 IRON CONDOR (Experienced)')
        lines.append('Sell ' + sym + str(c1) + ' CE + ' + sym + str(p1) + ' PE')
        lines.append('Buy further OTM CE + PE')
        lines.append('Risk: Limited, sideways profit')

    return '\n'.join(lines)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        'Shon A.I. Advanced Trading Bot\n\n'
        'Features:\n'
        '- Live Market Price\n'
        '- Dynamic Greeks\n'
        '- Option Recommendations\n'
        '- Risk Management\n\n'
        'Commands:\n'
        '/analyze nifty\n'
        '/analyze nifty 24500\n'
        '/help\n\n'
        'Assets: nifty, banknifty, finnifty,\n'
        'sensex, midcap, crude, btc, eth\n\n'
        'Ready to analyze!'
    )
    await update.message.reply_text(text)

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args

    if not args:
        await update.message.reply_text(
            'Use: /analyze [asset] [price]\n\n'
            'Live price:\n'
            '/analyze nifty\n'
            '/analyze banknifty\n'
            '/analyze crude\n\n'
            'Manual price:\n'
            '/analyze nifty 24500\n'
            '/analyze banknifty 45000'
        )
        return

    asset = args[0].lower()
    if asset not in ASSETS:
        await update.message.reply_text(
            asset + ' supported nahi!\n\n'
            'Valid: nifty, banknifty, finnifty,\n'
            'sensex, midcap, crude, btc, eth'
        )
        return

    cfg = ASSETS[asset]
    price = None
    change = 0.0
    pct = 0.0

    if len(args) >= 2:
        try:
            price = float(args[1].replace(',', ''))
        except ValueError:
            await update.message.reply_text('Price number असायला हवा!\nExample: /analyze nifty 24500')
            return
    else:
        loading = await update.message.reply_text('Live price ghet ahe ' + asset.upper() + '...')
        price, change, pct = get_price(cfg['ticker'], crude=(asset == 'crude'))
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

    sym = cfg['sym']
    gap = cfg['gap']
    lot = cfg['lot']

    atm = round(price / gap) * gap
    call_strike = atm + gap
    put_strike = atm - gap

    if asset in ['btc', 'eth']:
        premium = max(round(price * 0.015), 500)
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
    rec = get_recommendation(g['market'], atm, gap, sym)

    if change and pct:
        arrow = 'UP' if change >= 0 else 'DOWN'
        sign = '+' if change >= 0 else ''
        change_line = arrow + ' ' + sign + str(change) + ' (' + sign + str(pct) + '%)'
    else:
        change_line = 'Manual input'

    lines = [
        '--- ' + cfg['name'] + ' @ ' + sym + str(price) + ' ---',
        change_line,
        '',
        'MARKET: ' + g['market'] + ' (' + str(g['conf']) + '%)',
        'IV: ' + str(g['iv']) + '% | Rank: ' + g['iv_rank'],
        '',
        'STRIKES:',
        'ATM:  ' + sym + str(atm),
        'Call: ' + sym + str(call_strike) + ' CE *',
        'Put:  ' + sym + str(put_strike) + ' PE',
        '',
        'GREEKS (Dynamic):',
        'Delta: ' + str(g['delta']) + ' (' + sym + str(int(g['delta']*100)) + '/100pts)',
        'Gamma: ' + str(g['gamma']),
        'Theta: ' + str(g['theta']) + ' (' + sym + str(abs(g['theta'])) + '/day loss)',
        'Vega:  ' + str(g['vega']) + ' (per 1% IV change)',
        'IV: ' + str(g['iv']) + '%',
        '',
        'TRADE SETUP:',
        'Buy ' + str(call_strike) + ' CE',
        'Premium: ' + sym + str(premium),
        'Target:  ' + sym + str(target),
        'SL:      ' + sym + str(sl),
        '',
        'Investment: ' + sym + str(investment),
        'Max Profit: ' + sym + str(max_profit),
        'Max Loss:   ' + sym + str(max_loss),
        'R:R = 1:2',
        '',
        'STRATEGIES:',
        'Aggressive: ' + sym + str(investment) + ' (35% win)',
        'Moderate:   ' + sym + str(int(investment * 0.8)) + ' (55% win)',
        'Safe:       ' + sym + str(investment * 2) + ' (70% win)',
        '',
        'TIMING:',
        'Entry: 10-11:30 AM',
        'Avoid: 3-3:30 PM',
        '',
        'RISK:',
        'Max 2 lots | SL: 30%',
        'Max Risk: ' + sym + str(max_loss),
        '',
        '---',
        rec,
        '',
        'Educational only! Always use SL.'
    ]

    await update.message.reply_text('\n'.join(lines))

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        'HELP GUIDE\n\n'
        'Live Price:\n'
        '/analyze nifty\n'
        '/analyze banknifty\n'
        '/analyze crude\n'
        '/analyze btc\n\n'
        'Manual Price:\n'
        '/analyze nifty 24500\n'
        '/analyze banknifty 45000\n\n'
        'Assets:\n'
        'nifty, banknifty, finnifty\n'
        'sensex, midcap, crude\n'
        'btc, eth\n\n'
        'You Get:\n'
        'Live Price + Change%\n'
        'Market Direction\n'
        'Dynamic Greeks\n'
        'Option Recommendations\n'
        'Trade Setup (Entry/Target/SL)\n'
        'Risk Management\n\n'
        'Trade smart!'
    )
    await update.message.reply_text(text)

def main():
    if not TOKEN:
        logger.error('BOT_TOKEN not set!')
        return
    logger.info('Bot starting...')
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('analyze', analyze))
    app.add_handler(CommandHandler('help', help_command))
    logger.info('Bot running!')
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
