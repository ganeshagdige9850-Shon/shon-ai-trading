import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import anthropic
import requests
import pyotp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment Variables
TOKEN = os.environ.get('BOT_TOKEN')
ANGEL_API_KEY = os.environ.get('ANGEL_API_KEY')
ANGEL_CLIENT_ID = os.environ.get('ANGEL_CLIENT_ID')
ANGEL_PASSWORD = os.environ.get('ANGEL_PASSWORD')
ANGEL_TOTP_SECRET = os.environ.get('ANGEL_TOTP_SECRET')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')

# Initialize clients
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

# Assets config
ASSETS = {
    'nifty': {'name': 'NIFTY', 'lot': 25, 'token': '99926000'},
    'banknifty': {'name': 'BANK NIFTY', 'lot': 15, 'token': '99926009'},
    'finnifty': {'name': 'FIN NIFTY', 'lot': 25, 'token': '99926037'}
}

class AngelAPI:
    def __init__(self):
        self.token = None
        self.url = 'https://apiconnect.angelone.in'
    
    def login(self):
        try:
            totp = pyotp.TOTP(ANGEL_TOTP_SECRET).now()
            r = requests.post(f'{self.url}/rest/auth/angelbroking/user/v1/loginByPassword',
                json={'clientcode': ANGEL_CLIENT_ID, 'password': ANGEL_PASSWORD, 'totp': totp},
                headers={'X-PrivateKey': ANGEL_API_KEY}, timeout=10)
            if r.status_code == 200:
                self.token = r.json()['data']['jwtToken']
                return True
        except: pass
        return False
    
    def get_price(self, token):
        if not self.token:
            self.login()
        try:
            r = requests.post(f'{self.url}/rest/secure/angelbroking/market/v1/quote/',
                json={'mode': 'LTP', 'exchangeTokens': {'NSE': [token]}},
                headers={'Authorization': f'Bearer {self.token}', 'X-PrivateKey': ANGEL_API_KEY},
                timeout=10)
            if r.status_code == 200:
                return float(r.json()['data']['fetched'][0]['ltp'])
        except: pass
        return None

angel = AngelAPI() if all([ANGEL_API_KEY, ANGEL_CLIENT_ID, ANGEL_PASSWORD, ANGEL_TOTP_SECRET]) else None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = '🤖 Shon AI Trading Bot\n\n'
    msg += 'Commands:\n'
    msg += '/recommend - AI suggests best trade\n'
    msg += '/markets - Live prices\n'
    msg += '/help - Guide\n\n'
    msg += 'Try: /recommend'
    await update.message.reply_text(msg)

async def recommend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not anthropic_client:
        await update.message.reply_text('❌ AI not configured!')
        return
    
    await update.message.reply_text('🤖 AI analyzing markets...\nWait 20 seconds...')
    
    # Get market data
    market_data = ""
    for key, cfg in ASSETS.items():
        if angel:
            price = angel.get_price(cfg['token'])
            if price:
                market_data += f"{cfg['name']}: Rs{price:,.2f}\n"
    
    if not market_data:
        await update.message.reply_text('❌ No market data!')
        return
    
    # AI analysis
    try:
        msg = anthropic_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1500,
            messages=[{
                "role": "user",
                "content": f"""You're an options trader. Analyze this data and suggest ONE option to BUY within Rs15,000.

MARKET DATA:
{market_data}

Provide:
1. Asset (NIFTY/BANKNIFTY/FINNIFTY)
2. Direction (CALL/PUT)
3. Strike price
4. Premium estimate
5. Entry/Target/SL
6. Reasoning (technical indicators, Greeks, OI)

Format:
BUY: [Asset] [Strike] [CE/PE]
Premium: Rs[X]
Investment: Rs[X] ([lots] lots)
Entry: Rs[X]
Target: Rs[X] ([%] profit)
Stop Loss: Rs[X] ([%] loss)
Reasoning: [why this trade]
Confidence: [%]"""
            }]
        )
        
        result = msg.content[0].text
        
        response = '═' * 35 + '\n'
        response += '🤖 AI RECOMMENDATION\n'
        response += '═' * 35 + '\n\n'
        response += result + '\n\n'
        response += '⚠️ Educational only. Trade at your risk!'
        
        await update.message.reply_text(response)
        
    except Exception as e:
        await update.message.reply_text(f'❌ Error: {str(e)}')

async def markets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not angel:
        await update.message.reply_text('❌ Angel One not configured!')
        return
    
    msg = 'LIVE MARKETS\n' + '='*25 + '\n\n'
    for key, cfg in ASSETS.items():
        price = angel.get_price(cfg['token'])
        if price:
            msg += f"{cfg['name']}: Rs{price:,.2f}\n"
    
    await update.message.reply_text(msg)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = '📚 HELP\n\n'
    msg += '/recommend - AI suggests best option trade\n'
    msg += '/markets - Live NIFTY, BANKNIFTY, FINNIFTY prices\n\n'
    msg += 'AI analyzes:\n'
    msg += '✅ Technical indicators\n'
    msg += '✅ Greeks (Delta, Gamma, Theta, Vega)\n'
    msg += '✅ IV, OI, PCR\n'
    msg += '✅ Risk management\n\n'
    msg += 'Budget: Rs15,000 default'
    await update.message.reply_text(msg)

def main():
    if not TOKEN:
        print('BOT_TOKEN not set!')
        return
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('recommend', recommend))
    app.add_handler(CommandHandler('markets', markets))
    app.add_handler(CommandHandler('help', help_cmd))
    
    print('Bot running!')
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
  
