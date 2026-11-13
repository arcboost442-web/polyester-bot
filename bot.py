import os
import asyncio
import json
import random
import time
from pathlib import Path
from decimal import Decimal
from polyester import AsyncPolyester
from polyester.types.money import Price

# ==================== PENGATURAN ====================
ACCOUNTS_FILE = os.environ.get("ACCOUNTS_FILE", "accounts.json")

# Minimum saldo untuk trade (dalam unit asset)
MIN_BALANCE = {
    "USDT": 10.0,
    "USDC": 10.0,
    "BTC": 0.0001,
    "ETH": 0.001,
    "LTC": 0.1,
    "XRP": 5.0,
    "TRX": 10.0,
    "POL": 5.0,
    "HYPE": 0.5,
    "BNB": 0.01,
    "SOL": 0.1,
    "DOGE": 20.0,
    "AVAX": 0.1,
    "BCH": 0.01,
    "ETC": 0.1,
    "ARB": 1.0,
    "ZEC": 0.01,
    "XAUT": 0.001,
}

# Config per pair: tick_size actual, interval, qty
PAIR_CONFIG = {
    "LTC-USDT":  {"tick_size": 10_000_000,   "interval": 10_000_000,   "qty_min": 1.0,     "qty_max": 3.0},
    "BTC-USDT":  {"tick_size": 10_000_000,   "interval": 1_000_000_000,"qty_min": 0.0001,  "qty_max": 0.0005},
    "ETH-USDT":  {"tick_size": 20_000_000,   "interval": 20_000_000,   "qty_min": 0.002,   "qty_max": 0.008},
    "SOL-USDT":  {"tick_size": 30_000_000,   "interval": 30_000_000,   "qty_min": 0.1,     "qty_max": 0.5},
    "SOL-USDC":  {"tick_size": 10_000_000,   "interval": 10_000_000,   "qty_min": 0.1,     "qty_max": 0.5},
    "XRP-USDT":  {"tick_size": 100_000,      "interval": 1_000_000,    "qty_min": 10.0,    "qty_max": 40.0},
    "TRX-USDT":  {"tick_size": 30_000,       "interval": 300_000,      "qty_min": 50.0,    "qty_max": 200.0},
    "POL-USDT":  {"tick_size": 10_000,       "interval": 100_000,      "qty_min": 10.0,    "qty_max": 40.0},
    "HYPE-USDT": {"tick_size": 1_000_000,    "interval": 10_000_000,   "qty_min": 0.1,     "qty_max": 0.5},
    "BNB-USDT":  {"tick_size": 10_000_000,   "interval": 100_000_000,  "qty_min": 0.005,   "qty_max": 0.02},
    "DOGE-USDT": {"tick_size": 30_000,       "interval": 300_000,      "qty_min": 50.0,    "qty_max": 200.0},
    "AVAX-USDT": {"tick_size": 1_000_000,    "interval": 10_000_000,   "qty_min": 0.1,     "qty_max": 0.5},
    "BCH-USDT":  {"tick_size": 100_000_000,  "interval": 1_000_000_000,"qty_min": 0.01,    "qty_max": 0.05},
    "ETC-USDT":  {"tick_size": 2_000_000,    "interval": 20_000_000,   "qty_min": 0.2,     "qty_max": 1.0},
    "ARB-USDT":  {"tick_size": 100_000,      "interval": 1_000_000,    "qty_min": 5.0,     "qty_max": 20.0},
    "ZEC-USDT":  {"tick_size": 20_000_000,   "interval": 200_000_000,  "qty_min": 0.01,    "qty_max": 0.05},
    "XAUT-USDT": {"tick_size": 10_000_000,   "interval": 100_000_000,  "qty_min": 0.001,   "qty_max": 0.005},
    "ETH-USDC":  {"tick_size": 10_000_000,   "interval": 100_000_000,  "qty_min": 0.002,   "qty_max": 0.008},
}

# Map asset_id ke asset code
ASSET_ID_MAP = {
    1: "USDT", 2: "USDC", 3: "BTC", 4: "SOL", 5: "BNB",
    6: "ETH", 17: "XRP", 18: "LTC", 19: "DOGE", 22: "HYPE",
    23: "ARB", 24: "POL", 25: "TRX", 26: "ETC", 40: "XAUT",
    43: "ZEC", 15: "AVAX", 20: "BCH",
}

GRIDS = 5
STAGGER_DELAY = 15
LOOP_DELAY_MIN = 40
LOOP_DELAY_MAX = 60
RETRY_MAX = 3
RETRY_DELAY = 2

# TWAP CONFIG
TWAP_SYMBOL = "LTC-USDT"
TWAP_DURATION = 120_000
TWAP_INTERVAL = 30_000
TWAP_SIMULTANEOUS = 5
TWAP_QTY_EACH = "0.5"
WAIT_AFTER_TWAP_MIN = 20
WAIT_AFTER_TWAP_MAX = 40
TWAP_STAGGER = 20
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


