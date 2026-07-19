import requests
import json
import time
import subprocess
import os

def test_webhooks():
    # Start the server in the background
    server_process = subprocess.Popen(["python", "bridge.py"])
    time.sleep(2) # Give the server time to start

    try:
        # 1. Update config to enable webhooks and set a secret
        config_url = 'http://localhost:5000/api/settings'
        config_data = {
            "webhookEnabled": True,
            "webhookSecret": "supersecret123"
        }
        requests.post(config_url, json=config_data)

        url_radarr = 'http://localhost:5000/api/webhook/radarr'
        url_jellyfin = 'http://localhost:5000/api/webhook/jellyfin'

        payload_radarr = {"eventType": "Download", "movie": {"title": "Test"}}
        payload_jellyfin = {"NotificationType": "ItemAdded", "Item": {"Name": "Test"}}

        # Test Radarr Webhook
        print("Testing Radarr Webhook...")
        # Missing secret
        resp = requests.post(url_radarr, json=payload_radarr)
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"

        # Invalid secret
        resp = requests.post(url_radarr, json=payload_radarr, headers={"X-Webhook-Secret": "wrong"})
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"

        # Valid secret
        resp = requests.post(url_radarr, json=payload_radarr, headers={"X-Webhook-Secret": "supersecret123"})
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        print("Radarr Webhook OK")

        # Test Jellyfin Webhook
        print("Testing Jellyfin Webhook...")
        # Missing secret
        resp = requests.post(url_jellyfin, json=payload_jellyfin)
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"

        # Invalid secret
        resp = requests.post(url_jellyfin, json=payload_jellyfin, headers={"X-Webhook-Secret": "wrong"})
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"

        # Valid secret
        resp = requests.post(url_jellyfin, json=payload_jellyfin, headers={"X-Webhook-Secret": "supersecret123"})
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        print("Jellyfin Webhook OK")

        print("All tests passed!")

    finally:
        # Terminate the server
        server_process.terminate()
        server_process.wait()

if __name__ == '__main__':
    test_webhooks()
