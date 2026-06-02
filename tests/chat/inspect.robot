*** Settings ***
Documentation    Send a CloudTrail remediation prompt to Escher and OBSERVE
...              whatever it renders. This test does not assume Escher will
...              respond with any particular shape — it might render a plan
...              with options, a clarifying question, plain text, an error,
...              or anything else. Whatever shows up, we capture a screenshot
...              and the accessibility tree so a human can review it.
...
...              Cleanup is best-effort: if a Cancel-style button happens to
...              be visible, we coordinate-click it so we don't leave an
...              action pending. We NEVER click Approve. If there's no Cancel
...              we just leave the screen alone.
...
...              The test only hard-fails on real infrastructure problems:
...              cannot attach to Escher, cannot find the chat input, or the
...              answer never stops streaming. Whatever Escher itself shows
...              is fine.

Library          OperatingSystem
Library          ../../libraries/EscherKeywords.py
Resource         ../../resources/common.resource

Suite Setup      Open Application    ${APPIUM_SERVER}    platformName=mac    automationName=mac2    bundleId=${ESCHER_BUNDLE_ID}    newCommandTimeout=300    noReset=true
Test Teardown    Defensive Plan Cancel


*** Test Cases ***
Observe Escher's response to a CloudTrail remediation prompt
    [Documentation]    Sends the prompt, waits for the answer to settle, and
    ...                records what Escher rendered. Passes regardless of
    ...                response shape.

    Wait Until Element Is Visible    ${NEW_CHAT_LINK}    ${DEFAULT_WAIT}
    Click Element                    ${NEW_CHAT_LINK}
    Wait Until Element Is Visible    ${PROMPT_INPUT}     ${DEFAULT_WAIT}
    Click Element                    ${PROMPT_INPUT}
    Input Text                       ${PROMPT_INPUT}     create a remediation plan for cloudtrail logging gaps
    Sleep    1s
    Click Element                    ${SEND_BUTTON}

    Wait For Answer To Finish

    Capture Observation    response_observed

    ${cancel_clicked}=    Try Click Visible Cancel
    IF    ${cancel_clicked}
        Sleep    3s
        Capture Observation    response_after_cancel
    END


*** Keywords ***
Capture Observation
    [Documentation]    Saves a screenshot plus the current window's AX tree to
    ...                `results/<base_name>.png` and `results/<base_name>.xml`.
    ...                Always succeeds — used to record exactly what Escher
    ...                rendered regardless of shape.
    [Arguments]    ${base_name}
    Capture Page Screenshot    ${base_name}.png
    ${src}=    Get Source
    Create File    ${OUTPUT_DIR}/${base_name}.xml    ${src}
    Log    Observation captured → ${base_name}.png + ${base_name}.xml    console=True

Try Click Visible Cancel
    [Documentation]    If an on-screen Cancel button is present, coordinate-click
    ...                it and return ${TRUE}. Otherwise return ${FALSE}. Never
    ...                fails — this is best-effort cleanup, not a contract.
    ${present}=    Run Keyword And Return Status
    ...    Page Should Contain Element    xpath=//XCUIElementTypeButton[@title="Cancel"]
    IF    not ${present}
        Log    No Cancel button in the AX tree — Escher's response had nothing to cancel.    console=True
        RETURN    ${FALSE}
    END
    @{els}=    Get WebElements    xpath=//XCUIElementTypeButton[@title="Cancel"]
    FOR    ${el}    IN    @{els}
        ${onscreen}=    Element Is Onscreen    ${el}
        IF    ${onscreen}
            ${coords}=    Coordinate Click Element    ${el}    expected_title=Cancel
            Log    Coordinate-clicked Cancel at ${coords}.    console=True
            RETURN    ${TRUE}
        END
    END
    Log    Cancel button(s) exist in the AX tree but none are on-screen — nothing to click.    console=True
    RETURN    ${FALSE}

Wait For Answer To Finish
    [Documentation]    Polls the page source length every 2s. When the length is
    ...                unchanged for 3 consecutive polls (~6s stable), assumes
    ...                streaming has stopped. Hard-fails after 180s if Escher
    ...                never settles (real bug, not a quirk of the response).
    ${prev}=     Set Variable    ${-1}
    ${stable}=   Set Variable    ${0}
    FOR    ${i}    IN RANGE    90
        ${src}=    Get Source
        ${len}=    Get Length    ${src}
        IF    ${len} == ${prev}
            ${stable}=    Evaluate    ${stable} + 1
        ELSE
            ${stable}=    Set Variable    ${0}
        END
        ${prev}=    Set Variable    ${len}
        IF    ${stable} >= 3    RETURN
        Sleep    2s
    END
    Fail    Answer never stopped changing — Escher may be stuck/streaming.

Defensive Plan Cancel
    [Documentation]    Teardown safety net: try to click any on-screen Cancel,
    ...                ignore failures. Does NOT close Escher.
    Run Keyword And Ignore Error    Try Click Visible Cancel
