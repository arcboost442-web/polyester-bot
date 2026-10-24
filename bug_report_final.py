import asyncio
import json
import inspect
import time
from pathlib import Path
from polyester import AsyncPolyester

ACCOUNTS_FILE = "accounts.json"
API_URL       = "https://api.testnet.polyester.com"
WS_URL        = "wss://api.testnet.polyester.com"
TEST_SYMBOL   = "SOL-USDC"

report_lines = []

def section(title):
    line = f"\n{'='*65}\n  {title}\n{'='*65}"
    print(line)
    report_lines.append(line)

def log(msg):
    print(msg)
    report_lines.append(msg)


async def verify_bug1_orders_get(client):
    """
    BUG #1: orders.get() tidak menerima client_order_id sebagai keyword argument
    Padahal orders.cancel() juga punya masalah serupa (ditemukan di run pertama)
    """
    section("BUG #1 — orders.get() keyword argument salah")

    log(f"  SDK Method  : client.orders.get()")
    log(f"  Signature   : {inspect.signature(client.orders.get)}")

    coid = f"bug1-{int(time.time()*1000)}"
    log(f"\n  Step 1: Buat order dengan client_order_id = {coid}")
    try:
        r = await client.orders.create(
            symbol=TEST_SYMBOL, side="buy", order_type="market",
            tif="ioc", qty="0.3", client_order_id=coid,
        )
        order_id = r.order_id
        log(f"  Order created → order_id={order_id}, status={r.status}")
    except Exception as e:
        log(f"  ❌ Gagal buat order: {e}")
        return

    await asyncio.sleep(2)

    log(f"\n  Step 2: Coba get via client_order_id (cara yang intuitif)")
    try:
        detail = await client.orders.get(client_order_id=coid)
        log(f"  ✅ Berhasil — tidak ada bug")
    except Exception as e:
        log(f"  ❌ ERROR: {e}")
        log(f"  🐛 BUG CONFIRMED: orders.get() tidak support 'client_order_id'")

    log(f"\n  Step 3: Coba get via order_id (cara alternatif)")
    try:
        sig = inspect.signature(client.orders.get)
        params = list(sig.parameters.keys())
        log(f"  Parameter tersedia: {params}")
        # Coba order_id
        detail = await client.orders.get(order_id=order_id)
        log(f"  ✅ get(order_id=...) berhasil! Status: {detail.status}")
        log(f"  ℹ️  Workaround: gunakan order_id, bukan client_order_id")
    except Exception as e:
        log(f"  ❌ get(order_id=...) juga error: {e}")

    log(f"\n  Step 4: Coba cancel via order_id")
    log(f"  Signature cancel: {inspect.signature(client.orders.cancel)}")
    try:
        params_cancel = list(inspect.signature(client.orders.cancel).parameters.keys())
        log(f"  Parameter cancel: {params_cancel}")
    except Exception as e:
        log(f"  ❌ {e}")


async def verify_bug2_batch_create(client):
    """
    BUG #2: batch_create() — signature pakai 'items' bukan 'orders'
    Dokumentasi tidak menyebutkan ini dengan jelas
    """
    section("BUG #2 — batch_create() parameter 'items' tidak terdokumentasi")

    sig = inspect.signature(client.orders.batch_create)
    log(f"  Signature aktual : {sig}")
    log(f"  Expected di docs : batch_create(orders=[...])")
    log(f"  Actual parameter : items=[...]")
    log(f"\n  🐛 BUG: Dokumentasi/SDK menyebutkan 'orders' tapi actual adalah 'items'")
    log(f"  Dampak: Developer tidak bisa batch order tanpa inspect SDK langsung")

    log(f"\n  Verifikasi: batch_create(items=[...]) bekerja atau tidak?")
    sample = [
        dict(symbol=TEST_SYMBOL, side="buy", order_type="market",
             tif="ioc", qty="0.3",
             client_order_id=f"bug2-batch-{int(time.time()*1000)}-{i}")
        for i in range(3)
    ]
    try:
        r = await client.orders.batch_create(items=sample)
        log(f"  ✅ batch_create(items=...) BERHASIL")
        log(f"  Result type: {type(r)}")
        log(f"  Result attrs: {[k for k in dir(r) if not k.startswith('_')]}")
        if hasattr(r, 'orders'):
            log(f"  Orders count: {len(r.orders)}")
            for o in r.orders:
                log(f"    → {o.status} {getattr(o, 'client_order_id', 'N/A')}")
        elif hasattr(r, 'results'):
            log(f"  Results: {r.results}")
    except Exception as e:
        log(f"  ❌ batch_create(items=...) juga error: {e}")