async def get_active_symbols(client) -> list:
    """Deteksi pair yang bisa ditrading berdasarkan saldo."""
    try:
        balances = await client.balances.list()
        available = {}
        for b in balances.balances:
            asset = ASSET_ID_MAP.get(b.asset_id)
            if asset:
                bal = int(b.available) / 1e18
                if bal > 0:
                    available[asset] = bal

        active = []
        for symbol, cfg in PAIR_CONFIG.items():
            base, quote = symbol.split("-")
            min_base = MIN_BALANCE.get(base, 0)
            min_quote = MIN_BALANCE.get(quote, 0)

            has_base = available.get(base, 0) >= min_base
            has_quote = available.get(quote, 0) >= min_quote

            if has_base or has_quote:
                active.append(symbol)

        return active
    except Exception as e:
        print(f"   [ERR] get_active_symbols: {e}")
        return ["LTC-USDT"]  # fallback


# ==================== GRID FUNCTIONS ====================

async def get_mid_ticks(client, symbol):
    tick_size = PAIR_CONFIG[symbol]["tick_size"]
    ob = await client.orderbook.get(symbol=symbol)
    bid = int(ob.bids[0].price.ticks)
    ask = int(ob.asks[0].price.ticks)
    mid = (bid + ask) // 2
    return (mid // tick_size) * tick_size


async def cancel_all_with_retry(client, symbol, name):
    for attempt in range(RETRY_MAX):
        try:
            await client.orders.cancel_all(symbol=symbol)
            print(f"   [CANCEL] [{name}] {symbol} OK")
            return
        except Exception as e:
            err = str(e)
            if "Internal error" in err:
                pass
            elif attempt < RETRY_MAX - 1:
                await asyncio.sleep(RETRY_DELAY)
            else:
                print(f"   [ERR] [{name}] Cancel {symbol}: {err[:60]}")


async def place_grid_with_retry(client, symbol, name, round_num):
    for attempt in range(RETRY_MAX):
        try:
            cfg = PAIR_CONFIG[symbol]
            tick_size = cfg["tick_size"]
            interval_ticks = cfg["interval"]
            qty_min = cfg["qty_min"]
            qty_max = cfg["qty_max"]

            mid = await get_mid_ticks(client, symbol)
            acc_offset = (int(name) - 1) * tick_size
            mid = mid + acc_offset
            print(f"   [GRID] [{name}] {symbol} mid={mid/1e8:.4f}")

            items = []
            ts = int(time.time() * 1000)

            for i in range(1, GRIDS + 1):
                qty = str(round(random.uniform(qty_min, qty_max), 6))

                buy_ticks = mid - interval_ticks * i
                buy_ticks = (buy_ticks // tick_size) * tick_size

                sell_ticks = mid + interval_ticks * i
                sell_ticks = (sell_ticks // tick_size) * tick_size

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
            print(f"   [BATCH] [{name}] {symbol} {result.accepted_count} acc {result.rejected_count} rej")
            return result.accepted_count

        except Exception as e:
            err = str(e)
            if "Service temporarily unavailable" in err or "Internal error" in err:
                if attempt < RETRY_MAX - 1:
                    print(f"   [RETRY] [{name}] attempt {attempt+1}/{RETRY_MAX}: {err[:60]}")
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    print(f"   [ERR] [{name}] {symbol} gagal: {err[:60]}")
            else:
                print(f"   [ERR] [{name}] {symbol}: {err[:80]}")
                return 0

    return 0


async def run_grid_loop(account: dict, index: int):
    name = account.get("name", "unknown")
    start_delay = index * STAGGER_DELAY
    print(f"[GRID WAIT] [{name}] mulai dalam {start_delay}s...")
    await asyncio.sleep(start_delay)

    round_num = 0
    total_success = 0

    while True:
        round_num += 1
        print(f"\n[GRID START] [{name}] putaran #{round_num}")

        try:
            async with AsyncPolyester(
                api_key_id=account["api_key_id"],
                api_private_key=account["api_private_key"],
                default_account_id=account["account_id"],
                api_url='https://api.testnet.polyester.com',
                ws_url='wss://api.testnet.polyester.com',
            ) as client:
                await client.wait_for_catalogs()

                # Auto-detect pair berdasarkan saldo
                symbols = await get_active_symbols(client)
                print(f"   [PAIRS] [{name}] aktif: {symbols}")

                for symbol in symbols:
                    await cancel_all_with_retry(client, symbol, name)

                await asyncio.sleep(1)

                for symbol in symbols:
                    ok = await place_grid_with_retry(client, symbol, name, round_num)
                    total_success += ok

                print(f"   [GRID TOTAL] [{name}] total sukses: {total_success}")

        except Exception as e:
            print(f"[GRID ERR] [{name}] Error: {e}")

        delay = random.randint(LOOP_DELAY_MIN, LOOP_DELAY_MAX)
        print(f"[GRID SLEEP] [{name}] istirahat {delay}s...")
        await asyncio.sleep(delay)


# ==================== TWAP FUNCTIONS ====================

async def cancel_all_triggers(client, name: str):
    try:
        triggers = await client.triggers.list(status=['running', 'armed'])
        tlist = getattr(triggers, 'triggers', [])
        for t in tlist:
            tid = getattr(t, 'trigger_id', None)
            if tid:
                try:
                    await client.triggers.cancel(trigger_id=tid)
                    print(f"   [TWAP CANCEL] [{name}] trigger {tid}")
                except Exception as e:
                    print(f"   [ERR] [{name}] cancel trigger: {e}")
    except Exception as e:
        print(f"   [ERR] [{name}] list triggers: {e}")


async def run_twap_batch(client, name: str, cycle: int, side: str, count: int):
    trigger_ids = []
    ts = int(time.time() * 1000)
    print(f"   [TWAP {side.upper()}] [{name}] cycle #{cycle} — {count}x {side} {TWAP_QTY_EACH} {TWAP_SYMBOL}")

    for i in range(count):
        try:
            result = await client.triggers.create(
                symbol=TWAP_SYMBOL,
                side=side,
                trigger_type="twap",
                qty=TWAP_QTY_EACH,
                twap_duration_ms=TWAP_DURATION,
                twap_slice_interval_ms=TWAP_INTERVAL,
                client_trigger_id=f"twap-{side}-{name}-{cycle}-{i}-{ts}",
            )
            tid = getattr(result, 'trigger_id', None)
            status = getattr(result, 'status', 'unknown')
            if tid:
                trigger_ids.append(tid)
                print(f"   [TWAP] [{name}] #{i+1}/{count} {side} trigger={tid} {status}")
        except Exception as e:
            err = str(e)[:60]
            print(f"   [ERR] [{name}] twap {side} #{i+1}: {err}")
            if "294" in err or "limit" in err.lower():
                print(f"   [LIMIT] [{name}] max trigger reached at {i+1}")
                break

    return trigger_ids


async def wait_all_triggers(client, name: str, trigger_ids: list):
    completed = 0
    pending = list(trigger_ids)
    timeout = (TWAP_DURATION // 1000) + 90
    start_time = time.time()

    while pending and (time.time() - start_time) < timeout:
        await asyncio.sleep(10)
        still_pending = []
        for tid in pending:
            try:
                t = await client.triggers.get(trigger_id=tid)
                status = getattr(t, 'status', 'unknown')
                if status in ('completed', 'cancelled', 'failed'):
                    if status == 'completed':
                        completed += 1
                else:
                    still_pending.append(tid)
            except Exception:
                still_pending.append(tid)
        pending = still_pending

    print(f"   [TWAP DONE] [{name}] {completed}/{len(trigger_ids)} completed")
    return completed


async def run_twap_loop(account: dict, index: int):
    name = account.get("name", "unknown")
    start_delay = index * TWAP_STAGGER + 10
    print(f"[TWAP WAIT] [{name}] mulai dalam {start_delay}s...")
    await asyncio.sleep(start_delay)

    cycle = 0

    while True:
        cycle += 1
        print(f"\n[TWAP START] [{name}] cycle #{cycle}")

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
                    balances = await client.balances.list()
                    total = sum(
                        int(b.trading) if isinstance(b.trading, str) else b.trading
                        for b in balances.balances
                    )
                    usd = total / 1e18
                    print(f"   [TWAP BAL] [{name}] ${usd:,.2f}")
                    if usd < 10:
                        print(f"   [TWAP SKIP] [{name}] balance terlalu kecil!")
                        await asyncio.sleep(60)
                        continue
                except Exception as e:
                    print(f"   [ERR] [{name}] balance: {e}")

                await cancel_all_triggers(client, name)

                buy_ids = await run_twap_batch(client, name, cycle, "buy", TWAP_SIMULTANEOUS)
                buy_ok = await wait_all_triggers(client, name, buy_ids)

                wait = random.randint(WAIT_AFTER_TWAP_MIN, WAIT_AFTER_TWAP_MAX)
                print(f"   [TWAP WAIT] [{name}] jeda {wait}s sebelum sell...")
                await asyncio.sleep(wait)

                sell_ids = await run_twap_batch(client, name, cycle, "sell", TWAP_SIMULTANEOUS)
                sell_ok = await wait_all_triggers(client, name, sell_ids)

                vol_est = (buy_ok + sell_ok) * float(TWAP_QTY_EACH) * 525
                print(f"   [TWAP STAT] [{name}] buy={buy_ok} sell={sell_ok} vol_est=${vol_est:,.0f}")

        except Exception as e:
            print(f"[TWAP ERR] [{name}] {e}")
            await asyncio.sleep(30)


# ==================== MAIN ====================

async def main():
    accounts = load_accounts()
    if not accounts:
        print("Tidak ada akun. Periksa accounts.json")
        return

    print(f"Total akun: {len(accounts)}")
    print(f"Mode: GRID AUTO-DETECT + TWAP | All pairs\n")

    tasks = []
    for i, acc in enumerate(accounts):
        tasks.append(run_grid_loop(acc, i))
        tasks.append(run_twap_loop(acc, i))

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())