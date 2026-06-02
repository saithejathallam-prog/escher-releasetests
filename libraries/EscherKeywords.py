"""Custom Robot Framework keyword library for the Escher test suite.

Why this exists
---------------
AppiumLibrary's `Click Element` fires an accessibility press
(XCUIElement.pressAction). Tauri's WebView reports the press as "succeeded"
but the web side never sees a `click` event, so in-WebView buttons don't fire
their handlers. The workaround is a real pointer click at the element's
on-screen coordinates — that goes through the OS event loop and reaches the
WebView.

Keywords exposed
----------------
* `Coordinate Click`         — click at absolute screen (x, y).
* `Coordinate Click Element` — coordinate-click an already-resolved WebElement,
                               with optional expected_title safety check.
* `Click At Element Center`  — same as above but resolves a Robot-style locator.
* `Wait For Response To Stabilize`
                             — block until the static-text content under a scope
                               is unchanged for `settle_seconds`. Useful for
                               waiting on streamed LLM responses.

The `expected_title` arg on the click keywords is the PROD safety net: if the
resolved element's title doesn't match exactly, the click is refused.
"""
from __future__ import annotations

import hashlib
import time
from typing import List, Optional

from robot.api import logger
from robot.api.deco import keyword, library
from robot.libraries.BuiltIn import BuiltIn
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.common.actions.pointer_input import PointerInput


