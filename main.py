"""
Shonaiautomated - Compact Version
5-Min Scalping Strategy | Configure via Railway Variables
"""
import os, logging, sys, asyncio, requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from datetime import datetime, time
from collections import deque

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Environment Variables
TOKEN = os.environ.get('BOT_TOKEN')
DHAN_CLIENT_ID = os.environ.get('DHAN_CLIENT_ID')
DHAN_ACCESS_TOKEN = os.environ.get('DHAN_ACCESS_TOKEN')
TRADING_ENABLED = os.environ.get('TRADING_ENABLED', 'false').lower() == 'true'
TRADING_CAPITAL = float(os.environ.get('TRADING_CAPITAL', '8000'))
NIFTY_LOT = 65
NIFTY_STRIKE_GAP = 50

# Calculate or use custom values
MAX_PREMIUM = float(os.environ.get('MAX_PREMIUM', int(TRADING_CAPITAL / NIFTY_LOT)))
CUSTOM_LOTS = os.environ.get('LOTS_PER_TRADE')
if CUSTOM_LOTS:
    LOTS_PER_TRADE = int(CUSTOM_LOTS)
else:
    max_inv = MAX_PREMIUM * NIFTY_LOT
    LOTS_PER_TRADE = max(1, int((TRADING_CAPITAL * 0.95) / max_inv))

# Strategy Config
MAX_POSITIONS = int(os.environ.get('MAX_POSITIONS', '2'))
DAILY_LOSS_LIMIT = float(os.environ.get('DAILY_LOSS_LIMIT', '0.15'))
TARGET = float(os.environ.get('TARGET_PERCENT', '0.30'))
STOP_LOSS = float(os.environ.get('STOP_LOSS_PERCENT', '0.20'))
MAX_HOLD_TIME = int(os.environ.get('MAX_HOLD_TIME_MIN', '25'))
MIN_SIGNAL_POINTS = int(os.environ.get('MIN_SIGNAL_POINTS', '10'))
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

logger.info(f"Config: Capital Rs{TRADING_CAPITAL:,.0f} | Premium Rs{MAX_PREMIUM} | Lots {LOTS_PER_TRADE}")

