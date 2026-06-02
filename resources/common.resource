*** Settings ***
Documentation    Shared variables and keywords for the Escher test suite.
Library          AppiumLibrary

*** Variables ***
# --- Appium / Mac2 session ---
${APPIUM_SERVER}            http://127.0.0.1:4723
${PLATFORM_NAME}            mac
${AUTOMATION_NAME}          mac2

# Bundle IDs of the three Escher builds installed under /Applications.
# Suite currently targets Staging; switch ${ESCHER_BUNDLE_ID} to point at a different env.
${ESCHER_BUNDLE_ID_PROD}        com.escher.v2-desktop-app-tauri
${ESCHER_BUNDLE_ID_STAGING}     com.escher-staging.v2-desktop-app-tauri
${ESCHER_BUNDLE_ID_DEV}         com.escher-dev.v2-desktop-app-tauri
${ESCHER_BUNDLE_ID}             ${ESCHER_BUNDLE_ID_PROD}

# --- Timeouts ---
${APP_LAUNCH_TIMEOUT}       30s
${LLM_RESPONSE_TIMEOUT}     90s
${DEFAULT_WAIT}             10s

# --- Selectors ---
# Mac2 driver: match by AX role + attributes via XPath. We use XPath rather
# than `name=` because AppiumLibrary's `name=` strategy is ambiguous on Mac2.
# All selectors below are confirmed against `results/window_subtree.xml`
# (regenerate with scripts/probe_accessibility_tree.py if the app UI changes).

# Active AWS profile in Escher. The Send button is anchored on this — if you
# switch profiles in Escher you must update this AND the test's precondition.
${ACTIVE_PROFILE_NAME}      dataplane

# Sidebar nav.
${NEW_CHAT_LINK}            xpath=//XCUIElementTypeButton[@title="New Chat"]

# Chat input: there is only one TextView in the new-chat window, so the role
# alone is unique enough. Distinguishable by its placeholder if it isn't.
${PROMPT_INPUT}             xpath=//XCUIElementTypeTextView

# The active-profile button shows the profile name as its title.
${ACTIVE_PROFILE_BUTTON}    xpath=//XCUIElementTypeButton[@title="${ACTIVE_PROFILE_NAME}"]

# Send button: title-less, identifier-less, ~42x43 px button. Structurally,
# it's the 2nd button that follows the input TextView's container Group (the
# 1st following-sibling button is the active-profile selector). This anchor
# is profile-agnostic — works regardless of which AWS profile is selected.
${SEND_BUTTON}              xpath=//XCUIElementTypeTextView/parent::*/following-sibling::XCUIElementTypeButton[2]

# --- Domain patterns ---
# EC2 instance IDs: `i-` + 8 hex chars (legacy) OR `i-` + 17 hex chars (current).
${EC2_INSTANCE_PATTERN}     i-[0-9a-f]{8}(?:[0-9a-f]{9})?

*** Keywords ***
Launch Escher
    [Documentation]    Open Escher-Staging via Appium Mac2 driver.
    Open Application    ${APPIUM_SERVER}
    ...    platformName=${PLATFORM_NAME}
    ...    automationName=${AUTOMATION_NAME}
    ...    bundleId=${ESCHER_BUNDLE_ID}
    Set Appium Timeout    ${DEFAULT_WAIT}

Close Escher
    Close Application
