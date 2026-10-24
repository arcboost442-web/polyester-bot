import asyncio
import json
import time
from pathlib import Path
from polyester import AsyncPolyester

ACCOUNTS_FILE = "accounts.json"
API_URL       = "https://api.testnet.polyester.com"
WS_URL        = "wss://api.testnet.polyester.com"
TEST_SYMBOL   = "SOL-USDC"


async def investigate(account: dict):
    print(f"\n{'='*60}")
    print(f"  INVESTIGASI BUG — Akun: {account.get('name')}")
    print(f"{'='*60}\n")

    async with AsyncPolyester(
        api_key_id        =account["api_key_id"],
        api_private_key   =account["api_private_key"],
        default_account_id=account["account_id"],
        api_url           =API_URL,
        ws_url            =WS_URL,
    ) as client:
        await client.wait_for_catalogs()

        # ============================================================
        # INVESTIGASI BUG #1 — Status "accepted" pada market IOC order
        # ============================================================
        print("🔍 BUG #1 — Investigasi status 'accepted' pada market IOC order")
        print("-" * 60)

        coid = f"inv-{int(time.time()*1000)}"
        try:
            result = await client.orders.create(
                symbol          =TEST_SYMBOL,
                side            ="buy",
                order_type      ="market",
                tif             ="ioc",
                qty             ="0.5",
                client_order_id =coid,
            )
            print(f"  Status langsung  : {result.status}")
            print(f"  Order ID         : {result.order_id if hasattr(result, 'order_id') else 'N/A'}")
            print(f"  Client Order ID  : {result.client_order_id if hasattr(result, 'client_order_id') else 'N/A'}")
            print(f"  Full result keys : {[k for k in dir(result) if not k.startswith('_')]}")

            # Tunggu 2 detik lalu cek status akhir via get
            await asyncio.sleep(2)
            print(f"\n  ⏳ Menunggu 2 detik, lalu cek status via get...")
            try:
                order_detail = await client.orders.get(client_order_id=coid)
                print(f"  Status setelah 2s: {order_detail.status}")
                print(f"  Filled qty       : {getattr(order_detail, 'filled_qty', 'N/A')}")
                print(f"  Orig qty         : {getattr(order_detail, 'orig_qty', 'N/A')}")
            except Exception as e:
                print(f"  ❌ get() error: {e}")
                # Coba via list_open
                try:
                    open_orders = await client.orders.list_open()
                    matching = [o for o in open_orders.orders 
                                if getattr(o, 'client_order_id', '') == coid]
                    if matching:
                        print(f"  Status di list_open: {matching[0].status}")
                    else:
                        print(f"  Order tidak ada di list_open (kemungkinan sudah settled/cancelled)")
                except Exception as e2:
                    print(f"  ❌ list_open() error: {e2}")

        except Exception as e:
            print(f"  ❌ Order gagal: {e}")

        print()

        # ============================================================
        # INVESTIGASI BUG #2 — batch_create keyword argument
        # ============================================================
        print("🔍 BUG #2 — Investigasi batch_create() signature")
        print("-" * 60)

        # Cek signature yang benar
        import inspect
        try:
            sig = inspect.signature(client.orders.batch_create)
            print(f"  Signature batch_create: {sig}")
        except Exception as e:
            print(f"  Tidak bisa inspect: {e}")

        # Coba berbagai cara panggil batch_create
        sample_orders = [
            dict(symbol=TEST_SYMBOL, side="buy",  order_type="market",
                 tif="ioc", qty="0.3",
                 client_order_id=f"inv-batch-{int(time.time()*1000)}-{i}")
            for i in range(3)
        ]

        # Cara 1: positional
        print("\n  Coba cara 1: batch_create(sample_orders)")
        try:
            r = await client.orders.batch_create(sample_orders)
            print(f"  ✅ Berhasil! Keys: {[k for k in dir(r) if not k.startswith('_')]}")
        except Exception as e:
            print(f"  ❌ {e}")

        # Cara 2: keyword 'requests'
        print("\n  Coba cara 2: batch_create(requests=sample_orders)")
        try:
            r = await client.orders.batch_create(requests=sample_orders)
            print(f"  ✅ Berhasil!")
        except Exception as e:
            print(f"  ❌ {e}")

        # Cara 3: keyword 'create_orders'
        print("\n  Coba cara 3: batch_create(create_orders=sample_orders)")
        try:
            r = await client.orders.batch_create(create_orders=sample_orders)
            print(f"  ✅ Berhasil!")
        except Exception as e:
            print(f"  ❌ {e}")

        # Cara 4: list objek dict langsung
        print("\n  Coba cara 4: batch_create(*sample_orders)")
        try:
            r = await client.orders.batch_create(*sample_orders)
            print(f"  ✅ Berhasil!")
        except Exception as e:
            print(f"  ❌ {e}")

        print()

        # ============================================================
        # INVESTIGASI BUG #3/#4 — CandlesResult & MarketTradesResult
        # ============================================================
        print("🔍 BUG #3/#4 — Investigasi struktur CandlesResult & MarketTradesResult")
        print("-" * 60)

        print("\n  Candles:")
        try:
            candles = await client.market_data.get_candles(
                symbol=TEST_SYMBOL, timeframe="1m", limit=5
            )
            print(f"  Type   : {type(candles)}")
            print(f"  Attrs  : {[k for k in dir(candles) if not k.startswith('_')]}")
            # Coba akses berbagai cara
            for attr in ["candles", "data", "items", "results", "rows"]:
                val = getattr(candles, attr, None)
                if val is not None:
                    print(f"  .{attr} → {type(val)} len={len(val) if hasattr(val, '__len__') else '?'}")
        except Exception as e:
            print(f"  ❌ {e}")

        print("\n  Trades:")
        try:
            trades = await client.market_data.get_trades(
                symbol=TEST_SYMBOL, limit=5
            )
            print(f"  Type   : {type(trades)}")
            print(f"  Attrs  : {[k for k in dir(trades) if not k.startswith('_')]}")
            for attr in ["trades", "data", "items", "results", "rows"]:
                val = getattr(trades, attr, None)
                if val is not None:
                    print(f"  .{attr} → {type(val)} len={len(val) if hasattr(val, '__len__') else '?'}")
        except Exception as e:
            print(f"  ❌ {e}")

        print(f"\n{'='*60}")
        print("  Investigasi selesai. Cek hasil di atas untuk laporan bug.")
        print(f"{'='*60}")


async def main():
    accounts = json.load(open(ACCOUNTS_FILE))
    await investigate(accounts[0])

if __name__ == "__main__":
    asyncio.run(main())
