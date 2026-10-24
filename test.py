import asyncio
import json
from pathlib import Path
from polyester import AsyncPolyester

async def test():
    with open("accounts.json", "r") as f:
        accounts = json.load(f)
    
    account = accounts[0]  # test akun pertama saja
    print(f"Testing akun: {account.get('name')}")
    print(f"api_key_id: {account['api_key_id'][:10]}...")
    print(f"account_id: {account['account_id']}")
    
    async with AsyncPolyester(
        api_key_id=account["api_key_id"],
        api_private_key=account["api_private_key"],
        default_account_id=account["account_id"],
        api_url="https://api-testnet.polyester.com/",
        ws_url="wss://api-testnet.polyester.com",
    ) as client:
        print("✅ Client berhasil dibuat")
        
        try:
            me = await client.auth.me()
            print(f"✅ auth.me(): {me}")
        except Exception as e:
            print(f"❌ auth.me() gagal: {e}")
        
        try:
            balances = await client.balances.list()
            print(f"✅ balances.list(): {balances}")
        except Exception as e:
            print(f"❌ balances.list() gagal: {e}")

asyncio.run(test())