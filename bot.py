import os
import asyncio
import json
import random
import time
from pathlib import Path

from polyester import AsyncPolyester, Price

# ==================== PENGATURAN ====================
ACCOUNTS_FILE = os.environ.get("ACCOUNTS_FILE", "accounts.json")

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

MAKER_MODE = True
MAKER_CANCEL_AFTER = 30
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


async def place_maker_order(client, symbol, side, qty, round_num, name, i):
    try:
        ob = await client.orderbook.get(symbol=symbol)
        if side == "buy":
            price = ob.bids[0].price
        else:
            price = ob.asks[0].price

        client_order_id = f"maker-{name}-{round_num}-{int(time.time()*1000)}-{i}"
        result = await client.orders.create(
            symbol=symbol,
            side=side,
            order_type="limit",
            tif="gtc",
            qty=qty,
            price=price,
            post_only=True,
            client_order_id=client_order_id,
        )
        order_id = result.order_id
        price_val = price.ticks / 100_000_000
        print(f"   [MAKER] [{name}] LIMIT {side.upper():4} {qty} {symbol} @ {price_val:.2f} -> {result.status}")

        await asyncio.sleep(MAKER_CANCEL_AFTER)
        try:
            await client.orders.cancel(order_id=order_id, symbol=symbol)
            # Tidak filled -> fallback ke market order
            fallback_id = f"fallback-{name}-{round_num}-{int(time.time()*1000)}-{i}"
            result2 = await client.orders.create(
                symbol=symbol,
                side=side,
                order_type="market",
                tif="ioc",
                qty=qty,
                client_order_id=fallback_id,
            )
            print(f"   [FALLBACK] [{name}] MARKET {side.upper():4} {qty} {symbol} -> {result2.status}")
        except Exception:
            pass  # sudah filled oleh maker, tidak perlu fallback
        return True
    except Exception as e:
        print(f"   [ERR] [{name}] Gagal maker {side} {symbol}: {str(e)[:80]}")
        return False


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

        if MAKER_MODE:
            ok = await place_maker_order(client, symbol, side, qty, round_num, name, i)
            if ok:
                success += 1
            else:
                fail += 1
        else:
            try:
                result = await client.orders.create(
                    symbol=symbol,
                    side=side,
                    order_type="market",
                    tif="ioc",
                    qty=qty,
                    client_order_id=client_order_id,
                )
                print(f"   [OK] [{name}] {side.upper():4} {qty} {symbol} -> {result.status}")
                success += 1
            except Exception as e:
                print(f"   [ERR] [{name}] Gagal {side} {symbol}: {str(e)[:80]}")
                fail += 1

        await asyncio.sleep(random.uniform(ORDER_DELAY_MIN, ORDER_DELAY_MAX))

    print(f"   [STAT] [{name}] sukses={success} gagal={fail}")
    return success


async def run_account_loop(account: dict):
    name = account.get("name", "unknown")
    proxy_str = account.get("proxy", "")
    start_delay = random.randint(DELAY_MIN * 2, DELAY_MAX * 4)
    print(f"[WAIT] [{name}] mulai dalam {start_delay}s...")
    await asyncio.sleep(start_delay)

    total_success = 0
    round_num = 0

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

                ok = await trade_one_account(client, account, round_num)
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
    mode = "MAKER (limit post_only)" if MAKER_MODE else "MARKET (taker)"
    print(f"Mode: {mode} | Multi-pair | Qty random\n")

    await asyncio.gather(*[run_account_loop(acc) for acc in accounts])


if __name__ == "__main__":
    asyncio.run(main())
