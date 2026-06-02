#!/usr/bin/env python3
"""
Probe Escher-Staging's accessibility tree so we can read off real selectors.

Recommended usage
-----------------
1. Launch Escher-Staging by hand and navigate to the screen you want to inspect
   (e.g. the chat screen with the "New Chat" link visible).
2. In one terminal:
       appium
3. In another terminal:
       python scripts/probe_accessibility_tree.py
   The probe attaches to the already-running Escher process; it doesn't reset it.

Outputs
-------
    results/accessibility_dump_before.png   Screenshot taken at session start
    results/accessibility_dump.png          Screenshot after the settle wait
    results/accessibility_dump.xml          Full AX tree (Escher app + menu bar + touch bar)
    results/window_subtree.xml              Just the <XCUIElementTypeWindow> subtree(s) —
                                             this is where the chat UI lives
    stdout                                   Summary of every named element inside the
                                             Escher window(s) — the candidate selectors.

First-run note
--------------
macOS will prompt for Accessibility permission for "Xcode Helper" the first
time you run this. Grant it via System Settings → Privacy & Security →
Accessibility, then re-run.
"""
from __future__ import annotations

import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.dom import minidom

try:
    from appium import webdriver
    from appium.options.common.base import AppiumOptions
except ImportError:
    print(
        "Missing dependency 'Appium-Python-Client'. Install with:\n"
        "    pip install -r requirements.txt",
        file=sys.stderr,
    )
    sys.exit(2)


APPIUM_URL = "http://127.0.0.1:4723"
BUNDLE_ID = "com.escher.v2-desktop-app-tauri"

# How long to wait after attaching before dumping — gives the WebView time
# to finish rendering if the app was just launched.
SETTLE_SECONDS = 10

NAME_LIKE_ATTRS = (
    "AXTitle",
    "title",
    "name",
    "label",
    "AXIdentifier",
    "identifier",
    "id",
    "AXValue",
    "value",
    "AXRoleDescription",
    "AXHelp",
    "AXPlaceholderValue",
    "placeholder",
)


def pretty(xml_text: str) -> str:
    return minidom.parseString(xml_text).toprettyxml(indent="  ")


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    results_dir = repo_root / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    before_png = results_dir / "accessibility_dump_before.png"
    after_png = results_dir / "accessibility_dump.png"
    full_xml = results_dir / "accessibility_dump.xml"
    window_xml = results_dir / "window_subtree.xml"

    options = AppiumOptions()
    options.set_capability("platformName", "mac")
    options.set_capability("appium:automationName", "mac2")
    options.set_capability("appium:bundleId", BUNDLE_ID)

    print(f"Connecting to Appium at {APPIUM_URL}")
    print(f"Targeting bundle:    {BUNDLE_ID}\n")

    try:
        driver = webdriver.Remote(APPIUM_URL, options=options)
    except Exception as exc:  # noqa: BLE001 — surface root cause to the user
        print(f"Failed to start Mac2 session: {exc}", file=sys.stderr)
        print(
            "\nCommon causes:\n"
            "  - Appium server is not running. Start it in another terminal: `appium`\n"
            "  - Xcode is not installed or not selected. Check: `xcode-select -p`\n"
            "  - Accessibility permission not granted to Xcode Helper "
            "(System Settings → Privacy & Security → Accessibility).\n",
            file=sys.stderr,
        )
        return 1

    try:
        driver.save_screenshot(str(before_png))
        print(f"Before screenshot   → {before_png}")

        print(f"Waiting {SETTLE_SECONDS}s for Escher to settle...")
        time.sleep(SETTLE_SECONDS)

        driver.save_screenshot(str(after_png))
        print(f"After screenshot    → {after_png}")

        page_source = driver.page_source
        full_xml.write_text(pretty(page_source), encoding="utf-8")
        print(f"Full AX tree        → {full_xml}")

        root = ET.fromstring(page_source)
        windows = root.findall(".//XCUIElementTypeWindow")
        if windows:
            wrapper = ET.Element("Windows")
            for w in windows:
                wrapper.append(w)
            window_xml.write_text(
                pretty(ET.tostring(wrapper, encoding="unicode")),
                encoding="utf-8",
            )
            print(f"Escher windows only → {window_xml}")

        print(f"\n=== Candidate selectors in Escher window(s) ===")
        seen = 0
        for window in windows:
            for el in window.iter():
                attrs = []
                for key in NAME_LIKE_ATTRS:
                    v = el.attrib.get(key)
                    if v and v.strip():
                        attrs.append(f'{key}="{v[:80]}"')
                if not attrs:
                    continue
                role = el.tag.replace("XCUIElementType", "")
                print(f"  <{role}>  " + "  ".join(attrs))
                seen += 1
        if seen == 0:
            print(
                "  (no named elements inside Escher window — see "
                "results/window_subtree.xml; if the window subtree is just an "
                "empty Group, the WebView is opaque to AX and we need to pivot "
                "to WebKit Remote Debugging.)"
            )
    finally:
        driver.quit()

    return 0


if __name__ == "__main__":
    sys.exit(main())