async def verify_bug3_order_status_lifecycle(client):
    """
    BUG #3: Status 'accepted' tidak terdokumentasi dalam lifecycle order
    Docs hanya menyebut: created, armed, running, completed, cancelled, failed, paused
    Tapi market order return 'accepted'
    """
    section("BUG #3 — Status 'accepted' tidak ada di dokumentasi lifecycle")

    log(f"  Documented statuses (dari SDK docs):")
    log(f"  created, armed, running, completed, cancelled, failed, paused")
    log(f"\n  Observed status: 'accepted'")
    log(f"  🐛 BUG: 'accepted' tidak terdokumentasi — developer tidak tahu")
    log(f"          apakah order ini akan filled atau perlu polling manual")

    log(f"\n  Verifikasi: track status lifecycle lengkap market IOC order")
    coid = f"bug3-lifecycle-{int(time.time()*1000)}"
    try:
        r = await client.orders.create(
            symbol=TEST_SYMBOL, side="buy", order_type="market",
            tif="ioc", qty="0.5", client_order_id=coid,
        )
        log(f"  T+0s  status = {r.status}")
        log(f"  order_id     = {r.order_id}")

        # Poll status beberapa kali
        for delay in [1, 2, 5]:
            await asyncio.sleep(delay)
            try:
                # Coba get via order_id
                sig_params = list(inspect.signature(client.orders.get).parameters.keys())
                if 'order_id' in sig_params:
                    detail = await client.orders.get(order_id=r.order_id)
                    log(f"  T+{sum([1,2,5][:([1,2,5].index(delay)+1)]):2d}s status = {detail.status} | filled={getattr(detail,'filled_qty','?')}")
                else:
                    # Coba list recent orders
                    open_orders = await client.orders.list_open()
                    match = [o for o in open_orders.orders
                             if getattr(o, 'client_order_id', '') == coid]
                    if match:
                        log(f"  T+{delay}s  masih di list_open: status={match[0].status}")
                    else:
                        log(f"  T+{delay}s  tidak ada di list_open (sudah settled/cancelled)")
                        break
            except Exception as e:
                log(f"  T+{delay}s  error polling: {e}")
    except Exception as e:
        log(f"  ❌ Order gagal: {e}")


async def verify_bug4_cancel_signature(client):
    """
    BUG #4: orders.cancel() keyword argument — ditemukan di run pertama
    """
    section("BUG #4 — orders.cancel() keyword argument")

    sig = inspect.signature(client.orders.cancel)
    log(f"  Signature aktual: {sig}")
    params = list(sig.parameters.keys())
    log(f"  Parameters      : {params}")
    log(f"\n  Cara intuitif cancel: cancel(client_order_id='xxx')")
    log(f"  Cara intuitif cancel: cancel(order_id='xxx')")

    # Test cancel dengan berbagai cara
    # Buat order dulu
    coid = f"bug4-cancel-{int(time.time()*1000)}"
    try:
        r = await client.orders.create(
            symbol=TEST_SYMBOL, side="buy", order_type="limit",
            tif="gtc", qty="0.3", price="1",  # harga sangat rendah supaya tidak filled
            client_order_id=coid,
        )
        log(f"\n  Order GTC dibuat: {r.status} id={r.order_id}")
        oid = r.order_id

        # Coba cancel berbagai cara
        for kw, val in [("client_order_id", coid), ("order_id", oid)]:
            try:
                await client.orders.cancel(**{kw: val})
                log(f"  ✅ cancel({kw}=...) BERHASIL")
                break
            except Exception as e:
                log(f"  ❌ cancel({kw}=...) error: {e}")
    except Exception as e:
        log(f"  ❌ Gagal buat limit order: {e}")


