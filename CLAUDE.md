# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project purpose

This repository contains an **automated test suite for Escher**, a macOS desktop application. Escher is an AI agent for cloud operations that connects to AWS and Azure accounts in read-only mode and answers natural-language questions about infrastructure (cost, security, etc.). This repo does **not** contain Escher's source — it contains tests that drive Escher as an external system.

- Escher user docs: https://escher-docs.vercel.app/user/get-started/introduction
- Escher is built on Tauri v2 (https://v2.tauri.app/) — a Rust-backed shell hosting a webview frontend. Tests therefore target a native macOS app, not a browser.

## Status

Scaffolded with the first scenario in draft form (`tests/chat/ec2_list.robot`). The draft has `TODO`s for app-side details (bundle ID, accessibility selectors, submit gesture) that need to be confirmed against the real Escher-Staging build before the suite can actually run. The user (`saitheja.thallam@tessell.com`) supplies scenarios and test cases — do not invent test scenarios or assume coverage requirements without being given them.

## Layout

```
escher-releasetests/
├── CLAUDE.md
├── requirements.txt
├── resources/
│   └── common.resource          # Shared variables (selectors, timeouts) and session keywords
├── tests/
│   └── chat/
│       └── ec2_list.robot       # First scenario: EC2 list via dataplane profile
├── scripts/
│   └── probe_accessibility_tree.py   # One-shot tool to dump Escher's AX tree
└── results/                     # Robot Framework output + probe artifacts (gitignored)
```

### Escher app bundles installed locally

| Build | Path | Bundle ID |
|---|---|---|
| Prod | `/Applications/Escher.app` | `com.escher.v2-desktop-app-tauri` |
| Staging | `/Applications/Escher-Staging.app` | `com.escher-staging.v2-desktop-app-tauri` |
| Dev | `/Applications/Escher-Dev.app` | `com.escher-dev.v2-desktop-app-tauri` |

The suite targets Staging via `${ESCHER_BUNDLE_ID}` in `resources/common.resource`.

### Discovering selectors

`scripts/probe_accessibility_tree.py` opens a Mac2 session against Escher-Staging and writes the full accessibility tree to `results/accessibility_dump.xml` plus a screenshot to `results/accessibility_dump.png`. It also prints a stdout summary of every element with a name, identifier, or value — those are the candidate selectors to plug into `common.resource`. Run it whenever the app's UI changes meaningfully and we need to refresh selectors.

When adding Python keyword libraries (e.g., for WebKit remote-debugging DOM access), put them under `libraries/` and `Library    libraries/Foo.py` from a `.resource` file.

## Running the suite

**One-time setup** (host machine):
```
# Python deps
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Appium server + Mac2 driver (Node.js required)
npm install -g appium
appium driver install mac2
```

**Each run:**
```
# Terminal 1 — start Appium
appium

# Terminal 2 — run the suite (or a single test)
robot --outputdir results tests/
robot --outputdir results tests/chat/ec2_list.robot
```

Robot Framework writes `log.html`, `report.html`, and `output.xml` into `results/`.

## Stack

| Layer | Choice |
|---|---|
| Language | Python 3.11+ |
| Test framework | **Robot Framework** (keyword-driven, `.robot` files) |
| UI keywords | `robotframework-appiumlibrary` |
| Native UI driver | Appium Server + **Mac2 driver** (XCTest / macOS accessibility) |
| WebView DOM access | Custom Python keywords wrapping Apple's WebKit remote-debugging protocol (see caveat below) |
| Reporting | Robot Framework's built-in HTML / XML reports |
| Screenshots / visual diff | Pillow if/when needed |

### Why Robot Framework on macOS (and not `tauri-driver`)

Tauri's docs recommend WebdriverIO with `tauri-driver`, but **`tauri-driver` does not support macOS** — Apple does not ship a WKWebView WebDriver. All UI driving therefore goes through Appium's Mac2 driver, which talks to the app via XCTest/accessibility. Robot Framework sits on top of that via AppiumLibrary.

### Hybrid assertion model

Tests are expected to mix native macOS UI assertions (driven through Appium Mac2) with **DOM-level assertions inside Escher's WKWebView**. This is non-trivial on macOS — Appium's Mac2 driver does not expose a WebView context switch the way the iOS/Android drivers do. The committed path is a small set of **custom Python keywords** that attach to Escher's WKWebView over Apple's WebKit remote-debugging protocol and expose `Get Element Text`-style operations to `.robot` files. If the Escher team is open to it, a longer-term option is a test-only Tauri `invoke` command that returns DOM state directly. Validate the DOM-access mechanism on a single representative scenario before propagating the pattern across the whole suite.

### Authoring conventions

- Scenarios live in `.robot` files and read like English (`Click Button    Run Query`, `Element Text Should Be    ...    ...`).
- Anything that needs real logic (loops, parsing, LLM-output structural checks) goes into Python keyword libraries, not embedded in `.robot` files. Keep `.robot` files declarative.

## Things to keep in mind when this codebase grows

- **Tauri on macOS is not a browser.** Standard web-only drivers (plain Playwright/Selenium pointed at a URL) will not attach. Driving a Tauri app generally requires either WebDriver via `tauri-driver` + `webdriver` (the Tauri-supported path) or macOS-native UI automation (Appium with the Mac2 driver, or AppleScript/`osascript`). Pick the approach once with the user — don't silently switch later.
- **Read-only cloud credentials.** Escher connects to real AWS/Azure accounts. Any test that exercises cloud-connected flows needs to be explicit about which account/credentials it uses and must respect Escher's read-only posture. Never introduce test setup that would mutate cloud resources to make an assertion pass.
- **Natural-language outputs.** Escher's answers are LLM-generated and non-deterministic. Assertions should target structural/behavioral signals (a response arrived, the right tool/console was invoked, a chart rendered, a citation links to the right resource) rather than exact answer text, unless the user explicitly asks for string matching.

