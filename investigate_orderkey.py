import asyncio
import json
import inspect
import time
from polyester import AsyncPolyester

ACCOUNTS_FILE = "accounts.json"
API_URL       = "https://api.testnet.polyester.com"
WS_URL        = "wss://api.testnet.polyester.com"
TEST_SYMBOL   = "SOL-USDC"

async def investigate(account):
    async with AsyncPolyester(
        api_key_id        =account["api_key_id"],
        api_private_key   =account["api_private_key"],
        default_account_id=account["account_id"],
        api_url=API_URL, ws_url=WS_URL,
    ) as client:
        await client.wait_for_catalogs()
        print("✅ Connected\n")

        # ── 1. Cari tahu apa itu OrderKey ──────────────────────────
        print("=" * 60)
        print("1. INVESTIGASI OrderKey")
        print("=" * 60)
        try:
            from polyester.models.trading import OrderKey
            print(f"  ✅ OrderKey ditemukan di polyester.models.trading")
            print(f"  Type    : {OrderKey}")
            print(f"  Fields  : {[k for k in dir(OrderKey) if not k.startswith('_')]}")
            try:
                sig = inspect.signature(OrderKey)
                print(f"  Signature: {sig}")
            except Exception as e:
                print(f"  inspect error: {e}")
        except ImportError:
            print("  ❌ OrderKey tidak ada di models.trading")

        try:
            from polyester.models import OrderKey
            print(f"  ✅ OrderKey ada di polyester.models")
        except ImportError:
            print("  ❌ OrderKey tidak ada di polyester.models")

        try:
            import polyester
            print(f"\n  polyester top-level attrs: {[x for x in dir(polyester) if 'key' in x.lower() or 'order' in x.lower()]}")
        except Exception as e:
            print(f"  {e}")

        # ── 2. Buat order lalu coba get/cancel pakai berbagai cara ──
        print("\n" + "=" * 60)
        print("2. COBA get() DAN cancel() DENGAN OrderKey")
        print("=" * 60)

        # Buat limit order dulu (supaya tidak langsung filled, bisa di-cancel)
        # Cari harga tick yang valid dulu dari market data
        try:
            overview = await client.market_overview.list(limit=20)
            sol_market = next((m for m in overview.markets if m.symbol == TEST_SYMBOL), None)
            if sol_market and sol_market.last_price:
                last_price = sol_market.last_price.ticks / 1_000_000
                # Harga sangat jauh supaya tidak filled
                limit_price = round(last_price * 0.5, 2)
                print(f"  Last price SOL: ${last_price:.2f}, limit buy at: ${limit_price:.2f}")
            else:
                limit_price = 50.0
                print(f"  Pakai harga default: ${limit_price}")
        except Exception as e:
            limit_price = 50.0
            print(f"  Error get price: {e}, pakai default ${limit_price}")

        coid = f"keytest-{int(time.time()*1000)}"
        order_id = None
        try:
            r = await client.orders.create(
                symbol=TEST_SYMBOL, side="buy", order_type="limit",
                tif="gtc", qty="0.3",
                price=str(limit_price),
                client_order_id=coid,
            )
            order_id = r.order_id
            print(f"\n  Order dibuat: order_id={order_id} status={r.status}")
        except Exception as e:
            print(f"  ❌ Limit order gagal: {e}")
            # Coba market order saja
            try:
                r = await client.orders.create(
                    symbol=TEST_SYMBOL, side="buy", order_type="market",
                    tif="ioc", qty="0.3", client_order_id=coid,
                )
                order_id = r.order_id
                print(f"  Market order: order_id={order_id} status={r.status}")
            except Exception as e2:
                print(f"  ❌ Market order juga gagal: {e2}")

        if order_id:
            print(f"\n  Coba berbagai cara OrderKey...")

            # Cara A: string order_id langsung sebagai key
            print(f"\n  A) orders.get(key='{order_id}')")
            try:
                detail = await client.orders.get(key=order_id)
                print(f"  ✅ BERHASIL! status={detail.status}")
            except Exception as e:
                print(f"  ❌ {e}")

            # Cara B: dict
            print(f"\n  B) orders.get(key={{'order_id': '{order_id}'}})")
            try:
                detail = await client.orders.get(key={"order_id": order_id})
                print(f"  ✅ BERHASIL! status={detail.status}")
            except Exception as e:
                print(f"  ❌ {e}")

            # Cara C: dict dengan client_order_id
            print(f"\n  C) orders.get(key={{'client_order_id': '{coid}'}})")
            try:
                detail = await client.orders.get(key={"client_order_id": coid})
                print(f"  ✅ BERHASIL! status={detail.status}")
            except Exception as e:
                print(f"  ❌ {e}")

            # Cara D: coba OrderKey class langsung
            try:
                from polyester.models.trading import OrderKey
                ok = OrderKey(order_id=order_id)
                print(f"\n  D) orders.get(key=OrderKey(order_id=...))")
                detail = await client.orders.get(key=ok)
                print(f"  ✅ BERHASIL! status={detail.status}")
            except ImportError:
                pass
            except Exception as e:
                print(f"  ❌ {e}")

            # Cara E: cancel dengan key=order_id
            print(f"\n  E) orders.cancel(key='{order_id}')")
            try:
                cr = await client.orders.cancel(key=order_id)
                print(f"  ✅ CANCEL BERHASIL! status={cr.status if hasattr(cr,'status') else cr}")
            except Exception as e:
                print(f"  ❌ {e}")

        # ── 3. Cek list_open → untuk tahu field apa yang ada ────────
        print("\n" + "=" * 60)
        print("3. STRUKTUR ORDER DARI list_open()")
        print("=" * 60)
        try:
            open_orders = await client.orders.list_open()
            if open_orders.orders:
                o = open_orders.orders[0]
                print(f"  Fields tersedia: {[k for k in dir(o) if not k.startswith('_')]}")
                print(f"  order_id        : {getattr(o, 'order_id', 'N/A')}")
                print(f"  client_order_id : {getattr(o, 'client_order_id', 'N/A')}")
                print(f"  status          : {getattr(o, 'status', 'N/A')}")
                print(f"  symbol          : {getattr(o, 'symbol', 'N/A')}")
            else:
                print("  Tidak ada open orders")
        except Exception as e:
            print(f"  ❌ {e}")

        # ── 4. Cek user trades ────────────────────────────────────────
        print("\n" + "=" * 60)
        print("4. USER TRADES — apakah order kita masuk sebagai filled?")
        print("=" * 60)
        try:
            trades = await client.user_trades.list(symbol=TEST_SYMBOL, limit=5)
            print(f"  Type    : {type(trades)}")
            print(f"  Attrs   : {[k for k in dir(trades) if not k.startswith('_')]}")
            trade_list = getattr(trades, 'trades', getattr(trades, 'items', []))
            print(f"  Count   : {len(trade_list)}")
            if trade_list:
                t = trade_list[0]
                print(f"  Last trade fields: {[k for k in dir(t) if not k.startswith('_')]}")
                print(f"  order_id    : {getattr(t, 'order_id', 'N/A')}")
                print(f"  side        : {getattr(t, 'side', 'N/A')}")
                print(f"  qty         : {getattr(t, 'qty', 'N/A')}")
                print(f"  price       : {getattr(t, 'price', 'N/A')}")
                print(f"  settled     : {getattr(t, 'settled', 'N/A')}")
        except Exception as e:
            print(f"  ❌ user_trades error: {e}")

        print("\n" + "=" * 60)
        print("  SELESAI — Share hasil ini!")
        print("=" * 60)


async def main():
    accounts = json.load(open(ACCOUNTS_FILE))
    await investigate(accounts[0])

if __name__ == "__main__":
    asyncio.run(main())
