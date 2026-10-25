import os
import asyncio
import json
import random
import time
import uuid
from pathlib import Path
from decimal import Decimal

from polyester import AsyncPolyester

# ==================== PENGATURAN ====================
ACCOUNTS_FILE = os.environ.get("ACCOUNTS_FILE", "accounts.json")

GRID_CONFIG = {
    "LTC-USDT": {
        "grids": 10,
        "interval": 0.1,    # tick size 0.01, interval 0.1
        "qty_min": 0.5,
        "qty_max": 1.5,
    },
    "SOL-USDC": {
        "grids": 10,
        "interval": 0.1,    # tick size 0.01, interval 0.1
        "qty_min": 0.1,
        "qty_max": 0.5,
    },
}

LOOP_DELAY_MIN = 30
LOOP_DELAY_MAX = 60
ORDER_DELAY = 0.5
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


async def get_mid_price(client, symbol):
    ob = await client.orderbook.get(symbol=symbol)
    best_bid = ob.bids[0].price.ticks / 100_000_000
    best_ask = ob.asks[0].price.ticks / 100_000_000
    return (best_bid + best_ask) / 2


async def cancel_all_orders(client, symbol, name):
    try:
        await client.orders.cancel_all(symbol=symbol)
        print(f"   [CANCEL] [{name}] {symbol} semua order di-cancel")
    except Exception as e:
        print(f"   [ERR] [{name}] Cancel all {symbol}: {str(e)[:60]}")


async def place_grid_orders(client, symbol, name, round_num):
    config = GRID_CONFIG[symbol]
    grids = config["grids"]
    interval = config["interval"]
    qty_min = config["qty_min"]
    qty_max = config["qty_max"]

    try:
        mid = await get_mid_price(client, symbol)
        print(f"   [GRID] [{name}] {symbol} mid={mid:.4f}")
    except Exception as e:
        print(f"   [ERR] [{name}] Gagal get mid price {symbol}: {e}")
        return 0

    success = 0
    mid_d = Decimal(str(mid))
    interval_d = Decimal(str(interval))
    tick = Decimal("0.01")

    for i in range(1, grids + 1):
        qty = str(round(random.uniform(qty_min, qty_max), 2))
        ts = int(time.time() * 1000)

        # Buy order di bawah mid
        raw_buy = mid_d - interval_d * i
        buy_price = str(round(raw_buy / tick) * tick)
        try:
            await client.orders.create(
                symbol=symbol,
                side="buy",
                order_type="limit",
                tif="gtc",
                qty=qty,
                price=buy_price,
                post_only=True,
                client_order_id=f"grid-{name}-{round_num}-buy-{i}-{ts}",
            )
            print(f"   [GRID] [{name}] BUY  {qty} {symbol} @ {buy_price}")
            success += 1
        except Exception as e:
            print(f"   [ERR] [{name}] BUY grid {i} {symbol}: {str(e)[:60]}")

        await asyncio.sleep(ORDER_DELAY)

        # Sell order di atas mid
        raw_sell = mid_d + interval_d * i
        sell_price = str(round(raw_sell / tick) * tick)
        try:
            await client.orders.create(
                symbol=symbol,
                side="sell",
                order_type="limit",
                tif="gtc",
                qty=qty,
                price=sell_price,
                post_only=True,
                client_order_id=f"grid-{name}-{round_num}-sell-{i}-{ts}",
            )
            print(f"   [GRID] [{name}] SELL {qty} {symbol} @ {sell_price}")
            success += 1
        except Exception as e:
            print(f"   [ERR] [{name}] SELL grid {i} {symbol}: {str(e)[:60]}")

        await asyncio.sleep(ORDER_DELAY)

    return success


async def run_account_loop(account: dict):
    name = account.get("name", "unknown")
    symbols = account.get("symbols", list(GRID_CONFIG.keys()))
    start_delay = random.randint(6, 30)
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
                default_sub_account_id=account["account_id"],
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
                for symbol in symbols:
                    await cancel_all_orders(client, symbol, name)

                await asyncio.sleep(1)

                # Pasang grid baru
                for symbol in symbols:
                    ok = await place_grid_orders(client, symbol, name, round_num)
                    total_success += ok
                    print(f"   [STAT] [{name}] {symbol} {ok} orders placed")

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
    print(f"Mode: GRID TRADING | LTC-USDT & SOL-USDC\n")

    await asyncio.gather(*[run_account_loop(acc) for acc in accounts])


if __name__ == "__main__":
    asyncio.run(main())
