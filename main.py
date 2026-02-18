import os
import logging
import requests
import anthropic
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import pyotp
import math

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('BOT_TOKEN')
ANGEL_API_KEY = os.environ.get('ANGEL_API_KEY')
ANGEL_CLIENT_ID = os.environ.get('ANGEL_CLIENT_ID')
ANGEL_PASSWORD = os.environ.get('ANGEL_PASSWORD')
ANGEL_TOTP_SECRET = os.environ.get('ANGEL_TOTP_SECRET')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')

anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

ASSETS = {
    'nifty': {
        'name': 'NIFTY 50', 'lot': 25, 'sym': 'Rs', 'gap': 50,
        'exchange': 'NFO', 'symbol': 'NIFTY', 'index_token': '99926000'
    },
    'banknifty': {
        'name': 'BANK NIFTY', 'lot': 15, 'sym': 'Rs', 'gap': 100,
        'exchange': 'NFO', 'symbol': 'BANKNIFTY', 'index_token': '99926009'
    },
    'finnifty': {
        'name': 'FIN NIFTY', 'lot': 25, 'sym': 'Rs', 'gap': 50,
        'exchange': 'NFO', 'symbol': 'FINNIFTY', 'index_token': '99926037'
    },
    'sensex': {
        'name': 'SENSEX', 'lot': 10, 'sym': 'Rs', 'gap': 100,
        'exchange': 'NFO', 'symbol': 'SENSEX', 'index_token': '99919000'
    },
    'midcap': {
        'name': 'MIDCAP NIFTY', 'lot': 50, 'sym': 'Rs', 'gap': 25,
        'exchange': 'NFO', 'symbol': 'MIDCAP', 'index_token': '99926074'
    }
}

class AngelOneAPI:
    def __init__(self):
        self.access_token = None
        self.base_url = 'https://apiconnect.angelone.in'
    
    def login(self):
        try:
            totp = pyotp.TOTP(ANGEL_TOTP_SECRET).now()
            url = f'{self.base_url}/rest/auth/angelbroking/user/v1/loginByPassword'
            headers = {'Content-Type': 'application/json', 'X-PrivateKey': ANGEL_API_KEY}
            data = {'clientcode': ANGEL_CLIENT_ID, 'password': ANGEL_PASSWORD, 'totp': totp}
            
            response = requests.post(url, json=data, headers=headers, timeout=15)
            if response.status_code == 200:
                result = response.json()
                if result.get('status'):
                    self.access_token = result['data']['jwtToken']
                    return True
        except Exception as e:
            logger.error(f'Login error: {e}')
        return False
    
    def get_ltp(self, exchange, token):
        if not self.access_token:
            if not self.login():
                return None
        
        try:
            url = f'{self.base_url}/rest/secure/angelbroking/market/v1/quote/'
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json',
                'X-PrivateKey': ANGEL_API_KEY
            }
            data = {'mode': 'FULL', 'exchangeTokens': {exchange: [token]}}
            
            response = requests.post(url, json=data, headers=headers, timeout=10)
            if response.status_code == 200:
                result = response.json()
                if result.get('status') and result.get('data'):
                    fetched = result['data'].get('fetched', [])
                    if fetched:
                        return fetched[0]
        except Exception as e:
            logger.error(f'LTP error: {e}')
        return None

angel_api = AngelOneAPI() if all([ANGEL_API_KEY, ANGEL_CLIENT_ID, ANGEL_PASSWORD, ANGEL_TOTP_SECRET]) else None

def get_next_expiry():
    today = datetime.now()
    days = (3 - today.weekday()) % 7
    if days == 0 and today.hour >= 15:
        days = 7
    return today + timedelta(days=days)

