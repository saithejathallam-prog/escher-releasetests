*** Settings ***
Documentation    Smoke: a fresh chat asking Escher to list EC2 instances should
...              return a response that contains at least one valid EC2 instance ID.
...
...              Precondition: Escher's active AWS profile is `dataplane`. The test
...              reads this from `${ACTIVE_PROFILE_NAME}` in common.resource — if
...              the active profile changes in Escher, update both that variable
...              and this docstring.

Resource         ../../resources/common.resource

Test Setup       Launch Escher
Test Teardown    Close Escher

*** Test Cases ***
New chat returns EC2 instances from the dataplane profile
    [Tags]    chat    aws    ec2    smoke

    Wait Until Element Is Visible    ${NEW_CHAT_LINK}    ${APP_LAUNCH_TIMEOUT}
    Click Element                    ${NEW_CHAT_LINK}

    Wait Until Element Is Visible    ${PROMPT_INPUT}    ${DEFAULT_WAIT}
    Input Text                       ${PROMPT_INPUT}    list my ec2 instances

    # The send button becomes enabled once the input has text. AppiumLibrary 3.x
    # has no `Wait Until Element Is Enabled` keyword, so poll the assertion.
    Wait Until Keyword Succeeds      ${DEFAULT_WAIT}    0.5s
    ...    Element Should Be Enabled    ${SEND_BUTTON}
    Click Element                    ${SEND_BUTTON}

    # Escher's response is LLM-generated and streamed; polling Get Source for
    # the EC2 pattern is more robust than trying to scope to a "response" element.
    Wait Until Keyword Succeeds      ${LLM_RESPONSE_TIMEOUT}    3s
    ...    Response Should Mention An EC2 Instance

*** Keywords ***
Response Should Mention An EC2 Instance
    ${source}=    Get Source
    Should Match Regexp    ${source}    ${EC2_INSTANCE_PATTERN}
    ...    msg=No EC2 instance ID pattern found in the current window source.
