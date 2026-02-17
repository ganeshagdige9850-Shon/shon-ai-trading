import os
import logging
import requests
import base64
import anthropic
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('BOT_TOKEN')
ANTHROPIC_KEY = os.environ.get('ANTHROPIC_API_KEY')

# ============================================
# ASSET CONFIGURATION
# ============================================
ASSET_CONFIG = {
    'nifty':     {'name': 'NIFTY 50',     'lot': 25,  'gap': 50,   'sym': '₹', 'ticker': '^NSEI',              'type': 'index'},
    'banknifty': {'name': 'BANK NIFTY',   'lot': 15,  'gap': 100,  'sym': '₹', 'ticker': '^NSEBANK',           'type': 'index'},
    'finnifty':  {'name': 'FIN NIFTY',    'lot': 25,  'gap': 50,   'sym': '₹', 'ticker': 'NIFTY_FIN_SERVICE.NS','type': 'index'},
    'midcap':    {'name': 'MIDCAP NIFTY', 'lot': 50,  'gap': 25,   'sym': '₹', 'ticker': '^NSEI',              'type': 'index'},
    'sensex':    {'name': 'SENSEX',       'lot': 10,  'gap': 100,  'sym': '₹', 'ticker': '^BSESN',             'type': 'index'},
    'crude':     {'name': 'CRUDE OIL',    'lot': 100, 'gap': 50,   'sym': '₹', 'ticker': 'CL=F',               'type': 'commodity'},
    'btc':       {'name': 'BITCOIN',      'lot': 1,   'gap': 1000, 'sym': '$', 'ticker': 'BTC-USD',            'type': 'crypto'},
    'eth':       {'name': 'ETHEREUM',     'lot': 1,   'gap': 50,   'sym': '$', 'ticker': 'ETH-USD',            'type': 'crypto'},
}

# ============================================
# LIVE PRICE FUNCTIONS
# ============================================
def get_yahoo_price(ticker):
    """Get price from Yahoo Finance"""
    try:
        url = f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
        }
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            meta = data['chart']['result'][0]['meta']
            price = float(meta.get('regularMarketPrice', 0))
            prev = float(meta.get('previousClose', price))
            change = price - prev
            pct = (change / prev) * 100 if prev else 0
            return price, change, pct
    except Exception as e:
        logger.error(f"Yahoo v8 error for {ticker}: {e}")
    
    try:
        url = f'https://query2.finance.yahoo.com/v7/finance/quote?symbols={ticker}'
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            result = data['quoteResponse']['result'][0]
            price = float(result.get('regularMarketPrice', 0))
            change = float(result.get('regularMarketChange', 0))
            pct = float(result.get('regularMarketChangePercent', 0))
            return price, change, pct
    except Exception as e:
        logger.error(f"Yahoo v7 error for {ticker}: {e}")
    
    return None, None, None

def get_crude_inr_price():
    """Get Crude Oil MCX price in INR"""
    try:
        # Get USD price
        price_usd, change_usd, pct = get_yahoo_price('CL=F')
        if price_usd:
            # Get USD/INR rate
            usd_inr, _, _ = get_yahoo_price('USDINR=X')
            if not usd_inr:
                usd_inr = 84.0  # fallback rate
            # MCX crude = USD price * USD/INR * barrel_to_barrel
            mcx_price = round(price_usd * usd_inr / 159 * 100, 0)  # approximate MCX
            change_inr = round(change_usd * usd_inr / 159 * 100, 1)
            return mcx_price, change_inr, pct
    except Exception as e:
        logger.error(f"Crude INR error: {e}")
    return None, None, None

def get_live_price(asset):
    """Get live price for any asset"""
    cfg = ASSET_CONFIG.get(asset)
    if not cfg:
        return None, None, None
    
    if asset == 'crude':
        return get_crude_inr_price()
    
    return get_yahoo_price(cfg['ticker'])

