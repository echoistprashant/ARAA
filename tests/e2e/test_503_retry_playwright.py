import functools
import http.server
import json
import socketserver
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def _start_static_server():
    static_dir = str(Path(__file__).resolve().parents[2] / "app" / "static")
    handler = functools.partial(_QuietHandler, directory=static_dir)
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, port


def test_503_retry_and_error_message_playwright():
    """Mocks HTTP 503 responses on POST /api/v1/runs to verify retry and clear error UI."""
    httpd, port = _start_static_server()
    base_url = f"http://127.0.0.1:{port}/index.html"

    try:
        with sync_playwright() as p:
            browser = None
            for launch_kwargs in ({"headless": True}, {"headless": True, "channel": "msedge"}, {"headless": True, "channel": "chrome"}):
                try:
                    browser = p.chromium.launch(**launch_kwargs)
                    break
                except Exception:
                    continue
            if browser is None:
                raise RuntimeError("No Playwright Chromium/Edge/Chrome browser available")
            page = browser.new_page(viewport={"width": 1440, "height": 900})

            # Mock history endpoint so initial load is clean
            page.route("**/api/v1/runs?*", lambda route: route.fulfill(status=200, content_type="application/json", body="[]"))
            page.route("**/api/v1/events/runs/*/stream", lambda route: route.fulfill(status=200, content_type="text/event-stream", body=""))

            # 1) Empty submit shows validation message
            page.goto(base_url, wait_until="domcontentloaded")
            page.click("#startBtn")
            assert page.locator("#queryValidationError").is_visible()

            # 2) First POST returns 503 -> UI retries -> second POST returns 200
            attempt_count_retry = {"n": 0}

            def handle_retry_then_ok(route):
                attempt_count_retry["n"] += 1
                if attempt_count_retry["n"] == 1:
                    route.fulfill(status=503, content_type="application/json", body=json.dumps({"detail": "Source temporarily unavailable"}))
                else:
                    route.fulfill(status=200, content_type="application/json", body=json.dumps({"run_id": "run_retry_ok"}))

            page.route("**/api/v1/runs", handle_retry_then_ok)
            page.fill("#taskInput", "Test 503 retry recovery")
            page.click("#startBtn")
            page.wait_for_selector("text=Allocated run ID: run_retry_ok", timeout=5000)
            assert attempt_count_retry["n"] == 2
            assert page.locator("#terminalFeed").inner_text().find("Retrying Dispatch") != -1

            # 3) Persistent 503 -> UI retries once then shows clear error message
            page.unroute("**/api/v1/runs")
            page.goto(base_url, wait_until="domcontentloaded")
            attempt_count_fail = {"n": 0}

            def handle_persistent_503(route):
                attempt_count_fail["n"] += 1
                route.fulfill(status=503, content_type="application/json", body=json.dumps({"detail": "Upstream source 503"}))

            page.route("**/api/v1/runs", handle_persistent_503)
            page.fill("#taskInput", "Test persistent 503 error banner")
            page.click("#startBtn")
            page.wait_for_selector(".error-alert-box", timeout=5000)
            assert attempt_count_fail["n"] == 2
            error_text = page.locator(".error-alert-box").inner_text()
            assert "Investigation Failed" in error_text
            assert "503" in error_text
            assert not page.locator("#startBtn").is_disabled()

            browser.close()
    finally:
        httpd.shutdown()
        httpd.server_close()
