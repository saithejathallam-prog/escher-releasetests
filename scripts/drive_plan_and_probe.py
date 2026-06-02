#!/usr/bin/env python3
"""Drive Escher PROD to the CloudTrail-plan view and dump its AX tree.

We can't probe the plan view by re-opening an existing chat from Recent —
once a plan has been resolved (Approve/Cancel clicked), Escher only keeps
the plan TEXT as transcript; the Approve/Cancel/radio action UI is one-shot
and gone forever for that conversation. So this script generates a fresh
plan stream just for the purpose of capturing the AX tree of the action UI.

What it does:
  1. Attach to the running Escher PROD via Mac2.
  2. Click "New Chat".
  3. Type the CloudTrail prompt and submit.
  4. Wait until the static-text content under the WebView stops changing
     for 5 consecutive seconds.
  5. Dump the resulting accessibility tree to:
        results/plan_window_subtree.xml   (windows only, pretty-printed)
        results/plan_view_probe.png       (screenshot for context)
  6. End the Mac2 session WITHOUT clicking any action button.

The plan stays open in Escher after this script exits. Dismiss it yourself
by clicking Cancel in the UI — DO NOT click Approve (it provisions real AWS
resources on PROD).
"""
from __future__ import annotations

import hashlib
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.dom import minidom

from appium import webdriver
from appium.options.common.base import AppiumOptions

APPIUM_URL = "http://127.0.0.1:4723"
BUNDLE_ID = "com.escher.v2-desktop-app-tauri"
PROMPT = "create a remediation plan for cloudtrail logging gaps"

SETTLE_SECONDS = 5.0
STREAM_TIMEOUT = 180.0
POLL_INTERVAL = 2.0


def static_text_signature(driver) -> tuple[str, int]:
    web = driver.find_element("xpath", "//XCUIElementTypeWebView")
    nodes = web.find_elements("xpath", ".//XCUIElementTypeStaticText")
    joined = "\n".join((n.get_attribute("value") or "") for n in nodes)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest(), len(nodes)


def wait_until_stable(driver) -> None:
    last_sig = None
    last_change = time.monotonic()
    deadline = time.monotonic() + STREAM_TIMEOUT
    while time.monotonic() < deadline:
        sig, count = static_text_signature(driver)
        now = time.monotonic()
        if sig != last_sig:
            last_sig = sig
            last_change = now
            print(f"  streaming… {count} text nodes (sig {sig[:8]})")
        elif now - last_change >= SETTLE_SECONDS:
            print(f"  stable for {now - last_change:.1f}s")
            return
        time.sleep(POLL_INTERVAL)
    raise RuntimeError(
        f"Plan never stabilised within {STREAM_TIMEOUT}s — check Escher manually."
    )


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    results_dir = repo_root / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    xml_path = results_dir / "plan_window_subtree.xml"
    png_path = results_dir / "plan_view_probe.png"

    options = AppiumOptions()
    options.set_capability("platformName", "mac")
    options.set_capability("appium:automationName", "mac2")
    options.set_capability("appium:bundleId", BUNDLE_ID)
    options.set_capability("appium:newCommandTimeout", 300)

    print(f"Attaching to Escher PROD ({BUNDLE_ID}) via {APPIUM_URL}")
    driver = webdriver.Remote(APPIUM_URL, options=options)
    driver.implicitly_wait(5)

    try:
        print("Clicking New Chat")
        driver.find_element("xpath", '//XCUIElementTypeButton[@title="New Chat"]').click()
        time.sleep(2)

        print("Typing the prompt")
        prompt = driver.find_element("xpath", "//XCUIElementTypeTextView")
        prompt.click()
        prompt.send_keys(PROMPT)
        time.sleep(1)

        print("Clicking Send")
        send = driver.find_element(
            "xpath",
            "//XCUIElementTypeTextView/parent::*/following-sibling::XCUIElementTypeButton[2]",
        )
        send.click()

        print("Waiting for plan to finish streaming…")
        wait_until_stable(driver)

        print("\nDumping AX tree…")
        page = driver.page_source
        root = ET.fromstring(page)
        wrapper = ET.Element("Windows")
        for w in root.findall(".//XCUIElementTypeWindow"):
            wrapper.append(w)
        pretty = minidom.parseString(
            ET.tostring(wrapper, encoding="unicode")
        ).toprettyxml(indent="  ")
        xml_path.write_text(pretty, encoding="utf-8")
        print(f"  → {xml_path}")

        driver.save_screenshot(str(png_path))
        print(f"  → {png_path}")

        print(
            "\nLeaving the plan open in Escher. "
            "Click Cancel by hand to dismiss when you're done. "
            "Do NOT click Approve."
        )
        return 0
    finally:
        driver.quit()


if __name__ == "__main__":
    sys.exit(main())