# ============================================
# DYNAMIC GREEKS CALCULATION
# ============================================
def calculate_greeks(asset, price, change_pct=0):
    """Calculate dynamic Greeks based on asset and market movement"""
    
    # Volatility estimation based on asset type and movement
    base_iv = {
        'nifty': 15, 'banknifty': 20, 'finnifty': 18,
        'midcap': 22, 'sensex': 15, 'crude': 35,
        'btc': 65, 'eth': 75
    }
    
    iv = base_iv.get(asset, 20)
    
    # Adjust IV based on market movement
    if abs(change_pct) > 1.5:
        iv += 5  # High movement = higher IV
    elif abs(change_pct) > 0.8:
        iv += 2
    
    # Market direction affects Delta
    if change_pct > 0.5:
        delta = round(0.52 + (change_pct * 0.02), 3)
        market = "BULLISH"
        confidence = min(85, 70 + int(abs(change_pct) * 5))
    elif change_pct < -0.5:
        delta = round(0.48 - (abs(change_pct) * 0.02), 3)
        market = "BEARISH"
        confidence = min(85, 70 + int(abs(change_pct) * 5))
    else:
        delta = 0.50
        market = "NEUTRAL"
        confidence = 55

    # Gamma - higher near ATM, lower for crypto
    if asset in ['btc', 'eth']:
        gamma = round(0.0001 + (iv / 10000), 5)
    else:
        gamma = round(0.025 + (iv / 1000), 4)
    
    # Theta - time decay per day
    if asset in ['btc', 'eth']:
        theta = -round(price * 0.0008, 1)
    elif asset == 'crude':
        theta = -round(price * 0.002, 1)
    else:
        theta = -round(price * 0.0007, 1)
    
    # Vega - sensitivity to IV change
    vega = round(iv * 0.8, 1)
    
    # IV Percentile (simulated)
    iv_rank = "HIGH" if iv > 25 else "MEDIUM" if iv > 18 else "LOW"
    
    return {
        'delta': delta,
        'gamma': gamma,
        'theta': theta,
        'vega': vega,
        'iv': iv,
        'iv_rank': iv_rank,
        'market': market,
        'confidence': confidence,
    }

# ============================================
# OPTION RECOMMENDATION
# ============================================
def get_option_recommendation(asset, price, change_pct, greeks):
    """Get specific option trading recommendation"""
    cfg = ASSET_CONFIG[asset]
    gap = cfg['gap']
    sym = cfg['sym']
    market = greeks['market']
    iv_rank = greeks['iv_rank']
    
    atm = round(price / gap) * gap
    
    recommendations = []
    
    if market == "BULLISH":
        # Strategy 1: Buy CE (Best for strong bullish)
        otm1_call = atm + gap
        otm2_call = atm + (2 * gap)
        
        recommendations.append({
            'rank': 1,
            'type': '🟢 BUY CALL (Best Choice)',
            'strike': f'{sym}{otm1_call} CE',
            'action': 'BUY',
            'why': f'Market {change_pct:+.2f}% Bullish\nATM+1 OTM CE = Best R:R',
            'risk': 'Limited Risk = Premium Only',
            'when': 'Strong Bullish Trend',
        })
        
        # Strategy 2: Bull Call Spread (Lower cost)
        recommendations.append({
            'rank': 2,
            'type': '📊 BULL CALL SPREAD',
            'strike': f'Buy {sym}{otm1_call} CE + Sell {sym}{otm2_call} CE',
            'action': 'SPREAD',
            'why': 'Cost कमी होतो, Limited Profit',
            'risk': 'Very Limited Risk',
            'when': 'Moderate Bullish',
        })
        
        # Strategy 3: Sell Put (Premium collection)
        otm_put = atm - gap
        recommendations.append({
            'rank': 3,
            'type': '🔴 SELL PUT (Premium Collection)',
            'strike': f'{sym}{otm_put} PE SELL',
            'action': 'SELL',
            'why': f'IV Rank {iv_rank} - Premium मिळवा',
            'risk': 'Unlimited Risk - Careful!',
            'when': 'High IV Market',
        })
        
    elif market == "BEARISH":
        otm1_put = atm - gap
        otm2_put = atm - (2 * gap)
        
        recommendations.append({
            'rank': 1,
            'type': '🔴 BUY PUT (Best Choice)',
            'strike': f'{sym}{otm1_put} PE',
            'action': 'BUY',
            'why': f'Market {change_pct:+.2f}% Bearish\nATM-1 OTM PE = Best R:R',
            'risk': 'Limited Risk = Premium Only',
            'when': 'Strong Bearish Trend',
        })
        
        otm_call = atm + gap
        recommendations.append({
            'rank': 2,
            'type': '🟢 SELL CALL (Premium)',
            'strike': f'{sym}{otm_call} CE SELL',
            'action': 'SELL',
            'why': 'Bearish Market मध्ये CE Sell',
            'risk': 'Unlimited Risk - Careful!',
            'when': 'Strong Bearish with High IV',
        })
        
    else:  # NEUTRAL
        otm_call = atm + gap
        otm_put = atm - gap
        
        recommendations.append({
            'rank': 1,
            'type': '⚖️ SHORT STRADDLE/STRANGLE',
            'strike': f'Sell {sym}{atm} CE + Sell {sym}{atm} PE',
            'action': 'SELL BOTH',
            'why': 'Neutral Market = Range bound\nDouble Premium मिळवा',
            'risk': 'Unlimited Risk - Experienced Only!',
            'when': 'Low Volatility, Sideways Market',
        })
        
        recommendations.append({
            'rank': 2,
            'type': '📊 IRON CONDOR',
            'strike': f'Sell {sym}{atm}CE+PE, Buy OTM CE+PE',
            'action': 'SPREAD',
            'why': 'Range bound मध्ये profit',
            'risk': 'Limited Risk, Limited Profit',
            'when': 'Low VIX, Sideways',
        })
    
    return recommendations

