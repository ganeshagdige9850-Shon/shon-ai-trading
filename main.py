import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import anthropic
import requests
import pyotp
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment Variables
TOKEN = os.environ.get('BOT_TOKEN')
ANGEL_API_KEY = os.environ.get('ANGEL_API_KEY')
ANGEL_CLIENT_ID = os.environ.get('ANGEL_CLIENT_ID')
ANGEL_PASSWORD = os.environ.get('ANGEL_PASSWORD')
ANGEL_TOTP_SECRET = os.environ.get('ANGEL_TOTP_SECRET')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')

# Initialize AI
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

# Assets
ASSETS = {
    'nifty': {'name': 'NIFTY', 'lot': 25, 'token': '99926000'},
    'banknifty': {'name': 'BANK NIFTY', 'lot': 15, 'token': '99926009'},
    'finnifty': {'name': 'FIN NIFTY', 'lot': 25, 'token': '99926037'}
}

class AngelAPI:
    def __init__(self):
        self.token = None
        self.url = 'https://apiconnect.angelone.in'
        self.configured = all([ANGEL_API_KEY, ANGEL_CLIENT_ID, ANGEL_PASSWORD, ANGEL_TOTP_SECRET])
    
    def login(self):
        if not self.configured:
            logger.error('Angel One not configured!')
            return False
        
        try:
            totp = pyotp.TOTP(ANGEL_TOTP_SECRET).now()
            logger.info(f'TOTP generated: {totp}')
            
            headers = {
                'Content-Type': 'application/json',
                'X-PrivateKey': ANGEL_API_KEY,
                'X-UserType': 'USER',
                'X-SourceID': 'WEB',
                'X-ClientLocalIP': '192.168.1.1',
                'X-ClientPublicIP': '106.193.147.98',
                'X-MACAddress': '00:00:00:00:00:00'
            }
            
            data = {
                'clientcode': ANGEL_CLIENT_ID,
                'password': ANGEL_PASSWORD,
                'totp': totp
            }
            
            logger.info(f'Logging in to Angel One...')
            r = requests.post(
                f'{self.url}/rest/auth/angelbroking/user/v1/loginByPassword',
                json=data,
                headers=headers,
                timeout=15
            )
            
            logger.info(f'Login response status: {r.status_code}')
            
            if r.status_code == 200:
                result = r.json()
                logger.info(f'Login response: {result.get("message")}')
                
                if result.get('status'):
                    self.token = result['data']['jwtToken']
                    logger.info('Login successful!')
                    return True
                else:
                    logger.error(f'Login failed: {result.get("message")}')
            else:
                logger.error(f'Login failed with status {r.status_code}')
                
        except Exception as e:
            logger.error(f'Login error: {e}')
        
        return False
    
    def get_price(self, token_id):
        if not self.token:
            logger.info('No token, logging in...')
            if not self.login():
                return None
        
        try:
            headers = {
                'Authorization': f'Bearer {self.token}',
                'Content-Type': 'application/json',
                'X-PrivateKey': ANGEL_API_KEY,
                'X-UserType': 'USER',
                'X-SourceID': 'WEB',
                'X-ClientLocalIP': '192.168.1.1',
                'X-ClientPublicIP': '106.193.147.98',
                'X-MACAddress': '00:00:00:00:00:00'
            }
            
            data = {
                'mode': 'LTP',
                'exchangeTokens': {
                    'NSE': [token_id]
                }
            }
            
            logger.info(f'Fetching price for token {token_id}...')
            r = requests.post(
                f'{self.url}/rest/secure/angelbroking/market/v1/quote/',
                json=data,
                headers=headers,
                timeout=10
            )
            
            logger.info(f'Quote response status: {r.status_code}')
            
            if r.status_code == 200:
                result = r.json()
                if result.get('status') and result.get('data'):
                    fetched = result['data'].get('fetched', [])
                    if fetched:
                        price = float(fetched[0]['ltp'])
                        logger.info(f'Price fetched: {price}')
                        return price
            
        except Exception as e:
            logger.error(f'Price fetch error: {e}')
        
        return None
    
    def test_connection(self):
        """Test Angel One connection"""
        if not self.configured:
            return False, 'Angel One credentials not configured'
        
        if self.login():
            return True, 'Connected successfully'
        else:
            return False, 'Login failed - check credentials'

