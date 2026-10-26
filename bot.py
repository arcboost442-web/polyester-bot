import os
import asyncio
import json
import random
import time
import uuid
from pathlib import Path

from polyester import AsyncPolyester
from polyester.types.money import Price

# ==================== PENGATURAN ====================
ACCOUNTS_FILE = os.environ.get("ACCOUNTS_FILE", "accounts.json")

SYMBOLS = ["LTC-USDT"]
GRIDS = 10
QTY_MIN = 0.5
QTY_MAX = 1.5
TICK_SIZE = 10_000_000       # actual tick = $0.10
INTERVAL_TICKS = 10_000_000  # jarak antar grid

STAGGER_DELAY = 5            # detik antar akun
LOOP_DELAY_MIN = 20
LOOP_DELAY_MAX = 40
RETRY_MAX = 3
RETRY_DELAY = 2
# ====================================================


def load_accounts():
    accounts_json = os.environ.get("ACCOUNTS_JSON")
    if accounts_json:
        return json.loads(accounts_json)
    path = Path(ACCOUNTS_FILE)
    if not path.exists():
        print(f"Tidak ada file {ACCOUNTS_FILE}!")
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


async def get_mid_ticks(client, symbol):
    ob = await client.orderbook.get(symbol=symbol)
    bid = int(ob.bids[0].price.ticks)
    ask = int(ob.asks[0].price.ticks)
    mid = (bid + ask) // 2
    return (mid // TICK_SIZE) * TICK_SIZE


async def cancel_all_with_retry(client, symbol, name):
    for attempt in range(RETRY_MAX):
        try:
            await client.orders.cancel_all(symbol=symbol)
            print(f"   [CANCEL] [{name}] {symbol} OK")
            return
        except Exception as e:
            err = str(e)
            if "Internal error" in err:
                pass  # normal, lanjut
            elif attempt < RETRY_MAX - 1:
                await asyncio.sleep(RETRY_DELAY)
            else:
                print(f"   [ERR] [{name}] Cancel {symbol}: {err[:60]}")


async def place_grid_with_retry(client, symbol, name, round_num):
    for attempt in range(RETRY_MAX):
        try:
            mid = await get_mid_ticks(client, symbol)
            print(f"   [GRID] [{name}] {symbol} mid={mid/1e8:.2f}")

            items = []
            ts = int(time.time() * 1000)

            for i in range(1, GRIDS + 1):
                qty = str(round(random.uniform(QTY_MIN, QTY_MAX), 2))

                buy_ticks = mid - INTERVAL_TICKS * i
                buy_ticks = (buy_ticks // TICK_SIZE) * TICK_SIZE

                sell_ticks = mid + INTERVAL_TICKS * i
                sell_ticks = (sell_ticks // TICK_SIZE) * TICK_SIZE

                items.append({
                    "symbol": symbol,
                    "side": "buy",
                    "order_type": "limit",
                    "tif": "gtc",
                    "qty": qty,
                    "price": Price(ticks=int(buy_ticks)),
                    "post_only": True,
                    "client_order_id": f"grid-{name}-{round_num}-buy-{i}-{ts}",
                })
                items.append({
                    "symbol": symbol,
                    "side": "sell",
                    "order_type": "limit",
                    "tif": "gtc",
                    "qty": qty,
                    "price": Price(ticks=int(sell_ticks)),
                    "post_only": True,
                    "client_order_id": f"grid-{name}-{round_num}-sell-{i}-{ts}",
                })

            result = await client.orders.batch_create(items=items)
            success = result.accepted_count
            print(f"   [BATCH] [{name}] {symbol} {result.accepted_count} acc {result.rejected_count} rej")
            return success

        except Exception as e:
            err = str(e)
            if "Service temporarily unavailable" in err or "Internal error" in err:
                if attempt < RETRY_MAX - 1:
                    print(f"   [RETRY] [{name}] attempt {attempt+1}/{RETRY_MAX}: {err[:60]}")
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    print(f"   [ERR] [{name}] {symbol} gagal setelah {RETRY_MAX}x: {err[:60]}")
            else:
                print(f"   [ERR] [{name}] {symbol}: {err[:80]}")
                return 0

    return 0


async def run_account_loop(account: dict, index: int):
    name = account.get("name", "unknown")
    start_delay = index * STAGGER_DELAY
    print(f"[WAIT] [{name}] mulai dalam {start_delay}s...")
    await asyncio.sleep(start_delay)

    round_num = 0
    total_success = 0

    while True:
        round_num += 1
        print(f"\n[START] [{name}] putaran #{round_num}")

        try:
            async with AsyncPolyester(
                api_key_id=account["api_key_id"],
                api_private_key=account["api_private_key"],
                default_account_id=account["account_id"],
                api_url='https://api.testnet.polyester.com',
                ws_url='wss://api.testnet.polyester.com',
            ) as client:
                await client.wait_for_catalogs()

                try:
                    await client.balances.list()
                except Exception as e:
                    print(f"   [ERR] [{name}] Balances error: {e}")
                    await asyncio.sleep(30)
                    continue

                # Cancel semua order lama
                for symbol in SYMBOLS:
                    await cancel_all_with_retry(client, symbol, name)

                await asyncio.sleep(1)

                # Pasang grid baru
                for symbol in SYMBOLS:
                    ok = await place_grid_with_retry(client, symbol, name, round_num)
                    total_success += ok

                print(f"   [TOTAL] [{name}] total sukses: {total_success}")

        except Exception as e:
            print(f"[ERR] [{name}] Error: {e}")

        delay = random.randint(LOOP_DELAY_MIN, LOOP_DELAY_MAX)
        print(f"[SLEEP] [{name}] istirahat {delay}s...")
        await asyncio.sleep(delay)


async def main():
    accounts = load_accounts()
    if not accounts:
        print("Tidak ada akun. Periksa accounts.json")
        return

    print(f"Total akun: {len(accounts)}")
    print(f"Mode: GRID TRADING | LTC-USDT only | batch_create\n")

    await asyncio.gather(*[
        run_account_loop(acc, i) for i, acc in enumerate(accounts)
    ])


if __name__ == "__main__":
    asyncio.run(main())