@library(scope="SUITE")
class EscherKeywords:

    # ------------------------------------------------------------ helpers

    def _driver(self):
        appium = BuiltIn().get_library_instance("AppiumLibrary")
        return appium._current_application()

    def _find(self, locator: str):
        """Resolve a Robot-style locator (`strategy=value` or raw XPath) to an element."""
        driver = self._driver()
        if locator.startswith("/"):
            return driver.find_element("xpath", locator)
        if "=" not in locator:
            raise ValueError(
                f"Locator must include a `strategy=value` prefix or start "
                f"with `/` for raw XPath. Got: {locator!r}"
            )
        strategy, value = locator.split("=", 1)
        strategy_map = {
            "xpath": "xpath",
            "accessibility_id": "accessibility id",
            "id": "id",
            "name": "name",
            "class": "class name",
        }
        return driver.find_element(strategy_map.get(strategy, strategy), value)

    def _static_texts_under(self, scope_locator: str) -> List[str]:
        root = self._find(scope_locator)
        nodes = root.find_elements("xpath", ".//XCUIElementTypeStaticText")
        out: List[str] = []
        for n in nodes:
            v = n.get_attribute("value") or n.get_attribute("label") or ""
            if v:
                out.append(v)
        return out

    def _click_at(self, x: int, y: int) -> None:
        driver = self._driver()
        try:
            driver.execute_script("macos: click", {"x": x, "y": y})
            return
        except Exception as exc:  # noqa: BLE001 — fall back, then surface both
            logger.warn(
                f"`macos: click` failed at ({x},{y}): {exc}. "
                f"Falling back to W3C pointer actions."
            )
            try:
                mouse = PointerInput("mouse", "default-mouse")
                ab = ActionBuilder(driver, mouse=mouse)
                ab.pointer_action.move_to_location(x, y)
                ab.pointer_action.click()
                ab.perform()
            except Exception as inner:  # noqa: BLE001
                raise AssertionError(
                    f"Both `macos: click` and W3C pointer actions failed at "
                    f"({x},{y}). macos: {exc}. w3c: {inner}"
                )

    def _click_element_at_center(self, element, expected_title: Optional[str]) -> str:
        if expected_title is not None:
            actual = element.get_attribute("title") or ""
            if actual != expected_title:
                raise AssertionError(
                    f"Refusing to click: resolved element has title "
                    f"{actual!r}, expected {expected_title!r}. "
                    f"Fix the locator before retrying."
                )
        rect = element.rect  # {"x", "y", "width", "height"} in screen points
        if rect["width"] <= 0 or rect["height"] <= 0:
            raise AssertionError(
                f"Refusing to click on zero-size element. rect={rect}"
            )
        cx = int(rect["x"] + rect["width"] / 2)
        cy = int(rect["y"] + rect["height"] / 2)
        logger.info(
            f"Coordinate-clicking ({cx}, {cy}) — "
            f"title={element.get_attribute('title')!r} rect={rect}"
        )
        self._click_at(cx, cy)
        return f"{cx},{cy}"

    # ------------------------------------------------------------ visibility

    @keyword("Element Is Onscreen")
    def element_is_onscreen(self, element) -> bool:
        """True iff the element has positive size AND its top-left is at
        non-negative screen coordinates.

        XCUITest's `is_displayed` returns True for elements that exist with
        positive size regardless of where they sit — including off-screen
        panels (sign-out menus, hidden popovers, etc.) whose rect.x is a
        large negative number. We need a stricter "actually on screen" gate
        before coordinate-clicking, otherwise we can fire clicks into dead
        space.
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

    # ------------------------------------------------------------ click keywords

    @keyword("Coordinate Click")
    def coordinate_click(self, x, y) -> str:
        """Click at absolute screen coordinates via `macos: click`."""
        cx, cy = int(x), int(y)
        self._click_at(cx, cy)
        return f"{cx},{cy}"

    @keyword("Coordinate Click Element")
    def coordinate_click_element(self, element, expected_title: Optional[str] = None) -> str:
        """Coordinate-click an already-resolved WebElement.

        If `expected_title` is provided, refuses to click unless the element's
        `title` attribute matches it exactly. Returns `"x,y"` of the click.
        """
        return self._click_element_at_center(element, expected_title)

    @keyword("Click At Element Center")
    def click_at_element_center(self, locator: str, expected_title: Optional[str] = None) -> str:
        """Resolve `locator`, then coordinate-click the element's center.

        Use this for buttons inside Escher's Tauri WebView — AppiumLibrary's
        `Click Element` fires an AX press that the WebView ignores.

        If `expected_title` is provided, refuses to click unless the resolved
        element's `title` attribute matches it exactly. Returns `"x,y"` of the
        click for logging.
        """
        el = self._find(locator)
        return self._click_element_at_center(el, expected_title)

    # ------------------------------------------------------------ stability

    @keyword("Wait For Response To Stabilize")
    def wait_for_response_to_stabilize(
        self,
        scope_locator: str = "//XCUIElementTypeWebView",
        settle_seconds: float = 4.0,
        timeout_seconds: float = 180.0,
        poll_interval: float = 2.0,
    ) -> str:
        """Block until the static-text content under `scope_locator` is unchanged
        for `settle_seconds` consecutive seconds. Polls every `poll_interval`.
        Raises after `timeout_seconds`.
        """
        settle_seconds = float(settle_seconds)
        timeout_seconds = float(timeout_seconds)
        poll_interval = float(poll_interval)

        last_sig: Optional[str] = None
        last_change_at = time.monotonic()
        deadline = time.monotonic() + timeout_seconds

        while time.monotonic() < deadline:
            texts = self._static_texts_under(scope_locator)
            sig = hashlib.sha256("\n".join(texts).encode("utf-8")).hexdigest()
            now = time.monotonic()
            if sig != last_sig:
                last_sig = sig
                last_change_at = now
                logger.info(
                    f"Response still changing — {len(texts)} text nodes, "
                    f"sig={sig[:8]}."
                )
            else:
                stable_for = now - last_change_at
                if stable_for >= settle_seconds:
                    logger.info(
                        f"Response stable for {stable_for:.1f}s — "
                        f"{len(texts)} text nodes, sig={sig[:8]}."
                    )
                    return sig
            time.sleep(poll_interval)

        elapsed_since_last = time.monotonic() - last_change_at
        raise AssertionError(
            f"Response did not stabilize within {timeout_seconds}s "
            f"(last change was {elapsed_since_last:.1f}s ago)."
        )