# Initialize Angel API
angel = AngelAPI()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check configuration
    angel_status = '✅ Configured' if angel.configured else '❌ Not configured'
    ai_status = '✅ Configured' if anthropic_client else '❌ Not configured'
    
    msg = '🤖 Shon AI Trading Bot\n\n'
    msg += 'Status:\n'
    msg += f'Angel One: {angel_status}\n'
    msg += f'AI (Claude): {ai_status}\n\n'
    msg += 'Commands:\n'
    msg += '/test - Test Angel One connection\n'
    msg += '/recommend - AI suggests trade\n'
    msg += '/markets - Live prices\n'
    msg += '/help - Guide\n\n'
    
    if not angel.configured:
        msg += '⚠️ Angel One not configured!\n'
        msg += 'Add these to Railway:\n'
        msg += '- ANGEL_API_KEY\n'
        msg += '- ANGEL_CLIENT_ID\n'
        msg += '- ANGEL_PASSWORD\n'
        msg += '- ANGEL_TOTP_SECRET\n'
    
    await update.message.reply_text(msg)

async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test Angel One connection"""
    await update.message.reply_text('Testing Angel One connection...')
    
    success, message = angel.test_connection()
    
    if success:
        # Try to fetch a price
        price = angel.get_price(ASSETS['nifty']['token'])
        if price:
            await update.message.reply_text(
                f'✅ Angel One Connected!\n\n'
                f'Test: NIFTY = Rs{price:,.2f}\n\n'
                f'Ready to use /recommend'
            )
        else:
            await update.message.reply_text(
                f'⚠️ Login OK but data fetch failed\n'
                f'Check market hours: 9:15 AM - 3:30 PM'
            )
    else:
        await update.message.reply_text(
            f'❌ Connection Failed\n\n'
            f'Error: {message}\n\n'
            f'Check Railway variables:\n'
            f'- ANGEL_API_KEY\n'
            f'- ANGEL_CLIENT_ID\n'
            f'- ANGEL_PASSWORD\n'
            f'- ANGEL_TOTP_SECRET'
        )

async def recommend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check AI
    if not anthropic_client:
        await update.message.reply_text(
            '❌ AI not configured!\n\n'
            'Add ANTHROPIC_API_KEY to Railway:\n'
            'Get it from: console.anthropic.com'
        )
        return
    
    # Check Angel One
    if not angel.configured:
        await update.message.reply_text(
            '❌ Angel One not configured!\n\n'
            'Use /test to check connection'
        )
        return
    
    await update.message.reply_text(
        '🤖 AI analyzing markets...\n'
        'Fetching live data...\n'
        'Wait 20 seconds...'
    )
    
    # Get market data
    market_data = ""
    prices_found = 0
    
    for key, cfg in ASSETS.items():
        price = angel.get_price(cfg['token'])
        if price:
            market_data += f"{cfg['name']}: Rs{price:,.2f}\n"
            prices_found += 1
            logger.info(f'{cfg["name"]}: Rs{price:,.2f}')
    
    if prices_found == 0:
        now = datetime.now()
        current_time = now.strftime('%I:%M %p')
        
        await update.message.reply_text(
            f'❌ No market data available!\n\n'
            f'Current time: {current_time}\n\n'
            f'Possible reasons:\n'
            f'1. Market closed (9:15 AM - 3:30 PM only)\n'
            f'2. Weekend/Holiday\n'
            f'3. Angel One API issue\n\n'
            f'Try:\n'
            f'1. /test - Check connection\n'
            f'2. Wait for market hours\n'
            f'3. Check Railway logs'
        )
        return
    
    # AI analysis
    try:
        msg = anthropic_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1500,
            messages=[{
                "role": "user",
                "content": f"""You're an expert options trader. Analyze this LIVE market data and suggest ONE option to BUY within Rs15,000 budget.

LIVE MARKET DATA:
{market_data}

Provide detailed recommendation including:
1. Which asset (NIFTY/BANK NIFTY/FIN NIFTY)
2. Direction (CALL or PUT)
3. Strike price (ATM/OTM)
4. Premium estimate
5. Entry/Target/Stop Loss
6. Reasoning based on:
   - Technical indicators (RSI, MA)
   - Option Greeks (Delta, Gamma, Theta, Vega)
   - IV levels
   - OI patterns
   - PCR ratio
   - Risk management

