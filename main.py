
import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import requests
import pyotp
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('BOT_TOKEN')
ANGEL_API_KEY = os.environ.get('ANGEL_API_KEY')
ANGEL_CLIENT_ID = os.environ.get('ANGEL_CLIENT_ID')
ANGEL_PASSWORD = os.environ.get('ANGEL_PASSWORD')
ANGEL_TOTP_SECRET = os.environ.get('ANGEL_TOTP_SECRET')

ASSETS = {
    'nifty': {'name': 'NIFTY', 'lot': 25, 'token': '99926000', 'gap': 50},
    'banknifty': {'name': 'BANK NIFTY', 'lot': 15, 'token': '99926009', 'gap': 100},
    'finnifty': {'name': 'FIN NIFTY', 'lot': 25, 'token': '99926037', 'gap': 50}
}

class AngelAPI:
    def __init__(self):
        self.token = None
        self.url = 'https://apiconnect.angelone.in'
    
    def login(self):
        try:
            totp = pyotp.TOTP(ANGEL_TOTP_SECRET).now()
            r = requests.post(
                f'{self.url}/rest/auth/angelbroking/user/v1/loginByPassword',
                json={'clientcode': ANGEL_CLIENT_ID, 'password': ANGEL_PASSWORD, 'totp': totp},
                headers={'X-PrivateKey': ANGEL_API_KEY, 'Content-Type': 'application/json'},
                timeout=15
            )
            if r.status_code == 200 and r.json().get('status'):
                self.token = r.json()['data']['jwtToken']
                return True
        except: pass
        return False
    
    def get_price(self, token_id):
        if not self.token:
            self.login()
        try:
            r = requests.post(
                f'{self.url}/rest/secure/angelbroking/market/v1/quote/',
                json={'mode': 'LTP', 'exchangeTokens': {'NSE': [token_id]}},
                headers={'Authorization': f'Bearer {self.token}', 'X-PrivateKey': ANGEL_API_KEY},
                timeout=10
            )
            if r.status_code == 200:
                data = r.json()['data']['fetched'][0]
                return float(data['ltp']), float(data.get('pChange', 0))
        except: pass
        return None, None

angel = AngelAPI()

def analyze_simple(price, change, cfg):
    gap = cfg['gap']
    atm = round(price / gap) * gap
    
    if change > 1.0:
        signal, action, strike, conf = 'STRONG BULLISH', 'BUY CALL', atm + gap, 80
    elif change > 0.3:
        signal, action, strike, conf = 'BULLISH', 'BUY CALL', atm, 65
    elif change < -1.0:
        signal, action, strike, conf = 'STRONG BEARISH', 'BUY PUT', atm - gap, 80
    elif change < -0.3:
        signal, action, strike, conf = 'BEARISH', 'BUY PUT', atm, 65
    else:
        signal, action, strike, conf = 'NEUTRAL', 'WAIT', atm, 50
    
    premium = int(price * 0.02)
    investment = premium * cfg['lot']
    
    return {
        'signal': signal, 'action': action, 'strike': strike,
        'premium': premium, 'investment': investment, 'conf': conf, 'atm': atm
    }

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        '🤖 Shon Trading Bot (FREE)\n\n'
        'Live market data + Basic analysis\n'
        'No AI costs!\n\n'
        'Commands:\n'
        '/recommend - Get trade suggestion\n'
        '/markets - Live prices\n'
        '/analyze [asset] - Quick check\n\n'
        'Try: /recommend'
    )

