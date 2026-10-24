import asyncio
import json
import random
import time
from pathlib import Path

from polyester import AsyncPolyester

# ==================== PENGATURAN ====================
ACCOUNTS_FILE = "accounts.json"

SYMBOLS = ["LTC-USDT", "SOL-USDC"]
ORDERS_PER_ACCOUNT = 20
QTY_MIN = 0.2
QTY_MAX = 0.5

DELAY_MIN = 3
DELAY_MAX = 8
ORDER_DELAY_MIN = 0.8
ORDER_DELAY_MAX = 1.8

LOOP_DELAY_MIN = 30
LOOP_DELAY_MAX = 90
# ====================================================


def load_accounts():
    path = Path(ACCOUNTS_FILE)
    if not path.exists():
        print(f"❌ File {ACCOUNTS_FILE} tidak ditemukan!")
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


async def trade_one_account(client, account: dict, round_num: int):
    name = account.get("name", "unknown")
    symbols = account.get("symbols", SYMBOLS)
    weights = account.get("weights", None)
    if weights and len(weights) != len(symbols):
        weights = None
    success = 0
    fail = 0

    for i in range(ORDERS_PER_ACCOUNT):
        symbol = random.choices(symbols, weights=weights, k=1)[0]
        side = random.choice(["buy", "sell"])
        qty = str(round(random.uniform(QTY_MIN, QTY_MAX), 2))
        client_order_id = f"bot-{name}-{round_num}-{int(time.time()*1000)}-{i}"

        try:
            result = await client.orders.create(
                symbol=symbol,
                side=side,
                order_type="market",
                tif="ioc",
                qty=qty,
                client_order_id=client_order_id,
            )
            print(f"   ✅ [{name}] {side.upper():4} {qty} {symbol} → {result.status}")
            success += 1
        except Exception as e:
            print(f"   ❌ [{name}] Gagal {side} {symbol}: {str(e)[:80]}")
            fail += 1

        await asyncio.sleep(random.uniform(ORDER_DELAY_MIN, ORDER_DELAY_MAX))

    print(f"   📊 [{name}] sukses={success} gagal={fail}")
    return success


async def run_account_loop(account: dict):
    name = account.get("name", "unknown")
    round_num = 0
    total_success = 0

    start_delay = random.randint(0, 30)
    print(f"⏳ [{name}] mulai dalam {start_delay}s...")
    await asyncio.sleep(start_delay)

    while True:
        round_num += 1
        print(f"\n🚀 [{name}] putaran #{round_num}")

        try:
            async with AsyncPolyester(
                api_key_id=account["api_key_id"],
                api_private_key=account["api_private_key"],
                default_sub_account_id=account["account_id"],
                api_url='https://api.testnet.polyester.com',
                ws_url='wss://api.testnet.polyester.com',
            ) as client:

                await client.wait_for_catalogs()

                try:
                    await client.balances.list()
                except Exception as e:
                    print(f"   ❌ [{name}] Balances error: {e}")
                    await asyncio.sleep(30)
                    continue

                ok = await trade_one_account(client, account, round_num)
                total_success += ok
                print(f"   🏆 [{name}] total sukses: {total_success}")

        except Exception as e:
            print(f"❌ [{name}] Error: {e}")

        delay = random.randint(LOOP_DELAY_MIN, LOOP_DELAY_MAX)
        print(f"⏳ [{name}] istirahat {delay}s...")
        await asyncio.sleep(delay)


async def main():
    accounts = load_accounts()
    if not accounts:
        print("Tidak ada akun. Periksa accounts.json")
        return

    print(f"📋 Total akun: {len(accounts)}")
    print(f"⚡ Mode: LOOP OTOMATIS | Multi-pair | Qty random | Proxy aktif\n")

    await asyncio.gather(*[run_account_loop(acc) for acc in accounts])


if __name__ == "__main__":
    asyncio.run(main())