Format clearly:
BUY RECOMMENDATION:
Asset: [name]
Option: [strike] [CE/PE]
Premium: Rs[X]
Investment: Rs[X] ([lots] lots)

ANALYSIS:
[Technical + Greeks + IV + OI + PCR]

TRADE SETUP:
Entry: Rs[X]
Target: Rs[X] ([%] profit)
Stop Loss: Rs[X] ([%] loss)
Risk:Reward = 1:[X]

REASONING:
[Why this is best trade right now]

CONFIDENCE: [%]"""
            }]
        )
        
        result = msg.content[0].text
        
        response = '═' * 40 + '\n'
        response += '🤖 AI RECOMMENDATION\n'
        response += '═' * 40 + '\n\n'
        response += result + '\n\n'
        response += '⚠️ DISCLAIMER:\n'
        response += 'Educational only. Trade at your risk!\n'
        response += 'Always use stop loss!'
        
        # Split if too long
        if len(response) > 4000:
            parts = [response[i:i+3900] for i in range(0, len(response), 3900)]
            for part in parts:
                await update.message.reply_text(part)
        else:
            await update.message.reply_text(response)
        
    except Exception as e:
        logger.error(f'AI error: {e}')
        await update.message.reply_text(
            f'❌ AI analysis failed!\n\n'
            f'Error: {str(e)}\n\n'
            f'Check ANTHROPIC_API_KEY in Railway'
        )

async def markets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not angel.configured:
        await update.message.reply_text(
            '❌ Angel One not configured!\n'
            'Use /test to check'
        )
        return
    
    await update.message.reply_text('Fetching live prices...')
    
    msg = 'LIVE MARKETS\n' + '='*30 + '\n\n'
    now = datetime.now()
    msg += f'Time: {now.strftime("%I:%M %p")}\n\n'
    
    prices_found = 0
    for key, cfg in ASSETS.items():
        price = angel.get_price(cfg['token'])
        if price:
            msg += f"{cfg['name']}: Rs{price:,.2f}\n"
            prices_found += 1
    
    if prices_found == 0:
        msg += '\n❌ No data available\n'
        msg += 'Market may be closed\n'
        msg += 'Hours: 9:15 AM - 3:30 PM'
    else:
        msg += '\nUse /recommend for AI analysis'
    
    await update.message.reply_text(msg)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = '📚 HELP GUIDE\n\n'
    msg += 'COMMANDS:\n'
    msg += '/test - Test Angel One connection\n'
    msg += '/recommend - AI suggests best trade\n'
    msg += '/markets - Live NIFTY, BANK, FIN prices\n\n'
    msg += 'AI ANALYZES:\n'
    msg += '✅ Technical indicators (RSI, MA)\n'
    msg += '✅ Option Greeks (Δ, Γ, Θ, ν)\n'
    msg += '✅ IV, OI, PCR\n'
    msg += '✅ Risk management\n\n'
    msg += 'REQUIREMENTS:\n'
    msg += '1. Angel One account (for data)\n'
    msg += '2. Anthropic API (for AI)\n'
    msg += '3. Market hours: 9:15 AM - 3:30 PM\n\n'
    msg += 'BUDGET: Rs15,000 default\n\n'
    msg += 'TROUBLESHOOTING:\n'
    msg += 'If /recommend fails:\n'
    msg += '1. Run /test first\n'
    msg += '2. Check market hours\n'
    msg += '3. Check Railway variables\n'
    msg += '4. Check Railway logs'
    
    await update.message.reply_text(msg)

def main():
    if not TOKEN:
        print('❌ BOT_TOKEN not set!')
        return
    
    logger.info('Starting bot...')
    logger.info(f'Angel One configured: {angel.configured}')
    logger.info(f'Anthropic configured: {anthropic_client is not None}')
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('test', test))
    app.add_handler(CommandHandler('recommend', recommend))
    app.add_handler(CommandHandler('markets', markets))
    app.add_handler(CommandHandler('help', help_cmd))
    
    logger.info('Bot running!')
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
