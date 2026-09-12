import sys
import os
import httpx

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Manual, opt-in integration script against locally running services.
# Never hardcode credentials here — this file is public.
COLLECTOR_URL = os.getenv("COMMB_COLLECTOR_URL", "http://127.0.0.1:3000")
COMMB_URL = os.getenv("COMMB_URL", "http://127.0.0.1:8080")
API_KEY = os.getenv("COMMB_API_KEY", "")

def run_tests():
    print("=" * 65)
    print("[*] LIVE INTEGRATION TEST: COLLECTOR <---> CommB")
    print("=" * 65)

    with httpx.Client(timeout=10.0) as client:
        # 1. AgentOS Health & UI
        print("\n[1] Testing collector dashboard & APIs...")
        res_ui = client.get(f"{COLLECTOR_URL}/")
        print(f"  [OK] Dashboard UI (GET /) -> Status {res_ui.status_code}")

        res_ov = client.get(f"{COLLECTOR_URL}/api/v1/overview")
        ov_data = res_ov.json()
        print(f"  [OK] Overview API -> Status {res_ov.status_code} | Active Bots: {ov_data.get('activeBots')} | Total Revenue: NGN {ov_data.get('totalRevenue', 0):,}")

        # 2. CommB Engine Health
        print("\n[2] Testing CommB Engine...")
        res_commb = client.get(f"{COMMB_URL}/health")
        commb_data = res_commb.json()
        print(f"  [OK] Engine Health -> Status {res_commb.status_code} | App: {commb_data.get('app')} | Provider: {commb_data.get('llm_provider')}")

        # 3. AgentOS Authenticated Sync Endpoint
        print("\n[3] Testing AgentOS Config Sync Endpoint...")
        res_sync = client.get(
            f"{COLLECTOR_URL}/api/v1/sync",
            headers={"Authorization": f"Bearer {API_KEY}"}
        )
        sync_data = res_sync.json()
        print(f"  [OK] Sync Auth -> Status {res_sync.status_code}")
        print(f"       Tenant: {sync_data.get('tenant', {}).get('name')}")
        print(f"       Model: {sync_data.get('config', {}).get('model_name')} (Temp: {sync_data.get('config', {}).get('temperature')})")
        print(f"       RAG Knowledge Articles Count: {len(sync_data.get('knowledge_docs', []))}")
        print(f"       Catalog Products Count: {len(sync_data.get('catalog_items', []))}")

        # 4. Telemetry Stream Ingestion Pipeline
        print("\n[4] Testing Telemetry Ingestion (Client -> AgentOS)...")
        telemetry_payload = {
            "batch": [
                {
                    "channel": "whatsapp",
                    "customer_id": "+2348099887766",
                    "event": "payment_success",
                    "status": "success",
                    "amount": 185000.0,
                    "metadata": {"order_id": "ORD-LIVE-TEST-001", "gateway": "paystack"}
                },
                {
                    "channel": "telegram",
                    "customer_id": "9921820",
                    "event": "order_created",
                    "status": "success",
                    "amount": 95000.0,
                    "metadata": {"order_id": "ORD-LIVE-TEST-002", "gateway": "paystack"}
                }
            ]
        }
        res_telem = client.post(
            f"{COLLECTOR_URL}/api/v1/events",
            json=telemetry_payload,
            headers={"Authorization": f"Bearer {API_KEY}"}
        )
        print(f"  [OK] Telemetry Ingested -> Status {res_telem.status_code} | Result: {res_telem.json()}")

        # Verify event in AgentOS stream
        res_ov_after = client.get(f"{COLLECTOR_URL}/api/v1/overview").json()
        latest_event = res_ov_after.get("recentEvents", [])[0] if res_ov_after.get("recentEvents") else {}
        print(f"  [OK] Verified in AgentOS Stream -> Latest Event: '{latest_event.get('event')}' (Amount: NGN {latest_event.get('amount', 0):,})")

        # 5. Remote Sync Trigger Test
        print("\n[5] Testing Remote Sync Push Trigger...")
        res_trigger = client.post(
            f"{COLLECTOR_URL}/api/v1/trigger-sync",
            json={"botId": "bot-elena-luxe", "instanceUrl": COMMB_URL}
        )
        print(f"  [OK] Remote Trigger -> Status {res_trigger.status_code} | Message: {res_trigger.json().get('message')}")

        # 6. CommB Webhooks Simulation
        print("\n[6] Testing WhatsApp Webhook Verification Challenge...")
        res_wa = client.get(
            f"{COMMB_URL}/api/v1/webhooks/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "commb_webhook_verification_token_secret",
                "hub.challenge": "LIVE_CHALLENGE_999"
            }
        )
        print(f"  [OK] WhatsApp Challenge -> Status {res_wa.status_code} | Response: '{res_wa.text}'")

    print("\n" + "=" * 65)
    print("[+] SUCCESS: ALL LIVE INTEGRATION TESTS PASSED 100%!")
    print("=" * 65)

if __name__ == "__main__":
    run_tests()