# Dhan API
class DhanAPI:
    def __init__(self):
        self.client_id = DHAN_CLIENT_ID
        self.token = DHAN_ACCESS_TOKEN
        self.url = 'https://api.dhan.co'
        if not self.client_id or not self.token:
            raise ValueError("Dhan credentials required")
    
    def get_headers(self):
        return {'access-token': self.token, 'Content-Type': 'application/json'}
    
    def get_ltp(self):
        try:
            r = requests.post(f'{self.url}/v2/quotes/ltp', 
                json={'NSE_EQ': ['13']}, headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data.get('status') == 'success':
                    return float(data['data']['NSE_EQ']['13']['last_price'])
        except Exception as e:
            logger.error(f"LTP error: {e}")
        return None
    
    def estimate_premium(self, spot, strike):
        dist = abs(strike - spot)
        if dist <= 50: return 350
        elif dist <= 100: return 200
        elif dist <= 150: return 120
        elif dist <= 200: return 80
        elif dist <= 250: return 50
        return 30

# Trading Bot
class TradingBot:
    def __init__(self):
        self.dhan = DhanAPI()
        self.positions = []
        self.daily_pnl = 0.0
        self.capital = TRADING_CAPITAL
        self.start_capital = TRADING_CAPITAL
        self.history = deque(maxlen=10)
        self.active = TRADING_ENABLED
        logger.info(f"Bot ready: Rs{self.capital:,.0f}, {LOTS_PER_TRADE} lots")
    
    def is_market_open(self):
        now = datetime.now()
        return now.weekday() < 5 and MARKET_OPEN <= now.time() <= MARKET_CLOSE
    
    def update_price(self):
        ltp = self.dhan.get_ltp()
        if ltp:
            self.history.append({'time': datetime.now(), 'price': ltp})
            logger.info(f'NIFTY: Rs{ltp:,.2f}')
            return True
        return False
    
    def detect_signal(self):
        if len(self.history) < 3: return None
        c = list(self.history)[-3:]
        m1, m2 = c[1]['price'] - c[0]['price'], c[2]['price'] - c[1]['price']
        total = c[2]['price'] - c[0]['price']
        if m1 > 0 and m2 > 0 and total >= MIN_SIGNAL_POINTS:
            return {'type': 'CALL', 'price': c[2]['price']}
        if m1 < 0 and m2 < 0 and abs(total) >= MIN_SIGNAL_POINTS:
            return {'type': 'PUT', 'price': c[2]['price']}
        return None
    
    def can_trade(self):
        if len(self.positions) >= MAX_POSITIONS:
            return False, 'Max positions'
        if self.daily_pnl <= -(self.start_capital * DAILY_LOSS_LIMIT):
            return False, 'Loss limit'
        if not self.active:
            return False, 'Disabled'
        return True, 'OK'
    
    async def execute_trade(self, signal, bot, chat):
        can, reason = self.can_trade()
        if not can:
            logger.info(f'Skip: {reason}')
            return
        
        try:
            spot, direction = signal['price'], signal['type']
            options = []
            
            for dist in [50, 100, 150, 200, 250, 300]:
                if direction == 'CALL':
                    strike = int(round((spot + dist) / NIFTY_STRIKE_GAP) * NIFTY_STRIKE_GAP)
                else:
                    strike = int(round((spot - dist) / NIFTY_STRIKE_GAP) * NIFTY_STRIKE_GAP)
                prem = self.dhan.estimate_premium(spot, strike)
                if prem <= MAX_PREMIUM:
                    options.append({'strike': strike, 'premium': prem, 'distance': dist})
            
            if not options:
                logger.warning(f'No options <= Rs{MAX_PREMIUM}')
                return
            
            sel = min(options, key=lambda x: x['distance'])
            strike, prem = sel['strike'], sel['premium']
            qty = NIFTY_LOT * LOTS_PER_TRADE
            inv = prem * qty
            
            if inv > self.capital * 0.95:
                logger.warning(f'Investment Rs{inv:,.0f} too high')
                return
            
            pos = {
                'type': direction, 'strike': strike, 'spot_entry': spot,
                'entry_time': datetime.now(), 'lots': LOTS_PER_TRADE, 'qty': qty,
                'entry_premium': prem, 'investment': inv, 'status': 'OPEN'
            }
            self.positions.append(pos)
            logger.info(f"TRADE: {direction} @ {strike} | Rs{prem} | Qty {qty}")
            
            if bot and chat:
                await bot.send_message(chat, 
                    f"🤖 TRADE\n{direction} @ {strike}\n"
                    f"Premium: Rs{prem} | Lots: {LOTS_PER_TRADE}\n"
                    f"Qty: {qty} | Investment: Rs{inv:,.0f}")
        except Exception as e:
            logger.error(f"Execute error: {e}")
    
    async def monitor_positions(self, curr_price, bot, chat):
        for pos in self.positions[:]:
            if pos['status'] != 'OPEN': continue
            
            hold = (datetime.now() - pos['entry_time']).total_seconds() / 60
            spot_pct = ((curr_price - pos['spot_entry']) / pos['spot_entry']) * 100
            curr_prem = pos['entry_premium'] * (1 + spot_pct * 2 / 100)
            pnl_pct = ((curr_prem - pos['entry_premium']) / pos['entry_premium']) * 100
            
            exit_now, reason = False, ''
            if pnl_pct >= TARGET * 100:
                exit_now, reason = True, 'TARGET'
            elif pnl_pct <= -STOP_LOSS * 100:
                exit_now, reason = True, 'STOPLOSS'
            elif hold > MAX_HOLD_TIME:
                exit_now, reason = True, 'TIME'
            if not self.is_market_open():
                exit_now, reason = True, 'CLOSE'
            
            if exit_now:
                await self.exit_position(pos, reason, curr_prem, bot, chat)
    
    async def exit_position(self, pos, reason, exit_prem, bot, chat):
        try:
            if reason == 'TARGET':
                final = pos['entry_premium'] * (1 + TARGET)
            elif reason == 'STOPLOSS':
                final = pos['entry_premium'] * (1 - STOP_LOSS)
            else:
                final = exit_prem
            
            pnl = (final - pos['entry_premium']) * pos['qty']
            ret = ((final - pos['entry_premium']) / pos['entry_premium']) * 100
            
            self.daily_pnl += pnl
            self.capital += pnl
            pos['status'] = 'CLOSED'
            if pos in self.positions:
                self.positions.remove(pos)
            
            result = "✅ PROFIT" if pnl > 0 else "❌ LOSS"
            logger.info(f"{result}: {pos['type']} @ {pos['strike']} | {reason} | Rs{pnl:+,.0f}")
            
            if bot and chat:
                await bot.send_message(chat,
                    f"{result}\n{pos['type']} @ {pos['strike']}\n"
                    f"Exit: {reason}\nP&L: Rs{pnl:+,.0f} ({ret:+.1f}%)\n"
                    f"Capital: Rs{self.capital:,.0f}\nDaily: Rs{self.daily_pnl:+,.0f}")
        except Exception as e:
            logger.error(f"Exit error: {e}")

bot = TradingBot()

# Telegram Commands
async def start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.message.reply_text(
        f"🤖 DHAN BOT\n\nCapital: Rs{TRADING_CAPITAL:,.0f}\n"
        f"Premium: Rs{MAX_PREMIUM}\nLots: {LOTS_PER_TRADE}\n"
        f"Qty: {NIFTY_LOT * LOTS_PER_TRADE}\n\n"
        f"/status /enable /disable\n/positions /pnl /config")

async def status(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.message.reply_text(
        f"📊 STATUS\n\nTrading: {'🟢 ON' if bot.active else '🔴 OFF'}\n"
        f"Market: {'🟢 OPEN' if bot.is_market_open() else '🔴 CLOSED'}\n\n"
        f"Capital: Rs{bot.capital:,.0f}\n"
        f"Daily P&L: Rs{bot.daily_pnl:+,.0f}\n"
        f"Positions: {len(bot.positions)}/{MAX_POSITIONS}")

async def config(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.message.reply_text(
        f"⚙️ CONFIG\n\nCapital: Rs{TRADING_CAPITAL:,.0f}\n"
        f"Premium: Rs{MAX_PREMIUM}\nLot: {NIFTY_LOT}\n"
        f"Lots/Trade: {LOTS_PER_TRADE}\nQty/Trade: {NIFTY_LOT * LOTS_PER_TRADE}\n\n"
        f"Target: {TARGET*100:.0f}%\nSL: {STOP_LOSS*100:.0f}%\n"
        f"Max Hold: {MAX_HOLD_TIME} min")

async def enable(u: Update, c: ContextTypes.DEFAULT_TYPE):
    bot.active = True
    await u.message.reply_text('🟢 Trading ENABLED!')

async def disable(u: Update, c: ContextTypes.DEFAULT_TYPE):
    bot.active = False
    await u.message.reply_text('🔴 Trading DISABLED!')

async def positions(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if not bot.positions:
        await u.message.reply_text('No positions')
        return
    msg = '📋 POSITIONS\n\n'
    for i, p in enumerate(bot.positions, 1):
        hold = (datetime.now() - p['entry_time']).total_seconds() / 60
        msg += f"{i}. {p['type']} @ {p['strike']}\n   Rs{p['entry_premium']} | {hold:.0f}min\n\n"
    await u.message.reply_text(msg)

async def pnl(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.message.reply_text(
        f"💰 P&L\n\nToday: Rs{bot.daily_pnl:+,.0f}\n"
        f"Return: {(bot.daily_pnl/bot.start_capital*100):+.2f}%\n\n"
        f"Start: Rs{bot.start_capital:,.0f}\n"
        f"Current: Rs{bot.capital:,.0f}")

async def help_cmd(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.message.reply_text(
        "📖 COMMANDS\n\n/start /status /config\n"
        "/enable /disable\n/positions /pnl /help")

# Trading Loop
async def trading_loop(app):
    logger.info('🚀 Trading loop started')
    while True:
        try:
            if not bot.is_market_open():
                await asyncio.sleep(300)
                continue
            
            if bot.update_price():
                signal = bot.detect_signal()
                if signal and bot.active:
                    await bot.execute_trade(signal, app.bot, CHAT_ID)
                if bot.history:
                    await bot.monitor_positions(list(bot.history)[-1]['price'], app.bot, CHAT_ID)
            
            await asyncio.sleep(300)
        except Exception as e:
            logger.error(f'Loop error: {e}')
            await asyncio.sleep(60)

# Main
def main():
    if not TOKEN or not DHAN_CLIENT_ID or not DHAN_ACCESS_TOKEN:
        logger.error('Missing credentials!')
        sys.exit(1)
    
    logger.info(f"Starting: Rs{TRADING_CAPITAL:,.0f}, {LOTS_PER_TRADE} lots")
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('status', status))
    app.add_handler(CommandHandler('config', config))
    app.add_handler(CommandHandler('enable', enable))
    app.add_handler(CommandHandler('disable', disable))
    app.add_handler(CommandHandler('positions', positions))
    app.add_handler(CommandHandler('pnl', pnl))
    app.add_handler(CommandHandler('help', help_cmd))
    
    async def post_init(application):
        asyncio.create_task(trading_loop(application))
    
    app.post_init = post_init
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
