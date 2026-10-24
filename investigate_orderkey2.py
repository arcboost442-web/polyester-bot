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

        # ── 1. Import OrderId dan ClientOrderId ─────────────────────
        print("=" * 60)
        print("1. IMPORT OrderId dan ClientOrderId")
        print("=" * 60)

        OrderId_class       = None
        ClientOrderId_class = None

        # Coba berbagai lokasi import
        import_attempts = [
            "from polyester.models.order_key import OrderId, ClientOrderId",
            "from polyester.models.trading import OrderId, ClientOrderId",
            "from polyester.models import OrderId, ClientOrderId",
            "from polyester import OrderId, ClientOrderId",
        ]
        for attempt in import_attempts:
            try:
                exec(attempt)
                # Kalau berhasil, ambil class-nya
                ns = {}
                exec(attempt, ns)
                OrderId_class       = ns.get("OrderId")
                ClientOrderId_class = ns.get("ClientOrderId")
                print(f"  ✅ {attempt}")
                break
            except Exception as e:
                print(f"  ❌ {attempt}")
                print(f"     → {e}")

        # Inspect lebih dalam
        if OrderId_class:
            print(f"\n  OrderId class      : {OrderId_class}")
            print(f"  OrderId fields     : {[k for k in dir(OrderId_class) if not k.startswith('_')]}")
            try:
                print(f"  OrderId signature  : {inspect.signature(OrderId_class)}")
            except Exception as e:
                print(f"  OrderId inspect    : {e}")

        if ClientOrderId_class:
            print(f"\n  ClientOrderId class: {ClientOrderId_class}")
            try:
                print(f"  ClientOrderId sig  : {inspect.signature(ClientOrderId_class)}")
            except Exception as e:
                print(f"  ClientOrderId inspect: {e}")

        # ── 2. Coba konstruksi OrderKey ──────────────────────────────
        print("\n" + "=" * 60)
        print("2. KONSTRUKSI OrderKey DAN PAKAI DI get()/cancel()")
        print("=" * 60)

        # Buat market order dulu
        coid = f"ok2-{int(time.time()*1000)}"
        try:
            r = await client.orders.create(
                symbol=TEST_SYMBOL, side="buy", order_type="market",
                tif="ioc", qty="0.3", client_order_id=coid,
            )
            order_id = r.order_id
            print(f"  Order: order_id={order_id} coid={coid} status={r.status}")
        except Exception as e:
            print(f"  ❌ Order gagal: {e}")
            order_id = None

        await asyncio.sleep(1)

        if OrderId_class and order_id:
            print(f"\n  Coba OrderId('{order_id}')...")
            for args in [
                (order_id,),
                (),
            ]:
                for kwargs in [
                    {"order_id": order_id},
                    {"id": order_id},
                    {"value": order_id},
                ]:
                    try:
                        ok = OrderId_class(*args, **kwargs) if not args else OrderId_class(*args)
                        print(f"  ✅ OrderId({args}, {kwargs}) → {ok}")
                        # Coba pakai di get()
                        try:
                            detail = await client.orders.get(key=ok)
                            print(f"  ✅✅ orders.get(key=OrderId(...)) BERHASIL! status={detail.status}")
                        except Exception as e2:
                            print(f"  get() error: {e2}")
                        break
                    except Exception as e:
                        pass

        if ClientOrderId_class and coid:
            print(f"\n  Coba ClientOrderId('{coid}')...")
            for args in [(coid,), ()]:
                for kwargs in [
                    {"client_order_id": coid},
                    {"id": coid},
                    {"value": coid},
                ]:
                    try:
                        ok = ClientOrderId_class(*args) if args else ClientOrderId_class(**kwargs)
                        print(f"  ✅ ClientOrderId → {ok}")
                        try:
                            detail = await client.orders.get(key=ok)
                            print(f"  ✅✅ orders.get(key=ClientOrderId(...)) BERHASIL! status={detail.status}")
                        except Exception as e2:
                            print(f"  get() error: {e2}")
                        break
                    except Exception as e:
                        pass

        # ── 3. Cek module order_key secara lengkap ───────────────────
        print("\n" + "=" * 60)
        print("3. INSPECT polyester.models.order_key MODULE")
        print("=" * 60)
        try:
            import polyester.models.order_key as ok_module
            print(f"  Module contents: {dir(ok_module)}")
            for name in dir(ok_module):
                if not name.startswith("_"):
                    obj = getattr(ok_module, name)
                    print(f"\n  {name}: {obj}")
                    try:
                        print(f"    signature: {inspect.signature(obj)}")
                    except:
                        pass
                    try:
                        print(f"    fields: {[f for f in dir(obj) if not f.startswith('_')]}")
                    except:
                        pass
        except Exception as e:
            print(f"  ❌ {e}")

        # ── 4. Cek user trades via trades endpoint ───────────────────
        print("\n" + "=" * 60)
        print("4. CARI USER TRADES ENDPOINT")
        print("=" * 60)
        # Cek semua attribute client yang ada 'trade' di namanya
        trade_attrs = [a for a in dir(client) if 'trade' in a.lower()]
        print(f"  Trade-related attrs: {trade_attrs}")
        for attr in trade_attrs:
            obj = getattr(client, attr)
            methods = [m for m in dir(obj) if not m.startswith('_')]
            print(f"  client.{attr} methods: {methods}")

        # Coba akses
        for attr in trade_attrs:
            for method in ['list', 'get', 'list_trades', 'get_trades']:
                try:
                    fn = getattr(getattr(client, attr), method)
                    sig = inspect.signature(fn)
                    print(f"\n  client.{attr}.{method}{sig}")
                    # Coba call
                    result = await fn(limit=5)
                    print(f"  ✅ client.{attr}.{method}() → {type(result)}")
                    attrs_r = [k for k in dir(result) if not k.startswith('_')]
                    print(f"     attrs: {attrs_r}")
                    # Cari list di dalamnya
                    for a in attrs_r:
                        val = getattr(result, a, None)
                        if isinstance(val, list) and len(val) > 0:
                            print(f"     .{a}[0] fields: {[k for k in dir(val[0]) if not k.startswith('_')]}")
                            t = val[0]
                            for field in ['order_id','side','qty','price','symbol','settled','fee']:
                                print(f"       .{field} = {getattr(t, field, 'N/A')}")
                    break
                except AttributeError:
                    pass
                except Exception as e:
                    print(f"  client.{attr}.{method}() error: {e}")

        print("\n" + "=" * 60)
        print("  SELESAI")
        print("=" * 60)


async def main():
    accounts = json.load(open(ACCOUNTS_FILE))
    await investigate(accounts[0])

if __name__ == "__main__":
    asyncio.run(main())
