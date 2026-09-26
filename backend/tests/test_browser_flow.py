"""Controlled browser flow through the real UI, API, worker, and migrated database."""

import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from alembic.config import Config

from alembic import command
from netsentinel.discovery import ProbeResult
from netsentinel.main import create_app


class ControlledProbe:
    async def scan(self, _scope):
        return [ProbeResult("10.0.0.7", True, 2.0, "aa:bb:cc:dd:ee:ff", "tcp", {80: "unreachable"})]


def test_browser_setup_scan_device_and_alert(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    playwright = pytest.importorskip("playwright.sync_api")
    root = Path(__file__).parents[2]
    dist = root / "frontend" / "dist"
    if not (dist / "index.html").exists():
        pytest.skip("Run pnpm build in frontend before the browser test")
    browser_path = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    if not browser_path.exists():
        pytest.skip("Google Chrome is needed for the local browser test")
    database_url = f"sqlite:///{(tmp_path / 'browser.db').as_posix()}"
    config = Config(str(root / "backend" / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
    monkeypatch.setenv("NETSENTINEL_STATIC_DIR", str(dist))
    app = create_app(database_url)
    app.state.prober = ControlledProbe()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", log_level="error"))
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        assert server.started
        with playwright.sync_playwright() as driver:
            browser = driver.chromium.launch(executable_path=str(browser_path), headless=True)
            page = browser.new_page()
            page_errors: list[str] = []
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.on("dialog", lambda dialog: dialog.accept())
            page.goto(f"http://127.0.0.1:{port}/")
            page.get_by_label("Username").fill("owner")
            page.get_by_label("Password").fill("a-long-test-password")
            page.get_by_role("button", name="Create account").click()
            page.get_by_role("button", name="Settings").click()
            page.get_by_label("Private IPv4 CIDR").fill("10.0.0.0/28")
            page.get_by_label(
                "I own or am authorized to administer this range and approve bounded scans."
            ).check()
            page.get_by_role("button", name="Approve range").click()
            page.get_by_role("button", name="Run discovery").click()
            page.get_by_text("Run #1: completed").wait_for(timeout=15000)
            page.get_by_role("button", name="Devices").click()
            page.get_by_role("button", name="Open 10.0.0.7").click()
            page.get_by_text("TCP 80 · unreachable").wait_for()
            page.get_by_text("Reachability history").wait_for()
            page.get_by_role("button", name="Network map").click()
            page.get_by_text("Devices in map").wait_for()
            page.get_by_text("Inferred subnet grouping").wait_for()
            page.get_by_role("button", name="Alerts").click()
            page.get_by_text("New device observed: 10.0.0.7").wait_for()
            page.get_by_text("Evidence: observation:").wait_for()
            page.get_by_role("button", name="Acknowledge").click()
            page.get_by_text("acknowledged", exact=True).wait_for()
            page.get_by_role("button", name="Timeline").click()
            try:
                page.get_by_text("Acknowledged: New device observed: 10.0.0.7").wait_for(
                    timeout=15000
                )
            except Exception as exc:
                timeline_text = page.locator("body").inner_text()
                pytest.fail(
                    f"Timeline did not show acknowledgment at {page.url}: "
                    f"{timeline_text}; page errors: {page_errors}; {exc}"
                )
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
