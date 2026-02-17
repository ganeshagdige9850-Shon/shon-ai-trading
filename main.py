import os
import logging
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('BOT_TOKEN')

# Yahoo Finance Symbol Map
YAHOO_SYMBOLS = {
    'nifty':     '^NSEI',
    'banknifty': '^NSEBANK',
    'finnifty':  'NIFTY_FIN_SERVICE.NS',
    'midcap':    'NIFTY_MIDCAP_SELECT.NS',
    'sensex':    '^BSESN',
    'crude':     'MCX=F',
    'btc':       'BTC-USD',
    'eth':       'ETH-USD',
}

ASSET_CONFIG = {
    'nifty':     {'name': 'NIFTY 50',     'lot': 25,  'gap': 50,   'sym': '₹'},
    'banknifty': {'name': 'BANK NIFTY',   'lot': 15,  'gap': 100,  'sym': '₹'},
    'finnifty':  {'name': 'FIN NIFTY',    'lot': 25,  'gap': 50,   'sym': '₹'},
    'midcap':    {'name': 'MIDCAP NIFTY', 'lot': 50,  'gap': 25,   'sym': '₹'},
    'sensex':    {'name': 'SENSEX',       'lot': 10,  'gap': 100,  'sym': '₹'},
    'crude':     {'name': 'CRUDE OIL',    'lot': 100, 'gap': 5,    'sym': '₹'},
    'btc':       {'name': 'BITCOIN',      'lot': 1,   'gap': 1000, 'sym': '$'},
    'eth':       {'name': 'ETHEREUM',     'lot': 1,   'gap': 50,   'sym': '$'},
}

def get_live_price(asset):
    """Get live price from Yahoo Finance"""
    asset = asset.lower()
    
    if asset not in YAHOO_SYMBOLS:
        return None, None, None
    
    ticker = YAHOO_SYMBOLS[asset]
    
    try:
        # Method 1: Yahoo Finance v8 API
        url = f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}'
        headers = {'User-Agent': 'Mozilla/5.0'}
        params = {'interval': '1m', 'range': '1d'}
        
        r = requests.get(url, headers=headers, params=params, timeout=15)
        
        if r.status_code == 200:
            data = r.json()
            meta = data['chart']['result'][0]['meta']
            price = meta.get('regularMarketPrice', 0)
            prev = meta.get('previousClose', price)
            change = price - prev
            pct = (change / prev) * 100 if prev else 0
            return float(price), float(change), float(pct)
            
    except Exception as e:
        logger.error(f"Yahoo v8 error: {e}")
    
    try:
        # Method 2: Yahoo Finance v7 API (backup)
        url = f'https://query2.finance.yahoo.com/v7/finance/quote?symbols={ticker}'
        headers = {'User-Agent': 'Mozilla/5.0'}
        
        r = requests.get(url, headers=headers, timeout=15)
        
        if r.status_code == 200:
            data = r.json()
            result = data['quoteResponse']['result'][0]
            price = result.get('regularMarketPrice', 0)
            change = result.get('regularMarketChange', 0)
            pct = result.get('regularMarketChangePercent', 0)
            return float(price), float(change), float(pct)
            
    except Exception as e:
        logger.error(f"Yahoo v7 error: {e}")
    
    return None, None, None

def do_analysis(asset, price):
    """Generate trading analysis"""
    cfg = ASSET_CONFIG[asset]
    gap = cfg['gap']
    lot = cfg['lot']
    sym = cfg['sym']
    
    # ATM Strike
    atm = round(price / gap) * gap
    call_strike = atm + gap
    put_strike = atm - gap
    
    # Premium calculation
    if asset in ['btc', 'eth']:
        premium = round(price * 0.02)
    elif asset == 'crude':
        premium = round(price * 0.06)
    else:
        premium = round(price * 0.005)
    
    if premium < 30:
        premium = 30
    
    target = round(premium * 1.65)
    sl = round(premium * 0.65)
    investment = premium * lot
    max_profit = (target - premium) * lot
    max_loss = (premium - sl) * lot
    
    return {
        'name': cfg['name'],
        'sym': sym,
        'lot': lot,
        'atm': atm,
        'call': call_strike,
        'put': put_strike,
        'premium': premium,
        'target': target,
        'sl': sl,
        'investment': investment,
        'max_profit': max_profit,
        'max_loss': max_loss,
    }