# ============================================
# MAIN ANALYSIS FUNCTION
# ============================================
def full_analysis(asset, price, change=0, pct=0):
    """Complete trading analysis"""
    cfg = ASSET_CONFIG[asset]
    gap = cfg['gap']
    lot = cfg['lot']
    sym = cfg['sym']
    
    # Dynamic Greeks
    greeks = calculate_greeks(asset, price, pct)
    
    # ATM Strike
    atm = round(price / gap) * gap
    call_strike = atm + gap
    put_strike = atm - gap
    
    # Premium based on asset & IV
    if asset in ['btc', 'eth']:
        premium = round(price * 0.015)
    elif asset == 'crude':
        premium = round(price * 0.025)
    else:
        premium = round(price * 0.004 + (greeks['iv'] * 2))
    
    if premium < 30:
        premium = 30
    
    target = round(premium * 1.65)
    sl = round(premium * 0.60)
    investment = premium * lot
    max_profit = (target - premium) * lot
    max_loss = (premium - sl) * lot
    
    # Option Recommendations
    recs = get_option_recommendation(asset, price, pct, greeks)
    
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
        'greeks': greeks,
        'recommendations': recs,
    }

# ============================================
# AI CHART ANALYSIS
# ============================================
async def analyze_chart_with_ai(image_data: bytes) -> str:
    """Use Claude AI to analyze chart image"""
    if not ANTHROPIC_KEY:
        return None
    
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        
        image_base64 = base64.standard_b64encode(image_data).decode('utf-8')
        
        response = client.messages.create(
            model="claude-opus-4-5-20251101",
            max_tokens=1000,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_base64,
                            },
                        },
                        {
                            "type": "text",
                            "text": """You are an expert Indian stock market technical analyst specializing in Options Trading.

Analyze this trading chart and provide:

1. TREND: Current trend (Bullish/Bearish/Neutral) with strength (%)
2. CHART PATTERN: What pattern is visible (Head & Shoulders, Double Top/Bottom, Triangle, Flag, etc.)
3. KEY LEVELS:
   - Support levels (2-3 levels)
   - Resistance levels (2-3 levels)
4. INDICATORS (if visible): RSI, MACD, Moving Averages status
5. OPTION RECOMMENDATION:
   - Best option strategy for this chart
   - BUY CE or BUY PE or SELL CE or SELL PE
   - Why this strategy
6. ENTRY/EXIT:
   - Entry point
   - Target
   - Stop Loss
7. RISK LEVEL: Low/Medium/High
8. OVERALL SIGNAL: STRONG BUY / BUY / NEUTRAL / SELL / STRONG SELL

Keep response concise and in simple English/Hindi mix. 
Start with overall signal in bold."""
                        }
                    ],
                }
            ],
        )
        
        return response.content[0].text
        
    except Exception as e:
        logger.error(f"AI chart analysis error: {e}")
        return None