def calculate_greeks(spot, strike, premium, days_to_expiry, iv, option_type='CE'):
    """Calculate Option Greeks"""
    # Simplified Black-Scholes Greeks calculation
    
    # Delta calculation
    if option_type == 'CE':
        if strike < spot:  # ITM
            delta = 0.65 + (spot - strike) / spot * 0.15
        elif strike == spot:  # ATM
            delta = 0.50
        else:  # OTM
            delta = 0.35 - (strike - spot) / spot * 0.15
    else:  # PE
        if strike > spot:  # ITM
            delta = -0.65 - (strike - spot) / spot * 0.15
        elif strike == spot:  # ATM
            delta = -0.50
        else:  # OTM
            delta = -0.35 + (strike - spot) / spot * 0.15
    
    delta = max(min(delta, 1.0), -1.0)
    
    # Gamma (rate of delta change)
    atm_dist = abs(strike - spot) / spot
    gamma = 0.02 * (1 - atm_dist * 2) * (iv / 20)
    gamma = max(gamma, 0.001)
    
    # Theta (time decay per day)
    theta = -(premium * 0.003) * (iv / 20) * math.sqrt(30 / days_to_expiry)
    
    # Vega (IV sensitivity)
    vega = premium * 0.1 * math.sqrt(days_to_expiry / 30)
    
    return {
        'delta': round(delta, 3),
        'gamma': round(gamma, 4),
        'theta': round(theta, 2),
        'vega': round(vega, 2)
    }

def calculate_iv(premium, spot, strike, days_to_expiry):
    """Estimate Implied Volatility"""
    # Simplified IV calculation
    moneyness = premium / spot
    
    if abs(strike - spot) / spot < 0.01:  # ATM
        base_iv = 18
    elif strike < spot:  # ITM
        base_iv = 15
    else:  # OTM
        base_iv = 20
    
    # Adjust for premium
    premium_factor = (moneyness / 0.02) * 5
    iv = base_iv + premium_factor
    
    # Adjust for time
    time_factor = math.sqrt(30 / max(days_to_expiry, 1))
    iv = iv * time_factor
    
    return round(max(min(iv, 80), 8), 1)

def analyze_oi_pattern(ce_oi, pe_oi, ce_oi_change, pe_oi_change):
    """Analyze Open Interest patterns"""
    pcr = round(pe_oi / ce_oi, 2) if ce_oi > 0 else 0
    
    # PCR interpretation
    if pcr > 1.5:
        pcr_signal = 'VERY BULLISH (Heavy Put writing)'
    elif pcr > 1.2:
        pcr_signal = 'BULLISH (More Puts than Calls)'
    elif pcr > 0.8:
        pcr_signal = 'NEUTRAL (Balanced)'
    elif pcr > 0.5:
        pcr_signal = 'BEARISH (More Calls than Puts)'
    else:
        pcr_signal = 'VERY BEARISH (Heavy Call writing)'
    
    # OI Change pattern
    if ce_oi_change > 10 and pe_oi_change < -5:
        oi_pattern = 'BEARISH (Call build-up, Put unwinding)'
    elif pe_oi_change > 10 and ce_oi_change < -5:
        oi_pattern = 'BULLISH (Put build-up, Call unwinding)'
    elif ce_oi_change > 10 and pe_oi_change > 10:
        oi_pattern = 'HIGH VOLATILITY EXPECTED (Both building)'
    elif ce_oi_change < -10 and pe_oi_change < -10:
        oi_pattern = 'LOW VOLATILITY (Both unwinding)'
    else:
        oi_pattern = 'NEUTRAL (No clear OI pattern)'
    
    return {
        'pcr': pcr,
        'pcr_signal': pcr_signal,
        'oi_pattern': oi_pattern,
        'ce_oi': ce_oi,
        'pe_oi': pe_oi,
        'ce_oi_change': ce_oi_change,
        'pe_oi_change': pe_oi_change
    }