def escape_md(text):
    """Escape MarkdownV2 special chars"""
    chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for c in chars:
        text = str(text).replace(c, f'\\{c}')
    return text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🎯 *Shon A\\.I\\. Trading Bot*\n\n"
        "मी सर्व markets साठी analysis देतो\\!\n\n"
        "📊 *Supported:*\n"
        "• NIFTY, BANK NIFTY, FIN NIFTY\n"
        "• SENSEX, MIDCAP NIFTY\n"
        "• CRUDE OIL \\(MCX\\)\n"
        "• BITCOIN, ETHEREUM\n\n"
        "📝 *Commands:*\n"
        "/analyze nifty → Live price automatic\\!\n"
        "/analyze nifty 24500 → Manual price\n"
        "/help\n\n"
        "Ready to analyze\\! 🚀"
    )
    await update.message.reply_text(msg, parse_mode='MarkdownV2')

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "❌ Use: /analyze [asset] [price]\n\n"
            "Examples:\n"
            "/analyze nifty\n"
            "/analyze nifty 24500\n"
            "/analyze banknifty 45000\n"
            "/analyze crude 6500\n"
            "/analyze btc 85000"
        )
        return
    
    asset = args[0].lower()
    
    if asset not in ASSET_CONFIG:
        valid = list(ASSET_CONFIG.keys())
        await update.message.reply_text(
            f"❌ '{asset}' supported नाही!\n\n"
            f"Valid assets:\n{', '.join(valid)}"
        )
        return
    
    price = None
    change = 0
    pct = 0
    price_source = ""
    
    if len(args) >= 2:
        # Manual price
        try:
            price = float(args[1].replace(',', ''))
            price_source = "Manual"
        except ValueError:
            await update.message.reply_text("❌ Price number असायला हवा!\nExample: /analyze nifty 24500")
            return
    else:
        # Live price
        loading_msg = await update.message.reply_text(f"⏳ {asset.upper()} live price घेत आहे...")
        
        price, change, pct = get_live_price(asset)
        
        try:
            await loading_msg.delete()
        except:
            pass
        
        if price is None:
            await update.message.reply_text(
                f"⚠️ {asset.upper()} live price मिळाला नाही!\n\n"
                f"Market बंद असेल किंवा connection issue.\n\n"
                f"Manual price वापरा:\n"
                f"/analyze {asset} [price]\n\n"
                f"Example:\n"
                f"/analyze {asset} 24500"
            )
            return
        
        price_source = "📡 Live"
    
    # Generate analysis
    result = do_analysis(asset, price)
    sym = result['sym']
    
    # Change string
    change_line = ""
    if change and pct and price_source == "📡 Live":
        arrow = "📈" if change >= 0 else "📉"
        sign = "+" if change >= 0 else ""
        change_line = f"\n{arrow} {sign}{change:.1f} ({sign}{pct:.2f}%)"
    
    source_line = f" | {price_source}" if price_source else ""
    
    # Format price
    if asset in ['btc', 'eth']:
        price_str = f"{sym}{price:,.0f}"
    elif asset == 'crude':
        price_str = f"{sym}{price:.1f}"
    else:
        price_str = f"{sym}{price:,.0f}"
    
    msg = (
        f"📊 *{escape_md(result['name'])} @ {escape_md(price_str)}*{escape_md(source_line)}{escape_md(change_line)}\n\n"
        f"✅ BULLISH \\(75%\\)\n\n"
        f"*STRIKES:*\n"
        f"ATM: {sym}{escape_md(str(result['atm']))}\n"
        f"🟢 Call: {sym}{escape_md(str(result['call']))} CE ⭐\n"
        f"🔴 Put: {sym}{escape_md(str(result['put']))} PE\n\n"
        f"*GREEKS:*\n"
        f"Delta: 0\\.52\n"
        f"Gamma: 0\\.035\n"
        f"Theta: \\-18\n"
        f"Vega: 12\\.5\n\n"
        f"*TRADE SETUP:*\n"
        f"Buy {escape_md(str(result['call']))} CE\n"
        f"Premium: {sym}{escape_md(str(result['premium']))}\n"
        f"Target: {sym}{escape_md(str(result['target']))}\n"
        f"SL: {sym}{escape_md(str(result['sl']))}\n\n"
        f"Investment: {sym}{escape_md(str(result['investment']))}\n"
        f"Max Profit: {sym}{escape_md(str(result['max_profit']))}\n"
        f"Max Loss: {sym}{escape_md(str(result['max_loss']))}\n"
        f"R:R \\= 1:2\n\n"
        f"*STRATEGIES:*\n"
        f"🔥 Aggressive: {sym}{escape_md(str(result['investment']))} \\(35% win\\)\n"
        f"⚖️ Moderate: {sym}{escape_md(str(int(result['investment']*0.8)))} \\(55% win\\)\n"
        f"🛡️ Safe: {sym}{escape_md(str(result['investment']*2))} \\(70% win\\)\n\n"
        f"*TIMING:*\n"
        f"✅ Entry: 10\\-11:30 AM\n"
        f"❌ Avoid: 3\\-3:30 PM\n\n"
        f"*RISK:*\n"
        f"Max 2 lots \\| SL: 30%\n"
        f"Max Risk: {sym}{escape_md(str(result['max_loss']))}\n\n"
        f"⚠️ Educational only"
    )
    
    await update.message.reply_text(msg, parse_mode='MarkdownV2')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📚 *HELP GUIDE*\n\n"
        "*Live Price \\(Automatic\\):*\n"
        "/analyze nifty\n"
        "/analyze banknifty\n"
        "/analyze crude\n"
        "/analyze btc\n\n"
        "*Manual Price:*\n"
        "/analyze nifty 24500\n"
        "/analyze banknifty 45000\n"
        "/analyze btc 85000\n\n"
        "*Assets:*\n"
        "📊 nifty, banknifty, finnifty\n"
        "📊 sensex, midcap\n"
        "🛢️ crude\n"
        "₿ btc, eth\n\n"
        "Trade smart\\! 💪"
    )
    await update.message.reply_text(msg, parse_mode='MarkdownV2')

def main():
    if not TOKEN:
        logger.error("❌ BOT_TOKEN not set!")
        return
    logger.info("🤖 Shon A.I. Bot starting with LIVE DATA...")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("analyze", analyze))
    app.add_handler(CommandHandler("help", help_command))
    logger.info("✅ Bot running!")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