async def recommend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('📊 Analyzing live markets...')
    
    best_score, best_data = 0, None
    
    for key, cfg in ASSETS.items():
        price, change = angel.get_price(cfg['token'])
        if price:
            analysis = analyze_simple(price, change, cfg)
            score = abs(change) * 10 + analysis['conf']
            if score > best_score:
                best_score = score
                best_data = {
                    'asset': cfg['name'], 'price': price, 'change': change,
                    'analysis': analysis, 'lot': cfg['lot']
                }
    
    if not best_data:
        await update.message.reply_text('❌ No market data! Check market hours.')
        return
    
    a = best_data['analysis']
    arrow = '📈' if best_data['change'] > 0 else '📉'
    
    msg = '═' * 35 + '\n📊 TRADE RECOMMENDATION\n' + '═' * 35 + '\n\n'
    msg += f'Asset: {best_data["asset"]}\n'
    msg += f'Spot: Rs{best_data["price"]:,.2f} {arrow}\n'
    msg += f'Change: {best_data["change"]:+.2f}%\n\n'
    msg += f'SIGNAL: {a["signal"]}\n'
    msg += f'Action: {a["action"]}\n\n'
    
    if a['action'] != 'WAIT':
        msg += f'RECOMMENDATION:\n'
        msg += f'Strike: Rs{a["strike"]}\n'
        msg += f'Premium: Rs{a["premium"]} (est.)\n'
        msg += f'Investment: Rs{a["investment"]:,} ({best_data["lot"]} lots)\n'
        msg += f'Entry: Rs{a["premium"]}\n'
        msg += f'Target: Rs{int(a["premium"] * 1.6)} (60% profit)\n'
        msg += f'Stop Loss: Rs{int(a["premium"] * 0.7)} (30% loss)\n\n'
    else:
        msg += 'Market unclear. Better to WAIT.\n\n'
    
    msg += f'Confidence: {a["conf"]}%\n\n'
    msg += '⚠️ Basic analysis (no AI).\n'
    msg += 'Educational only. Trade at your risk!'
    
    await update.message.reply_text(msg)

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text('Use: /analyze [nifty/banknifty/finnifty]')
        return
    
    asset = context.args[0].lower()
    if asset not in ASSETS:
        await update.message.reply_text('❌ Asset not found!')
        return
    
    cfg = ASSETS[asset]
    price, change = angel.get_price(cfg['token'])
    
    if not price:
        await update.message.reply_text('❌ No data! Check market hours.')
        return
    
    analysis = analyze_simple(price, change, cfg)
    arrow = '📈' if change > 0 else '📉'
    
    msg = f'{cfg["name"]}\n' + '=' * 25 + '\n'
    msg += f'Spot: Rs{price:,.2f} {arrow}\n'
    msg += f'Change: {change:+.2f}%\n'
    msg += f'ATM: Rs{analysis["atm"]}\n\n'
    msg += f'Signal: {analysis["signal"]}\n'
    msg += f'Action: {analysis["action"]}\n'
    msg += f'Confidence: {analysis["conf"]}%'
    
    await update.message.reply_text(msg)

async def markets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = 'LIVE MARKETS\n' + '='*25 + '\n\n'
    
    for key, cfg in ASSETS.items():
        price, change = angel.get_price(cfg['token'])
        if price:
            arrow = '📈' if change >= 0 else '📉'
            msg += f'{cfg["name"]}: Rs{price:,.2f} {arrow} {change:+.2f}%\n'
    
    await update.message.reply_text(msg)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        '📚 HELP - FREE VERSION\n\n'
        'This bot uses:\n'
        '✅ Live Angel One data (FREE)\n'
        '✅ Basic technical analysis (FREE)\n\n'
        'Commands:\n'
        '/recommend - Best trade suggestion\n'
        '/markets - Live prices\n'
        '/analyze [asset] - Quick check\n\n'
        'Features:\n'
        '- Live spot price\n'
        '- Signal (Bullish/Bearish)\n'
        '- Strike suggestion\n'
        '- Entry/Target/SL\n\n'
        '100% FREE!'
    )

def main():
    if not TOKEN:
        print('BOT_TOKEN not set!')
        return
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('recommend', recommend))
    app.add_handler(CommandHandler('analyze', analyze))
    app.add_handler(CommandHandler('markets', markets))
    app.add_handler(CommandHandler('help', help_cmd))
    
    print('Free bot running!')
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
          