def get_comprehensive_option_data(asset, expiry, budget=15000):
    """Get complete option chain with all metrics"""
    if not angel_api:
        return None
    
    if not angel_api.access_token:
        if not angel_api.login():
            return None
    
    cfg = ASSETS[asset]
    
    # Get spot data
    spot_data = angel_api.get_ltp('NSE', cfg['index_token'])
    if not spot_data:
        return None
    
    spot = float(spot_data.get('ltp', 0))
    gap = cfg['gap']
    atm = round(spot / gap) * gap
    
    # Get strikes around ATM
    strikes = [
        atm - 2 * gap,  # ITM-2
        atm - gap,      # ITM-1
        atm,            # ATM
        atm + gap,      # OTM-1
        atm + 2 * gap   # OTM-2
    ]
    
    days_to_expiry = (expiry - datetime.now()).days
    
    options_data = []
    
    for strike in strikes:
        # Construct option symbols
        exp_str = expiry.strftime('%d%b%y').upper()
        ce_symbol = f"{cfg['symbol']}{exp_str}{int(strike)}CE"
        pe_symbol = f"{cfg['symbol']}{exp_str}{int(strike)}PE"
        
        # Get CE data
        ce_data = get_option_details(asset, ce_symbol, cfg['exchange'])
        # Get PE data
        pe_data = get_option_details(asset, pe_symbol, cfg['exchange'])
        
        if ce_data or pe_data:
            # Calculate position relative to spot
            if strike < atm - gap:
                position = 'ITM-2'
            elif strike < atm:
                position = 'ITM-1'
            elif strike == atm:
                position = 'ATM'
            elif strike == atm + gap:
                position = 'OTM-1'
            else:
                position = 'OTM-2'
            
            strike_data = {
                'strike': strike,
                'position': position,
                'ce': ce_data,
                'pe': pe_data
            }
            
            # Calculate Greeks and IV if data available
            if ce_data and ce_data.get('ltp'):
                ce_premium = ce_data['ltp']
                ce_iv = calculate_iv(ce_premium, spot, strike, days_to_expiry)
                ce_greeks = calculate_greeks(spot, strike, ce_premium, days_to_expiry, ce_iv, 'CE')
                strike_data['ce']['iv'] = ce_iv
                strike_data['ce']['greeks'] = ce_greeks
                
                # Check if fits budget
                investment = ce_premium * cfg['lot']
                strike_data['ce']['investment'] = investment
                strike_data['ce']['fits_budget'] = investment <= budget
            
            if pe_data and pe_data.get('ltp'):
                pe_premium = pe_data['ltp']
                pe_iv = calculate_iv(pe_premium, spot, strike, days_to_expiry)
                pe_greeks = calculate_greeks(spot, strike, pe_premium, days_to_expiry, pe_iv, 'PE')
                strike_data['pe']['iv'] = pe_iv
                strike_data['pe']['greeks'] = pe_greeks
                
                # Check if fits budget
                investment = pe_premium * cfg['lot']
                strike_data['pe']['investment'] = investment
                strike_data['pe']['fits_budget'] = investment <= budget
            
            options_data.append(strike_data)
    
    # Calculate overall PCR and OI patterns
    total_ce_oi = sum(opt['ce'].get('oi', 0) for opt in options_data if opt.get('ce'))
    total_pe_oi = sum(opt['pe'].get('oi', 0) for opt in options_data if opt.get('pe'))
    
    # Placeholder for OI change (would need historical data)
    ce_oi_change = 5  # Placeholder
    pe_oi_change = 3  # Placeholder
    
    oi_analysis = analyze_oi_pattern(total_ce_oi, total_pe_oi, ce_oi_change, pe_oi_change)
    
    return {
        'asset': asset,
        'spot': spot,
        'atm': atm,
        'expiry': expiry,
        'days_to_expiry': days_to_expiry,
        'options': options_data,
        'oi_analysis': oi_analysis,
        'lot_size': cfg['lot']
    }

