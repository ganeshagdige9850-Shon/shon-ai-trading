"""
DHAN API CONNECTION TEST
हे script Dhan API connection verify करतं
"""

import os
import requests
import json

print("="*70)
print("DHAN API CONNECTION TEST")
print("="*70)
print()

# Variables check
CLIENT_ID = os.environ.get('DHAN_CLIENT_ID')
ACCESS_TOKEN = os.environ.get('DHAN_ACCESS_TOKEN')

print("STEP 1: Variables Check")
print("-"*70)

if not CLIENT_ID:
    print("❌ DHAN_CLIENT_ID missing!")
    print("   Railway मध्ये हा variable add करा")
    exit(1)
else:
    print(f"✅ DHAN_CLIENT_ID: {CLIENT_ID}")

if not ACCESS_TOKEN:
    print("❌ DHAN_ACCESS_TOKEN missing!")
    print("   Railway मध्ये हा variable add करा")
    exit(1)
else:
    # Show first/last 20 chars only (security)
    token_preview = ACCESS_TOKEN[:20] + "..." + ACCESS_TOKEN[-20:]
    print(f"✅ DHAN_ACCESS_TOKEN: {token_preview}")
    print(f"   Token length: {len(ACCESS_TOKEN)} characters")

print()
print("STEP 2: API Connection Test")
print("-"*70)

# Test API call
try:
    url = 'https://api.dhan.co/v2/quotes/ltp'
    
    headers = {
        'access-token': ACCESS_TOKEN,
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    
    payload = {
        'NSE_EQ': ['13']  # NIFTY 50
    }
    
    print("🔄 Calling Dhan API...")
    print(f"   URL: {url}")
    print(f"   Security ID: 13 (NIFTY 50)")
    print()
    
    response = requests.post(
        url,
        json=payload,
        headers=headers,
        timeout=15
    )
    
    print(f"📡 Response Status: {response.status_code}")
    print()
    
    if response.status_code == 200:
        print("✅ API CONNECTION SUCCESSFUL!")
        print()
        
        data = response.json()
        print("Response Data:")
        print(json.dumps(data, indent=2))
        print()
        
        if data.get('status') == 'success':
            ltp = data['data']['NSE_EQ']['13']['last_price']
            print("="*70)
            print(f"🎉 SUCCESS! NIFTY Price: Rs{ltp}")
            print("="*70)
            print()
            print("✅ Dhan API काम करतो आहे!")
            print("✅ Token valid आहे!")
            print("✅ Connection perfect आहे!")
            print()
            print("अजूनही bot मध्ये problem असेल तर:")
            print("1. Bot restart करा")
            print("2. Railway redeploy करा")
            print("3. Telegram /status तपासा")
        else:
            print("❌ API response not successful")
            print(f"   Status: {data.get('status')}")
            print(f"   Message: {data.get('message', 'Unknown')}")
    
    elif response.status_code == 401:
        print("❌ AUTHENTICATION FAILED!")
        print()
        print("Problem: Token invalid आहे!")
        print()
        print("Solution:")
        print("1. Dhan App उघडा")
        print("2. Settings → API Management")
        print("3. Token REFRESH करा")
        print("4. NEW token copy करा")
        print("5. Railway Variables मध्ये update करा")
        print("6. DHAN_ACCESS_TOKEN = new_token")
        print("7. Save करा")
        print()
    
    elif response.status_code == 403:
        print("❌ FORBIDDEN!")
        print()
        print("Problem: API access denied!")
        print()
        print("Check:")
        print("1. Dhan API enabled आहे का?")
        print("2. API permissions correct आहेत का?")
        print("3. Client ID correct आहे का?")
        print()
    
    else:
        print(f"❌ UNEXPECTED STATUS CODE: {response.status_code}")
        print()
        print("Response:")
        try:
            print(json.dumps(response.json(), indent=2))
        except:
            print(response.text)
        print()

except requests.exceptions.Timeout:
    print("❌ REQUEST TIMEOUT!")
    print()
    print("Problem: API response मिळत नाही!")
    print()
    print("Possible causes:")
    print("1. Internet connection problem")
    print("2. Railway network issue")
    print("3. Dhan API down")
    print()

except requests.exceptions.ConnectionError:
    print("❌ CONNECTION ERROR!")
    print()
    print("Problem: Dhan API पर्यंत पोहोचू शकत नाही!")
    print()
    print("Check:")
    print("1. Internet connection")
    print("2. Railway network settings")
    print("3. Dhan API status")
    print()

except Exception as e:
    print(f"❌ ERROR: {e}")
    print()
    print("Unexpected error occurred!")
    print()

print()
print("="*70)
print("TEST COMPLETE")
print("="*70)
print()
print("Next steps:")
print("1. Screenshot या output ची घ्या")
print("2. Error असेल तर solution follow करा")
print("3. Success झालं तर bot restart करा")
print()
  
