# E2E Test Automation for Escher — Approach Comparison

**Author:** Sai Theja Thallam
**Date:** 2026-06-01
**Status:** Draft for senior review
**Audience:** Engineering leadership, QA stakeholders

---

## Executive Summary

Escher engineering currently maintains an end-to-end test suite that exercises the Gateway API directly via Cognito-authenticated requests (`escher-cloudops-ai/v2-e2e-test-suite-full-lab`). A separate effort, `escher-releasetests`, is in early development and targets the Tauri-based macOS desktop application. The two suites test **different layers of the platform** and are not duplicative. The reference suite's own strategy document explicitly identifies the desktop client as a "zero coverage" area; the new work is positioned to address that gap. This document compares the two approaches in terms of scope, stack, coverage, and trade-offs, and lists the open questions for senior validation.

---

## Approach A — Existing Reference Suite

**Repository:** `github.com/escher-cloudops-ai/v2-e2e-test-suite-full-lab`

| Attribute | Detail |
|---|---|
| Layer tested | Gateway API (server-side) |
| Language / runtime | TypeScript on Node |
| Runner | Vitest |
| Authentication | AWS Cognito SDK |
| Validation | Structural checks plus Claude (Anthropic SDK) for semantic validation of LLM responses |
| Test authoring | YAML scenarios — each file is a `prompt:` + `expected:` declaration |
| Reporting | Markdown, JSON, DOCX (executive-facing) |
| CI | GitHub Actions, weekly schedule; Slack notification |
| Maturity | Mature; in production; 360+ prompts per project README |

**Strengths**

- Fast per-test execution; deterministic infrastructure.
- Broad scenario coverage at low marginal cost (one YAML file per scenario).
- Handles non-deterministic LLM output through Claude semantic validation.
- Author-friendly: non-engineers can add scenarios by editing YAML.
- Strong reporting suitable for executive review.

**Limitations (acknowledged in the project's own `E2E-STRATEGY.md`)**

- Does not open the desktop application.
- Does not exercise the Tauri client-side execution pipeline.
- Does not validate UI rendering, button click handlers, or layout.
- Quoting the strategy document directly: *"the critical client-side execution pipeline — where scripts actually run on the user's machine — has zero test coverage."*

---

## Approach B — Desktop UI Automation (`escher-releasetests`)

**Repository:** `/Users/saithejathallam/escher-releasetests` (local; not yet published)

| Attribute | Detail |
|---|---|
| Layer tested | Tauri macOS desktop application (user-visible UI) |
| Language / runtime | Python 3.11 |
| Test framework | Robot Framework 7 |
| UI driver | AppiumLibrary on top of Appium Server with the Mac2 driver (XCTest / macOS accessibility) |
| Native prerequisites | Xcode, Appium 3, `appium-mac2-driver` |
| Test authoring | Robot Framework `.robot` files, keyword-driven |
| Validation | Accessibility-tree queries, on-screen coordinate clicks, before/after screenshots, screen XML dumps |
| Reporting | Robot Framework HTML/XML reports; screenshot artifacts |
| CI | Not yet integrated; requires a GUI-capable host with Xcode |
| Maturity | Early-stage; foundations in place |

**Strengths**

- Validates the end-to-end user experience including the desktop shell.
- Catches client-side issues invisible to the API-level suite, including:
  - In-WebView button click handlers that do not respond to standard accessibility press events (resolved here via the `macos: click` coordinate workaround).
  - Plan rendering, action-button presence, and the dismiss flow.
  - Streaming completion at the UI layer (rather than just at the API layer).
- Directly addresses the gap that the reference repo's strategy document calls out.

**Limitations**

- Higher per-test latency: a single scenario takes seconds to minutes (app attach, streaming wait, render settle).
- More environmental dependencies (Xcode, Appium Server, app installations).
- Selectors are tied to the accessibility tree, which can shift with UI redesigns.
- Lower CI feasibility — requires a macOS GUI host; not trivially containerizable.
- Tauri WebView buttons require a coordinate-click workaround; this is now solved in the framework but is a maintenance consideration.

---

## Coverage Comparison

| Concern | Reference (A) | Desktop UI (B) |
|---|:---:|:---:|
| Server prompt classification | Yes | Indirect |
| Server response content | Yes | Indirect |
| Cognito authentication | Yes | Uses the running app's session |
| Tauri IPC bridge | No | Yes |
| Desktop window rendering | No | Yes |
| Button click handlers inside the WebView | No | Yes |
| Plan UI: action buttons appear | No | Yes |
| Plan UI: option selection (radio buttons) | No | Not yet implemented |
| Approve / Cancel safety behavior | No | Yes |
| Streaming completion at the UI layer | No | Yes |
| Anonymization round-trip | No (per strategy doc) | Scope; not yet implemented |
| Multi-step execution at the client | No (per strategy doc) | Scope; not yet implemented |

---

## Trade-off Comparison

| Dimension | Reference (A) | Desktop UI (B) |
|---|---|---|
| Per-test latency | Seconds | 30 seconds to several minutes |
| Determinism | High | Moderate (UI render + Mac2 driver stability) |
| Scenario authoring | YAML — non-engineer friendly | `.robot` — readable but engineer-oriented |
| Maintenance cost | Low — UI changes do not break tests | Moderate — UI redesigns may require selector updates |
| Catches UI-only defects | No | Yes |
| CI feasibility | High (no display required) | Lower (requires GUI host + Xcode) |
| Existing investment | Mature, in production | Early-stage |
| Estimated effort to a first complete smoke set | N/A — exists | Two to four weeks |

---

## Open Questions for Senior Validation

1. **Goal alignment.** Is the primary objective to validate the **platform** (Gateway responses) or the **product** (UI behavior the customer experiences)? The reference suite addresses the former; this work addresses the latter.
2. **Closing the documented gap.** The strategy document names the desktop client as a P0 coverage gap. Is the intended path to fill it via desktop UI automation (this work), via direct Tauri IPC unit tests, or via some combination?
3. **Investment posture.** Should both layers be maintained as complements, or is one of the two the strategic direction? The two are not redundant — they catch different classes of defect.
4. **Authoring model.** If desktop UI automation continues, should it adopt the reference suite's **YAML scenario** authoring model so non-engineers can add scenarios uniformly across both suites?
5. **Semantic validation reuse.** Should the desktop suite reuse the reference suite's **Claude-based validator** for assertions over LLM-generated content, to keep validation behavior consistent across layers?

---

## Considerations for Path Forward

Three viable directions, in order of investment:

1. **Adopt the desktop UI suite as a complement to the existing API suite.**
   - Maintain both. API suite continues to cover Gateway behavior; desktop suite closes the documented client-side gap.
   - Recommend adopting two patterns from the reference suite to keep the projects consistent:
     - **YAML scenario authoring** — one file per scenario, `prompt` + `expected`.
     - **Claude semantic validation** — for non-deterministic content assertions.
2. **Pivot to API-only coverage.**
   - Drop the desktop UI work. Re-implement nothing on the UI side.
   - Net effect: the gap identified in the strategy document remains unaddressed.
3. **Adopt the desktop UI suite and additionally test the Tauri IPC layer directly.**
   - Highest coverage at highest investment.
   - Tauri IPC commands (`execute_python_script`, `execution-event`) are testable without UI; doing so reduces reliance on Mac2-driver stability for those layers.

The first option is the most aligned with the reference suite's stated coverage strategy and reuses the existing investment in `escher-releasetests`. The decision belongs to engineering leadership.

---

*End of document.*