async def print_final_report():
    section("RINGKASAN BUG UNTUK DILAPORKAN KE BUG SUPPORT")

    bugs = [
        {
            "id"      : "BUG-001",
            "severity": "MEDIUM",
            "title"   : "orders.get() tidak menerima 'client_order_id' sebagai parameter",
            "repro"   : "await client.orders.get(client_order_id='xxx')",
            "error"   : "AsyncOrdersService.get() got an unexpected keyword argument 'client_order_id'",
            "impact"  : "Developer tidak bisa lookup order by client_order_id setelah submit",
        },
        {
            "id"      : "BUG-002",
            "severity": "MEDIUM",
            "title"   : "batch_create() parameter bernama 'items' bukan 'orders' (tidak terdokumentasi)",
            "repro"   : "await client.orders.batch_create(orders=[...])  # gagal\nawait client.orders.batch_create(items=[...])   # berhasil",
            "error"   : "AsyncOrdersService.batch_create() got an unexpected keyword argument 'orders'",
            "impact"  : "Developer tidak bisa gunakan batch order sesuai dokumentasi",
        },
        {
            "id"      : "BUG-003",
            "severity": "LOW",
            "title"   : "Status 'accepted' tidak terdokumentasi dalam order lifecycle",
            "repro"   : "Market IOC order langsung return status='accepted'",
            "error"   : "Status 'accepted' tidak ada di docs (hanya: filled, cancelled, rejected, dll)",
            "impact"  : "Developer tidak tahu apakah order akan settled atau perlu action tambahan",
        },
        {
            "id"      : "BUG-004",
            "severity": "MEDIUM",
            "title"   : "orders.cancel() tidak menerima 'client_order_id' sebagai parameter",
            "repro"   : "await client.orders.cancel(client_order_id='xxx')",
            "error"   : "AsyncOrdersService.cancel() got an unexpected keyword argument 'client_order_id'",
            "impact"  : "Developer harus pakai order_id internal, bukan client_order_id yang mereka set sendiri",
        },
    ]

    for b in bugs:
        log(f"\n  [{b['id']}] [{b['severity']}] {b['title']}")
        log(f"  Reproduce : {b['repro']}")
        log(f"  Error     : {b['error']}")
        log(f"  Impact    : {b['impact']}")

    # Save ke file
    with open("bug_report_final.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    log(f"\n\n📄 Full report disimpan ke bug_report_final.txt")
    log(f"📋 Siap dilaporkan ke Bug Support Polyester!")


async def main():
    accounts = json.load(open(ACCOUNTS_FILE))
    account  = accounts[0]

    async with AsyncPolyester(
        api_key_id        =account["api_key_id"],
        api_private_key   =account["api_private_key"],
        default_account_id=account["account_id"],
        api_url           =API_URL,
        ws_url            =WS_URL,
    ) as client:
        await client.wait_for_catalogs()
        log("✅ Koneksi berhasil\n")

        await verify_bug1_orders_get(client)
        await asyncio.sleep(2)
        await verify_bug2_batch_create(client)
        await asyncio.sleep(2)
        await verify_bug3_order_status_lifecycle(client)
        await asyncio.sleep(2)
        await verify_bug4_cancel_signature(client)

    await print_final_report()

if __name__ == "__main__":
    asyncio.run(main())
