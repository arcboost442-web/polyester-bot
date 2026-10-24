import asyncio
import json
import random
import time
from pathlib import Path
from polyester import AsyncPolyester

# ==================== CONFIG ====================
ACCOUNTS_FILE = "accounts.json"
REPORT_FILE   = "bug_report.json"
API_URL       = "https://api.testnet.polyester.com"
WS_URL        = "wss://api.testnet.polyester.com"
TEST_SYMBOL   = "SOL-USDC"   # ganti sesuai pair yang aktif
# ================================================

bugs_found  = []
tests_done  = []

def log_bug(test_name, description, expected, actual, severity="HIGH"):
    entry = {
        "test"       : test_name,
        "description": description,
        "expected"   : expected,
        "actual"     : actual,
        "severity"   : severity,
        "timestamp"  : time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    bugs_found.append(entry)
    print(f"\n🐛 BUG DITEMUKAN [{severity}]: {test_name}")
    print(f"   Expected : {expected}")
    print(f"   Actual   : {actual}")
    print(f"   Detail   : {description}")

def log_ok(test_name, note=""):
    tests_done.append({"test": test_name, "status": "OK", "note": note})
    print(f"   ✅ {test_name} — OK {note}")

def log_skip(test_name, reason=""):
    tests_done.append({"test": test_name, "status": "SKIP", "note": reason})
    print(f"   ⏭️  {test_name} — SKIP ({reason})")

def save_report():
    report = {
        "total_tests" : len(tests_done),
        "bugs_found"  : len(bugs_found),
        "bugs"        : bugs_found,
        "all_tests"   : tests_done,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(REPORT_FILE, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n📄 Report disimpan ke {REPORT_FILE}")


# ============================================================
#  AREA 1 — ORDER EXECUTION
# ============================================================
async def test_market_order_fills(client):
    """Market IOC order — apakah benar-benar tereksekusi?"""
    test = "market_ioc_fill"
    print(f"\n🔬 [{test}] Market IOC order fill check...")
    try:
        result = await client.orders.create(
            symbol=TEST_SYMBOL,
            side="buy",
            order_type="market",
            tif="ioc",
            qty="0.3",
            client_order_id=f"bh-market-{int(time.time()*1000)}",
        )
        status = result.status
        if status in ("filled", "partially_filled"):
            log_ok(test, f"status={status}")
        elif status in ("cancelled", "rejected", "expired"):
            log_bug(test,
                    "Market IOC order tidak tereksekusi — volume tidak akan terhitung",
                    "filled / partially_filled",
                    status,
                    severity="HIGH")
        else:
            log_bug(test, f"Status tidak dikenal: {status}", "filled", status, severity="MEDIUM")
    except Exception as e:
        log_bug(test, str(e), "Order sukses", f"Exception: {e}", severity="HIGH")


async def test_duplicate_client_order_id(client):
    """Kirim 2 order dengan client_order_id yang sama → harusnya error/reject pada yg ke-2"""
    test = "duplicate_client_order_id"
    print(f"\n🔬 [{test}] Duplicate client_order_id check...")
    coid = f"bh-dup-{int(time.time()*1000)}"
    try:
        r1 = await client.orders.create(
            symbol=TEST_SYMBOL, side="buy", order_type="market",
            tif="ioc", qty="0.3", client_order_id=coid,
        )
        await asyncio.sleep(1)
        try:
            r2 = await client.orders.create(
                symbol=TEST_SYMBOL, side="buy", order_type="market",
                tif="ioc", qty="0.3", client_order_id=coid,
            )
            # Kalau r2 sukses tanpa error = BUG
            log_bug(test,
                    "Order ke-2 dengan client_order_id sama diterima tanpa error",
                    "Error / rejection pada order ke-2",
                    f"status={r2.status}",
                    severity="HIGH")
        except Exception as e2:
            log_ok(test, f"Order ke-2 ditolak dengan benar: {str(e2)[:60]}")
    except Exception as e:
        log_skip(test, f"Order pertama gagal: {str(e)[:60]}")


async def test_zero_qty_order(client):
    """Order qty=0 → harusnya error"""
    test = "zero_qty_order"
    print(f"\n🔬 [{test}] Zero qty order check...")
    try:
        r = await client.orders.create(
            symbol=TEST_SYMBOL, side="buy", order_type="market",
            tif="ioc", qty="0",
            client_order_id=f"bh-zero-{int(time.time()*1000)}",
        )
        log_bug(test,
                "Order qty=0 diterima tanpa error",
                "Error / validation rejection",
                f"status={r.status}",
                severity="HIGH")
    except Exception as e:
        log_ok(test, f"Ditolak dengan benar: {str(e)[:80]}")


async def test_invalid_symbol(client):
    """Order dengan symbol tidak valid → harusnya error"""
    test = "invalid_symbol"
    print(f"\n🔬 [{test}] Invalid symbol check...")
    try:
        r = await client.orders.create(
            symbol="FAKE-COIN", side="buy", order_type="market",
            tif="ioc", qty="1",
            client_order_id=f"bh-inv-{int(time.time()*1000)}",
        )
        log_bug(test,
                "Order dengan symbol FAKE-COIN diterima",
                "Error / rejection",
                f"status={r.status}",
                severity="HIGH")
    except Exception as e:
        log_ok(test, f"Ditolak: {str(e)[:80]}")


async def test_cancel_nonexistent_order(client):
    """Cancel order_id yang tidak ada → harusnya error bukan silent success"""
    test = "cancel_nonexistent_order"
    print(f"\n🔬 [{test}] Cancel non-existent order check...")
    fake_id = "bh-nonexistent-999999999999"
    try:
        await client.orders.cancel(client_order_id=fake_id)
        log_bug(test,
                "Cancel order tidak ada tidak menghasilkan error",
                "Error / not found exception",
                "Silent success (tidak ada exception)",
                severity="MEDIUM")
    except Exception as e:
        log_ok(test, f"Error dikembalikan dengan benar: {str(e)[:80]}")


async def test_batch_order_limit(client):
    """Batch 20 order (limit max) → semua harus masuk"""
    test = "batch_order_max_limit"
    print(f"\n🔬 [{test}] Batch 20 orders (max limit)...")
    try:
        orders = [
            {
                "symbol"          : TEST_SYMBOL,
                "side"            : random.choice(["buy", "sell"]),
                "order_type"      : "market",
                "tif"             : "ioc",
                "qty"             : "0.3",
                "client_order_id" : f"bh-batch-{int(time.time()*1000)}-{i}",
            }
            for i in range(20)
        ]
        result = await client.orders.batch_create(orders=orders)
        created = len(result.orders) if hasattr(result, "orders") else "unknown"
        if created == 20:
            log_ok(test, f"Semua 20 order masuk")
        else:
            log_bug(test,
                    f"Hanya {created} dari 20 order yang masuk",
                    "20 orders",
                    f"{created} orders",
                    severity="MEDIUM")
    except AttributeError:
        log_skip(test, "batch_create belum tersedia di SDK ini")
    except Exception as e:
        log_bug(test, str(e), "Batch sukses", f"Exception: {e}", severity="MEDIUM")


# ============================================================
#  AREA 2 — BALANCE & VIP
# ============================================================
async def test_balance_available(client):
    """Cek balance bisa diambil dan formatnya benar"""
    test = "balance_list"
    print(f"\n🔬 [{test}] Balance list check...")
    try:
        result = await client.balances.list()
        if result:
            log_ok(test, f"Balance tersedia")
        else:
            log_bug(test,
                    "Balance list kosong",
                    "Ada balance",
                    "Empty list",
                    severity="LOW")
    except Exception as e:
        log_bug(test, str(e), "Balance list sukses", f"Exception: {e}", severity="HIGH")


async def test_vip_status(client):
    """Cek endpoint VIP status bisa diakses"""
    test = "vip_status_endpoint"
    print(f"\n🔬 [{test}] VIP status endpoint check...")
    try:
        # Coba akses via raw jika belum ada wrapper
        result = await client.vip.get_status() if hasattr(client, "vip") else None
        if result is None:
            log_skip(test, "client.vip belum tersedia di SDK — cek manual via API")
        else:
            log_ok(test, f"VIP status: {result}")
    except AttributeError:
        log_skip(test, "VIP endpoint belum ada di SDK versi ini")
    except Exception as e:
        log_bug(test, str(e), "VIP status sukses", f"Exception: {e}", severity="MEDIUM")


async def test_open_orders_after_cancel_all(client):
    """Cancel all orders → list_open harusnya kosong"""
    test = "open_orders_after_cancel_all"
    print(f"\n🔬 [{test}] Open orders setelah cancel all...")
    try:
        await client.orders.cancel_all(symbol=TEST_SYMBOL)
        await asyncio.sleep(2)
        open_orders = await client.orders.list_open()
        remaining = [o for o in open_orders.orders if o.symbol == TEST_SYMBOL]
        if len(remaining) == 0:
            log_ok(test, "Tidak ada order tersisa setelah cancel_all")
        else:
            log_bug(test,
                    f"Masih ada {len(remaining)} order setelah cancel_all",
                    "0 open orders",
                    f"{len(remaining)} open orders",
                    severity="HIGH")
    except Exception as e:
        log_skip(test, f"cancel_all error: {str(e)[:80]}")


# ============================================================
#  AREA 3 — MARKET DATA
# ============================================================
async def test_candle_data(client):
    """Candle data harus bisa diambil"""
    test = "candle_data"
    print(f"\n🔬 [{test}] Candle data check...")
    try:
        candles = await client.market_data.get_candles(
            symbol=TEST_SYMBOL, timeframe="1m", limit=10
        )
        if candles and len(candles) > 0:
            log_ok(test, f"{len(candles)} candles diterima")
        else:
            log_bug(test, "Candle data kosong", "Ada candles", "Empty", severity="LOW")
    except Exception as e:
        log_bug(test, str(e), "Candle data sukses", f"Exception: {e}", severity="MEDIUM")


async def test_trades_data(client):
    """Recent trades harus bisa diambil"""
    test = "trades_data"
    print(f"\n🔬 [{test}] Recent trades check...")
    try:
        trades = await client.market_data.get_trades(symbol=TEST_SYMBOL, limit=10)
        if trades and len(trades) > 0:
            log_ok(test, f"{len(trades)} trades diterima")
        else:
            log_bug(test, "Trades kosong", "Ada trades", "Empty", severity="LOW")
    except Exception as e:
        log_bug(test, str(e), "Trades sukses", f"Exception: {e}", severity="MEDIUM")


async def test_market_overview(client):
    """Market overview harus tersedia"""
    test = "market_overview"
    print(f"\n🔬 [{test}] Market overview check...")
    try:
        overview = await client.market_overview.list(limit=10)
        if overview and len(overview.markets) > 0:
            log_ok(test, f"{len(overview.markets)} markets")
        else:
            log_bug(test, "Overview kosong", "Ada markets", "Empty", severity="LOW")
    except Exception as e:
        log_bug(test, str(e), "Overview sukses", f"Exception: {e}", severity="MEDIUM")


# ============================================================
#  AREA 4 — EDGE CASES
# ============================================================
async def test_float_qty_rejected(client):
    """Float sebagai qty harusnya error atau auto-convert, bukan crash diam"""
    test = "float_qty_input"
    print(f"\n🔬 [{test}] Float qty input check...")
    try:
        r = await client.orders.create(
            symbol=TEST_SYMBOL, side="buy", order_type="market",
            tif="ioc", qty=0.3,   # float bukan string
            client_order_id=f"bh-float-{int(time.time()*1000)}",
        )
        # Kalau tidak crash = ok jika dikonversi, tapi perlu dicatat
        log_bug(test,
                "Float qty diterima tanpa warning/error — docs bilang jangan pakai float",
                "Error atau explicit warning",
                f"Diterima, status={r.status}",
                severity="LOW")
    except (TypeError, ValueError) as e:
        log_ok(test, f"Float ditolak di sisi SDK: {str(e)[:60]}")
    except Exception as e:
        log_ok(test, f"Rejected: {str(e)[:60]}")


async def test_negative_qty(client):
    """Qty negatif harusnya ditolak"""
    test = "negative_qty"
    print(f"\n🔬 [{test}] Negative qty check...")
    try:
        r = await client.orders.create(
            symbol=TEST_SYMBOL, side="buy", order_type="market",
            tif="ioc", qty="-1",
            client_order_id=f"bh-neg-{int(time.time()*1000)}",
        )
        log_bug(test,
                "Order qty negatif diterima",
                "Error / rejection",
                f"status={r.status}",
                severity="HIGH")
    except Exception as e:
        log_ok(test, f"Ditolak: {str(e)[:80]}")


async def test_very_large_qty(client):
    """Qty sangat besar — harusnya ditolak atau ada max limit"""
    test = "very_large_qty"
    print(f"\n🔬 [{test}] Very large qty check...")
    try:
        r = await client.orders.create(
            symbol=TEST_SYMBOL, side="buy", order_type="market",
            tif="ioc", qty="999999999",
            client_order_id=f"bh-large-{int(time.time()*1000)}",
        )
        log_bug(test,
                "Order qty sangat besar diterima tanpa error",
                "Error / rejection karena insufficient balance atau limit",
                f"status={r.status}",
                severity="MEDIUM")
    except Exception as e:
        log_ok(test, f"Ditolak: {str(e)[:80]}")


# ============================================================
#  RUNNER UTAMA
# ============================================================
async def run_all_tests(account: dict):
    print(f"\n{'='*60}")
    print(f"  POLYESTER BUG HUNTER — Akun: {account.get('name')}")
    print(f"  Symbol: {TEST_SYMBOL} | SDK: 0.1.0a55")
    print(f"{'='*60}\n")

    async with AsyncPolyester(
        api_key_id       =account["api_key_id"],
        api_private_key  =account["api_private_key"],
        default_account_id=account["account_id"],
        api_url          =API_URL,
        ws_url           =WS_URL,
    ) as client:
        await client.wait_for_catalogs()
        print("✅ Koneksi berhasil, katalog loaded\n")

        # --- AREA 1: Order Execution ---
        print("📦 AREA 1: Order Execution Tests")
        print("-" * 40)
        await test_market_order_fills(client)
        await asyncio.sleep(1)
        await test_duplicate_client_order_id(client)
        await asyncio.sleep(1)
        await test_zero_qty_order(client)
        await asyncio.sleep(1)
        await test_invalid_symbol(client)
        await asyncio.sleep(1)
        await test_cancel_nonexistent_order(client)
        await asyncio.sleep(1)
        await test_batch_order_limit(client)
        await asyncio.sleep(1)

        # --- AREA 2: Balance & VIP ---
        print("\n💰 AREA 2: Balance & VIP Tests")
        print("-" * 40)
        await test_balance_available(client)
        await asyncio.sleep(1)
        await test_vip_status(client)
        await asyncio.sleep(1)
        await test_open_orders_after_cancel_all(client)
        await asyncio.sleep(1)

        # --- AREA 3: Market Data ---
        print("\n📊 AREA 3: Market Data Tests")
        print("-" * 40)
        await test_candle_data(client)
        await asyncio.sleep(1)
        await test_trades_data(client)
        await asyncio.sleep(1)
        await test_market_overview(client)
        await asyncio.sleep(1)

        # --- AREA 4: Edge Cases ---
        print("\n⚠️  AREA 4: Edge Cases")
        print("-" * 40)
        await test_float_qty_rejected(client)
        await asyncio.sleep(1)
        await test_negative_qty(client)
        await asyncio.sleep(1)
        await test_very_large_qty(client)

    # --- Ringkasan ---
    print(f"\n{'='*60}")
    print(f"  RINGKASAN HASIL")
    print(f"{'='*60}")
    print(f"  Total tests : {len(tests_done)}")
    print(f"  🐛 Bug found : {len(bugs_found)}")
    if bugs_found:
        print(f"\n  Bugs ditemukan:")
        for b in bugs_found:
            print(f"  [{b['severity']}] {b['test']}: {b['description']}")
    else:
        print("  Tidak ada bug obvious yang ditemukan di run ini.")

    save_report()


async def main():
    path = Path(ACCOUNTS_FILE)
    if not path.exists():
        print(f"❌ {ACCOUNTS_FILE} tidak ditemukan!")
        return
    accounts = json.load(open(path))
    if not accounts:
        print("Tidak ada akun!")
        return

    # Pakai akun pertama saja untuk bug hunting
    account = accounts[0]
    print(f"Menggunakan akun: {account.get('name')}")
    await run_all_tests(account)


if __name__ == "__main__":
    asyncio.run(main())