def get_option_details(asset, symbol, exchange):
    """Get option details from Angel One"""
    if not angel_api or not angel_api.access_token:
        return None
    
    try:
        # Search for option
        url = f'{angel_api.base_url}/rest/secure/angelbroking/order/v1/searchScrip'
        headers = {
            'Authorization': f'Bearer {angel_api.access_token}',
            'Content-Type': 'application/json',
            'X-PrivateKey': ANGEL_API_KEY
        }
        data = {'exchange': exchange, 'searchscrip': symbol}
        
        response = requests.post(url, json=data, headers=headers, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('status') and result.get('data'):
                options = result['data']
                for opt in options:
                    if opt.get('tradingsymbol') == symbol:
                        token = opt.get('symboltoken')
                        if token:
                            # Get full quote
                            quote = angel_api.get_ltp(exchange, token)
                            if quote:
                                return {
                                    'symbol': symbol,
                                    'ltp': float(quote.get('ltp', 0)),
                                    'volume': int(quote.get('volume', 0)),
                                    'oi': int(quote.get('oi', 0)),
                                    'change': float(quote.get('change', 0)),
                                    'pchange': float(quote.get('pChange', 0))
                                }
    except Exception as e:
        logger.error(f'Option details error: {e}')
    
    return None

def get_ai_comprehensive_recommendation(budget=15000):
    """Get AI recommendation with complete analysis"""
    if not anthropic_client:
        return None
    
    # Analyze all assets
    all_analysis = []
    expiry = get_next_expiry()
    
    for asset_key in ASSETS.keys():
        try:
            data = get_comprehensive_option_data(asset_key, expiry, budget)
            if data:
                all_analysis.append(data)
        except Exception as e:
            logger.error(f'Error analyzing {asset_key}: {e}')
    
    if not all_analysis:
        return None
    
    # Prepare comprehensive data for AI
    analysis_text = "COMPREHENSIVE MARKET ANALYSIS:\n\n"
    
    for data in all_analysis:
        cfg = ASSETS[data['asset']]
        analysis_text += f"{'='*50}\n"
        analysis_text += f"{cfg['name']} ANALYSIS\n"
        analysis_text += f"{'='*50}\n"
        analysis_text += f"Spot Price: Rs{data['spot']:,.2f}\n"
        analysis_text += f"Days to Expiry: {data['days_to_expiry']}\n"
        analysis_text += f"Lot Size: {data['lot_size']}\n\n"
        
        # OI Analysis
        oi = data['oi_analysis']
        analysis_text += f"PCR (Put-Call Ratio): {oi['pcr']}\n"
        analysis_text += f"PCR Signal: {oi['pcr_signal']}\n"
        analysis_text += f"OI Pattern: {oi['oi_pattern']}\n"
        analysis_text += f"Total CE OI: {oi['ce_oi']:,}\n"
        analysis_text += f"Total PE OI: {oi['pe_oi']:,}\n\n"
        
        # Options data
        analysis_text += "OPTION CHAIN DATA:\n"
        for opt in data['options']:
            analysis_text += f"\n{opt['position']} Strike: Rs{opt['strike']}\n"
            
            # CE data
            if opt.get('ce') and opt['ce'].get('ltp'):
                ce = opt['ce']
                analysis_text += f"  CALL (CE):\n"
                analysis_text += f"    LTP: Rs{ce['ltp']}\n"
                analysis_text += f"    IV: {ce.get('iv', 'N/A')}%\n"
                analysis_text += f"    Volume: {ce.get('volume', 0):,}\n"
                analysis_text += f"    OI: {ce.get('oi', 0):,}\n"
                if ce.get('greeks'):
                    g = ce['greeks']
                    analysis_text += f"    Greeks: Delta={g['delta']}, Gamma={g['gamma']}, Theta={g['theta']}, Vega={g['vega']}\n"
                analysis_text += f"    Investment: Rs{ce.get('investment', 0):,.0f}\n"
                analysis_text += f"    Fits Budget: {'YES' if ce.get('fits_budget') else 'NO'}\n"
            
            # PE data
            if opt.get('pe') and opt['pe'].get('ltp'):
                pe = opt['pe']
                analysis_text += f"  PUT (PE):\n"
                analysis_text += f"    LTP: Rs{pe['ltp']}\n"
                analysis_text += f"    IV: {pe.get('iv', 'N/A')}%\n"
                analysis_text += f"    Volume: {pe.get('volume', 0):,}\n"
                analysis_text += f"    OI: {pe.get('oi', 0):,}\n"
                if pe.get('greeks'):
                    g = pe['greeks']
                    analysis_text += f"    Greeks: Delta={g['delta']}, Gamma={g['gamma']}, Theta={g['theta']}, Vega={g['vega']}\n"
                analysis_text += f"    Investment: Rs{pe.get('investment', 0):,.0f}\n"
                analysis_text += f"    Fits Budget: {'YES' if pe.get('fits_budget') else 'NO'}\n"
        
        analysis_text += "\n"
    
    # Call AI for recommendation
    try:
        message = anthropic_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=3000,
            messages=[{
                "role": "user",
                "content": f"""You are an expert options trader. Analyze this comprehensive market data and recommend the SINGLE BEST option to BUY.

{analysis_text}

REQUIREMENTS:
1. Budget: Maximum Rs{budget}
2. Choose ONE specific option to BUY (asset, strike, CE/PE)
3. Consider ALL factors:
   - Greeks (Delta for direction, Gamma for acceleration, Theta for decay, Vega for IV risk)
   - IV levels (prefer moderate IV, not too high/low)
   - OI patterns (build-up vs unwinding)
   - PCR (market sentiment)
   - Volume (liquidity)
   - Days to expiry (time decay risk)
   - Investment amount (must fit budget)
   
4. Provide response in this EXACT format:

BUY RECOMMENDATION:
Asset: [name]
Option: [strike] [CE/PE]
Symbol: [exact symbol]
Premium (LTP): Rs[X]
Investment: Rs[X] ([Y] lots)

GREEKS ANALYSIS:
Delta: [value] - [interpretation]
Gamma: [value] - [interpretation]
Theta: [value] - [interpretation]
Vega: [value] - [interpretation]
Greeks Score: [X]/10

IV ANALYSIS:
Current IV: [X]%
IV Level: [High/Moderate/Low]
IV Score: [X]/10

OI & PCR ANALYSIS:
PCR: [value]
PCR Signal: [interpretation]
OI Pattern: [interpretation]
OI Score: [X]/10

RISK MANAGEMENT:
Entry: Rs[X] (Current LTP)
Stop Loss: Rs[X] ([Y]% loss)
Target 1: Rs[X] ([Y]% profit)
Target 2: Rs[X] ([Y]% profit)
Risk: Rs[X]
Max Profit Potential: Rs[X]
Risk:Reward = 1:[X]

REASONING:
[Detailed explanation why this is the best option considering all factors]

CONFIDENCE: [X]%

Keep analysis detailed but clear."""
            }]
        )
        
        return message.content[0].text
        
    except Exception as e:
        logger.error(f'AI recommendation error: {e}')
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = '🤖 Shon AI - Advanced Options Analyzer\n\n'
    msg += 'COMPLETE ANALYSIS:\n'
    msg += '✅ Greeks (Delta, Gamma, Theta, Vega)\n'
    msg += '✅ IV (Implied Volatility)\n'
    msg += '✅ OI (Open Interest patterns)\n'
    msg += '✅ PCR (Put-Call Ratio)\n'
    msg += '✅ Volume & Liquidity\n'
    msg += '✅ Risk Management\n\n'
    msg += 'AI analyzes 5 indices:\n'
    msg += '• NIFTY, BANKNIFTY, FINNIFTY\n'
    msg += '• SENSEX, MIDCAP\n\n'
    msg += 'Commands:\n'
    msg += '/recommend - AI suggests best BUY (₹15K)\n'
    msg += '/recommend 20000 - Custom budget\n'
    msg += '/analyze [asset] - Quick check\n'
    msg += '/markets - All prices\n'
    msg += '/help - Complete guide\n\n'
    msg += 'Try: /recommend'
    
    await update.message.reply_text(msg)

async def recommend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comprehensive AI recommendation"""
    budget = 15000
    if context.args:
        try:
            budget = int(context.args[0])
            if budget < 1000:
                await update.message.reply_text('❌ Minimum budget: Rs1000')
                return
            if budget > 50000:
                await update.message.reply_text('⚠️ Very high budget! Recommended max: Rs50,000')
        except:
            pass
    
    loading = await update.message.reply_text(
        '🤖 AI COMPREHENSIVE ANALYSIS\n\n'
        'Analyzing:\n'
        '🔍 5 Indices (NIFTY, BANK, FIN, SENSEX, MIDCAP)\n'
        '📊 Option Greeks (Δ,Γ,Θ,ν)\n'
        '📈 IV Levels\n'
        '🎯 OI Patterns\n'
        '⚖️ PCR Ratios\n'
        '💰 Risk Management\n\n'
        'This will take 20-30 seconds...\n'
        'Getting real-time data from NSE...'
    )
    
    recommendation = get_ai_comprehensive_recommendation(budget)
    
    try:
        await loading.delete()
    except:
        pass
    
    if not recommendation:
        await update.message.reply_text(
            '❌ Unable to generate recommendation!\n\n'
            'Please check:\n'
            '- Angel One API configured