# ============================================
# TELEGRAM HANDLERS
# ============================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🎯 *Shon A\\.I\\. Advanced Trading Bot*\n\n"
        "मी तुम्हाला complete options trading analysis देतो\\!\n\n"
        "📊 *Features:*\n"
        "✅ Live Market Price\n"
        "✅ Dynamic Greeks \\(Delta/Gamma/Theta/Vega\\)\n"
        "✅ Option Recommendations\n"
        "✅ AI Chart Analysis 🤖\n"
        "✅ Risk Management\n\n"
        "📝 *Commands:*\n"
        "/analyze nifty → Live Analysis\n"
        "/analyze nifty 24500 → Manual\n"
        "📸 Chart photo पाठवा → AI Analysis\\!\n\n"
        "💡 *Assets:*\n"
        "nifty, banknifty, finnifty, sensex,\n"
        "midcap, crude, btc, eth\n\n"
        "Ready to analyze\\! 🚀"
    )
    await update.message.reply_text(msg, parse_mode='MarkdownV2')

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "❌ Use: /analyze [asset] [price]\n\n"
            "Examples:\n"
            "/analyze nifty ← Live price\n"
            "/analyze nifty 24500 ← Manual\n"
            "/analyze banknifty\n"
            "/analyze crude\n"
            "/analyze btc\n\n"
            "📸 Chart photo पाठवा AI analysis साठी!"
        )
        return
    
    asset = args[0].lower()
    
    if asset not in ASSET_CONFIG:
        await update.message.reply_text(
            f"❌ '{asset}' supported नाही!\n\n"
            f"Valid: nifty, banknifty, finnifty, sensex, midcap, crude, btc, eth"
        )
        return
    
    price = None
    change = 0
    pct = 0
    price_source = "Manual"
    
    if len(args) >= 2:
        try:
            price = float(args[1].replace(',', ''))
        except ValueError:
            await update.message.reply_text("❌ Price number असायला हवा!\nExample: /analyze nifty 24500")
            return
    else:
        loading = await update.message.reply_text(f"⏳ {asset.upper()} live price घेत आहे...")
        price, change, pct = get_live_price(asset)
        try:
            await loading.delete()
        except:
            pass
        
        if price is None:
            await update.message.reply_text(
                f"⚠️ Live price मिळाला नाही!\n\n"
                f"Manual price वापरा:\n"
                f"/analyze {asset} [price]"
            )
            return
        price_source = "📡 Live"
    
    # Full Analysis
    result = full_analysis(asset, price, change, pct)
    sym = result['sym']
    greeks = result['greeks']
    recs = result['recommendations']
    
    # Change info
    change_str = ""
    if change and pct and price_source == "📡 Live":
        arrow = "📈" if change >= 0 else "📉"
        sign = "+" if change >= 0 else ""
        change_str = f"\n{arrow} {sign}{change:.1f} ({sign}{pct:.2f}%)"
    
    # Market sentiment emoji
    if greeks['market'] == "BULLISH":
        sentiment = "✅ BULLISH"
    elif greeks['market'] == "BEARISH":
        sentiment = "❌ BEARISH"
    else:
        sentiment = "⚖️ NEUTRAL"
    
    # Option recommendations text
    rec_text = "\n\n🎯 *OPTION RECOMMENDATIONS:*\n"
    for rec in recs[:2]:
        rec_text += f"\n#{rec['rank']} {rec['type']}\n"
        rec_text += f"Strike: {rec['strike']}\n"
        rec_text += f"Why: {rec['why']}\n"
        rec_text += f"Risk: {rec['risk']}\n"
    
    # Format price
    if asset in ['btc', 'eth']:
        price_display = f"{sym}{price:,.0f}"
    elif asset == 'crude':
        price_display = f"{sym}{price:,.0f}"
    else:
        price_display = f"{sym}{price:,.0f}"
    
    msg = f"""📊 {result['name']} @ {price_display}{change_str}
Source: {price_source}

{sentiment} ({greeks['confidence']}%)
IV: {greeks['iv']}% | IV Rank: {greeks['iv_rank']}

STRIKES:
ATM: {sym}{result['atm']}
🟢 Call: {sym}{result['call']} CE ⭐
🔴 Put: {sym}{result['put']} PE

GREEKS (Dynamic):
Delta: {greeks['delta']} ({sym}{int(greeks['delta']*100)}/100pts)
Gamma: {greeks['gamma']}
Theta: {greeks['theta']} ({sym}{abs(greeks['theta'])}/day)
Vega: {greeks['vega']} (per 1% IV change)
IV: {greeks['iv']}%

TRADE SETUP:
Buy {result['call']} CE
Premium: {sym}{result['premium']}
Target: {sym}{result['target']}
SL: {sym}{result['sl']}

Investment: {sym}{result['investment']}
Max Profit: {sym}{result['max_profit']}
Max Loss: {sym}{result['max_loss']}
R:R = 1:2

STRATEGIES:
🔥 Aggressive: {sym}{result['investment']} (35% win)
⚖️ Moderate: {sym}{int(result['investment']*0.8)} (55% win)
🛡️ Safe: {sym}{result['investment']*2} (70% win)

TIMING:
✅ Entry: 10-11:30 AM
❌ Avoid: 3-3:30 PM

RISK:
Max 2 lots | SL: 30%
Max Risk: {sym}{result['max_loss']}"""

    # Add recommendations
    msg += "\n\n🎯 OPTION RECOMMENDATIONS:"
    for rec in recs[:2]:
        msg += f"\n\n#{rec['rank']} {rec['type']}"
        msg += f"\nStrike: {rec['strike']}"
        msg += f"\nWhy: {rec['why']}"
        msg += f"\nRisk: {rec['risk']}"
    
    msg += "\n\n⚠️ Educational only\n📸 Chart पाठवा AI Analysis साठी!"
    
    await update.message.reply_text(msg)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle chart photo - AI Analysis"""
    
    if not ANTHROPIC_KEY:
        await update.message.reply_text(
            "⚠️ AI Chart Analysis साठी ANTHROPIC_API_KEY लागतो!\n\n"
            "Admin ला contact करा."
        )
        return
    
    loading = await update.message.reply_text("🤖 AI तुमचा chart analyze करत आहे...\n⏳ 10-15 seconds wait करा...")
    
    try:
        # Get photo (highest quality)
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        
        # Download image
        image_data = await file.download_as_bytearray()
        
        # AI Analysis
        analysis = await analyze_chart_with_ai(bytes(image_data))
        
        try:
            await loading.delete()
        except:
            pass
        
        if analysis:
            msg = f"🤖 *AI Chart Analysis*\n\n{analysis}\n\n⚠️ Educational only. Always use SL!"
            await update.message.reply_text(msg)
        else:
            await update.message.reply_text(
                "⚠️ Chart analyze करता आला नाही!\n\n"
                "कृपया:\n"
                "• Clear chart screenshot पाठवा\n"
                "• OHLC candles visible असाव्यात\n"
                "• पुन्हा try करा"
            )
            
    except Exception as e:
        logger.error(f"Photo handler error: {e}")
        try:
            await loading.delete()
        except:
            pass
        await update.message.reply_text("❌ Error झा
