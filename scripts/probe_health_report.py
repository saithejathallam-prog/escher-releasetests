#!/usr/bin/env python3
"""Probe Escher's Monthly Executive Cloud Health Report flow.

One-shot script. We drive Escher through the full flow once so we can
inspect the accessibility tree at the two interesting moments:

  1. Right after Turn 1 streams — chat shows text plus three action
     buttons (Cancel / Save / Accept).
  2. After Accept is clicked and the ~9-minute analysis completes —
     the right-side canvas should be open and the chat should have
     the final report inline.

From the second dump we will discover the canvas's accessibility-tree
shape so we can design scoped selectors for the actual test.

Safety
------
Clicking Accept here is intentionally allowed because the user has
confirmed the action is READ-ONLY (Escher reads cloud state and writes
a report; no AWS resources are provisioned or mutated). Do not copy this
pattern to other prompts without explicit confirmation that Accept is
safe for that prompt.

Prerequisites
-------------
- Appium server running on :4723 (`appium`).
- Escher running and signed in.
- The desired AWS profile is already selected in Escher.

Outputs (under `results/`)
--------------------------
  health_report_turn1_buttons.png   screenshot after the 3 buttons appear
  health_report_turn1_buttons.xml   AX tree at that moment
  health_report_final.png           screenshot after analysis completes
  health_report_final.xml           AX tree at that moment

If the probe fails, a `health_report_failure.*` pair is saved for
diagnostics. Escher is left running in all cases.
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
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.common.actions.pointer_input import PointerInput

APPIUM_URL = "http://127.0.0.1:4723"
# Pointing at Escher DEV for this probe run. The three bundle IDs are:
#   PROD:    com.escher.v2-desktop-app-tauri
#   STAGING: com.escher-staging.v2-desktop-app-tauri
#   DEV:     com.escher-dev.v2-desktop-app-tauri
BUNDLE_ID = "com.escher-dev.v2-desktop-app-tauri"

PROMPT = (
    "Generate a monthly executive cloud health report — "
    "cost / top risks / compliance gaps / waste / and top 3 recommendations"
)

# Timing
TURN1_TIMEOUT = 90.0           # wait for the 3 buttons to appear after Send
POST_APPROVE_TIMEOUT = 720.0   # 12 minutes max for the analysis
STABILITY_REQUIRED = 30.0      # source must stay unchanged this long to be "done"
POLL_INTERVAL = 10.0


def macos_coordinate_click(driver, x: int, y: int) -> None:
    try:
        driver.execute_script("macos: click", {"x": x, "y": y})
        return
    except Exception as exc:  # noqa: BLE001
        print(f"  macos: click failed at ({x},{y}): {exc}. Falling back to W3C.")
        mouse = PointerInput("mouse", "default-mouse")
        ab = ActionBuilder(driver, mouse=mouse)
        ab.pointer_action.move_to_location(x, y)
        ab.pointer_action.click()
        ab.perform()


def scroll_element_into_view(driver, element, max_attempts: int = 6) -> bool:
    """Scroll the element into the visible viewport before clicking.

    Tauri WebView elements report AX rects in document coordinates. When the
    WebView has been scrolled past an element, its AX-reported y is outside
    the visible viewport and a `macos: click` at that y lands in dead space.

    Mac2 has no scrollToVisible. We send `macos: scroll` events at a point
    inside the chat scroll area, in the direction needed to bring the
    element's y into the visible viewport (~ y=33..1050 for the Escher
    window). Re-queries the element's rect after each scroll and stops as
    soon as it lands in-bounds, or after `max_attempts`.

    Returns True if the element is in viewport at exit.
    """
    # Heuristic viewport bounds — adequate for an Escher window of typical
    # size. We aim for the button to sit a bit above the bottom edge.
    viewport_top = 100
    viewport_bottom = 950
    # Where to deliver the scroll event (somewhere in the chat content area).
    scroll_anchor_x, scroll_anchor_y = 1200, 500
    # How far each scroll step moves content.
    step = 300

    for attempt in range(max_attempts):
        try:
            rect = element.rect
        except Exception as exc:  # noqa: BLE001
            print(f"  could not read element rect on attempt {attempt}: {exc}")
            return False
        y = rect.get("y", 0)
        if viewport_top <= y <= viewport_bottom - rect.get("height", 0):
            print(f"  element rect now in-viewport (y={y}); done after {attempt} scroll(s)")
            return True
        # If element is below viewport, scroll content UP (positive deltaY in
        # macOS native semantics scrolls content down, so we use negative);
        # if above, scroll DOWN (positive deltaY). Empirically the sign on
        # `macos: scroll` matches "content delta" — we'll try one direction
        # and confirm with rect re-read.
        delta_y = -step if y > viewport_bottom else step
        print(f"  attempt {attempt}: element at y={y}, scrolling deltaY={delta_y}")
        try:
            driver.execute_script(
                "macos: scroll",
                {"x": scroll_anchor_x, "y": scroll_anchor_y,
                 "deltaX": 0, "deltaY": delta_y},
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  WARNING: scroll attempt {attempt} failed: {exc}")
            return False
        time.sleep(0.4)
    print(f"  WARNING: scrolled {max_attempts} times and element still off-viewport")
    return False


def click_element_by_coordinates(driver, element, expected_title: str) -> None:
    actual = element.get_attribute("title") or ""
    if actual != expected_title:
        raise AssertionError(
            f"Refusing to click — expected title {expected_title!r}, got {actual!r}"
        )
    rect = element.rect
    if rect["width"] <= 0 or rect["height"] <= 0:
        raise AssertionError(f"Refusing to click zero-size element. rect={rect}")
    cx = int(rect["x"] + rect["width"] / 2)
    cy = int(rect["y"] + rect["height"] / 2)
    print(f"  coordinate-clicking {expected_title!r} at ({cx},{cy}) rect={rect}")
    macos_coordinate_click(driver, cx, cy)


def _is_onscreen(element) -> bool:
    """True iff the element has positive size AND non-negative position.

    Tauri's accessibility tree contains stashed copies of clickable elements
    at large negative coordinates (popover state, hidden menus, etc.).
    Mac2's `find_element` happily returns these — and a `macos: click` at
    a negative coordinate is a no-op. Always filter before clicking.
    """
    try:
        rect = element.rect
    except Exception:  # noqa: BLE001
        return False
    return (
        rect.get("width", 0) > 0
        and rect.get("height", 0) > 0
        and rect.get("x", -1) >= 0
        and rect.get("y", -1) >= 0
    )


def wait_for_onscreen_element(driver, xpath: str, timeout_seconds: float):
    """Wait until at least one element matching `xpath` is actually on-screen."""
    deadline = time.monotonic() + timeout_seconds
    last_state = "no matches yet"
    while time.monotonic() < deadline:
        try:
            candidates = driver.find_elements("xpath", xpath)
        except Exception as exc:  # noqa: BLE001
            last_state = f"find_elements raised: {exc}"
            time.sleep(2)
            continue
        if not candidates:
            last_state = "no matches"
        else:
            for el in candidates:
                if _is_onscreen(el):
                    return el
            last_state = (
                f"found {len(candidates)} match(es) but none on-screen "
                "(stashed off-screen at negative coords)"
            )
        time.sleep(2)
    raise TimeoutError(
        f"No on-screen element matched {xpath!r} within {timeout_seconds}s. "
        f"Last state: {last_state}"
    )


def page_source_signature(driver) -> tuple[str, int]:
    src = driver.page_source
    return hashlib.sha256(src.encode("utf-8")).hexdigest(), len(src)


def wait_for_source_to_stabilize(driver, timeout_seconds: float,
                                 stability_seconds: float, poll: float) -> None:
    started = time.monotonic()
    deadline = started + timeout_seconds
    last_sig = None
    last_change = time.monotonic()
    while time.monotonic() < deadline:
        sig, src_len = page_source_signature(driver)
        now = time.monotonic()
        elapsed = int(now - started)
        if sig != last_sig:
            last_sig = sig
            last_change = now
            print(f"  [{elapsed:>4}s] source changing — len={src_len:,}, sig={sig[:8]}")
        else:
            stable_for = now - last_change
            if stable_for >= stability_seconds:
                print(f"  [{elapsed:>4}s] source stable for {stable_for:.0f}s — analysis done")
                return
            print(f"  [{elapsed:>4}s] stable for {stable_for:.0f}s of {stability_seconds:.0f}s needed")
        time.sleep(poll)
    raise TimeoutError(
        f"Source never stabilised within {timeout_seconds}s — analysis may be stuck."
    )


def dump(driver, results_dir: Path, base: str) -> None:
    png = results_dir / f"{base}.png"
    xml = results_dir / f"{base}.xml"
    driver.save_screenshot(str(png))
    pretty = minidom.parseString(driver.page_source).toprettyxml(indent="  ")
    xml.write_text(pretty, encoding="utf-8")
    print(f"  dumped → {png.name}, {xml.name}")


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    results_dir = repo_root / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    options = AppiumOptions()
    options.set_capability("platformName", "mac")
    options.set_capability("appium:automationName", "mac2")
    options.set_capability("appium:bundleId", BUNDLE_ID)
    options.set_capability("appium:newCommandTimeout", 900)  # 15 minutes
    options.set_capability("appium:noReset", True)           # attach, don't quit

    print(f"Attaching to Escher PROD ({BUNDLE_ID}) at {APPIUM_URL}")
    driver = webdriver.Remote(APPIUM_URL, options=options)
    driver.implicitly_wait(5)

    try:
        print("\n--- Setup ---")
        print("Clicking New Chat")
        wait_for_onscreen_element(driver, '//XCUIElementTypeButton[@title="New Chat"]', 30).click()
        time.sleep(2)

        print("Focusing the prompt input")
        prompt = wait_for_onscreen_element(driver, "//XCUIElementTypeTextView", 30)
        prompt.click()

        print("Typing the prompt")
        prompt.send_keys(PROMPT)
        time.sleep(1)

        print("Clicking Send")
        send = driver.find_element(
            "xpath",
            "//XCUIElementTypeTextView/parent::*/following-sibling::XCUIElementTypeButton[2]",
        )
        send.click()

        print(f"\n--- Turn 1: waiting up to {int(TURN1_TIMEOUT)}s for the 3 action buttons ---")
        approve = wait_for_onscreen_element(
            driver, '//XCUIElementTypeButton[@title="Accept"]', TURN1_TIMEOUT
        )
        print("  Accept button visible")
        for title in ("Cancel", "Save Plan"):
            candidates = driver.find_elements(
                "xpath", f'//XCUIElementTypeButton[@title="{title}"]'
            )
            onscreen = [el for el in candidates if _is_onscreen(el)]
            if onscreen:
                print(f"  {title} button on-screen ({len(candidates)} total, {len(onscreen)} visible)")
            elif candidates:
                print(f"  WARNING: {title} button exists ({len(candidates)}) but all are off-screen")
            else:
                print(f"  WARNING: {title} button NOT found at all")

        dump(driver, results_dir, "health_report_turn1_buttons")

        print("\n--- Accept ---")
        print("Scrolling Accept into the visible viewport")
        scroll_element_into_view(driver, approve)

        # Re-resolve the Accept button after the scroll. Its screen y will
        # have changed; using the pre-scroll element's cached rect would
        # click at the wrong coordinate again.
        approve = wait_for_onscreen_element(
            driver, '//XCUIElementTypeButton[@title="Accept"]', 10
        )
        print("Coordinate-clicking Accept (safety check: title must equal 'Accept')")
        click_element_by_coordinates(driver, approve, expected_title="Accept")

        print(f"\n--- Turn 2: waiting up to {int(POST_APPROVE_TIMEOUT/60)} minutes for analysis to complete ---")
        print(f"  Polling page source every {POLL_INTERVAL:.0f}s; \"done\" = unchanged for {STABILITY_REQUIRED:.0f}s")
        wait_for_source_to_stabilize(
            driver,
            timeout_seconds=POST_APPROVE_TIMEOUT,
            stability_seconds=STABILITY_REQUIRED,
            poll=POLL_INTERVAL,
        )

        dump(driver, results_dir, "health_report_final")

        print("\n--- Probe complete ---")
        print("Outputs in results/:")
        print("  health_report_turn1_buttons.png  health_report_turn1_buttons.xml")
        print("  health_report_final.png          health_report_final.xml")
        print("\nEscher left running. Inspect the dumps; the canvas should be open in Escher too.")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"\nPROBE FAILED: {exc}", file=sys.stderr)
        try:
            dump(driver, results_dir, "health_report_failure")
            print("Diagnostic dump saved to results/health_report_failure.*", file=sys.stderr)
        except Exception:  # noqa: BLE001
            pass
        return 1
    finally:
        # End the Appium session. With noReset=true, Escher itself is left
        # running so the user can inspect the canvas by hand if they want.
        driver.quit()


if __name__ == "__main__":
    sys.exit(main())
