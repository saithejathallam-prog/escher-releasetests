*** Settings ***
Documentation    S4 live-data checks, built on the proven EC2 pattern.
Resource         ../../resources/common.resource
Suite Setup      Open Application    ${APPIUM_SERVER}    platformName=mac    automationName=mac2    bundleId=${ESCHER_BUNDLE_ID}
Suite Teardown   Close Application

*** Variables ***
${S3_BUCKET_PATTERN}     (?i)(bucket|s3://)
${IAM_USER_PATTERN}      (?i)(iam|arn:aws:iam|user)
${CURRENCY_PATTERN}      [$€£]\s?[0-9,]+

*** Test Cases ***
List S3 buckets
    Ask Escher A Question    list my s3 buckets
    Response Should Contain Pattern    ${S3_BUCKET_PATTERN}

List IAM users
    Ask Escher A Question    list all iam users
    Response Should Contain Pattern    ${IAM_USER_PATTERN}

Current monthly run rate
    Ask Escher A Question    what is our current monthly run rate?
    Response Should Contain Pattern    ${CURRENCY_PATTERN}

*** Keywords ***
Ask Escher A Question
    [Arguments]    ${prompt}
    Wait Until Element Is Visible    ${NEW_CHAT_LINK}    ${DEFAULT_WAIT}
    Click Element                    ${NEW_CHAT_LINK}
    Wait Until Element Is Visible    ${PROMPT_INPUT}     ${DEFAULT_WAIT}
    Click Element                    ${PROMPT_INPUT}
    Input Text                       ${PROMPT_INPUT}     ${prompt}
    Sleep                            1s
    Click Element                    ${SEND_BUTTON}

Response Should Contain Pattern
    [Arguments]    ${pattern}
    Wait Until Keyword Succeeds      ${LLM_RESPONSE_TIMEOUT}    3s    Source Matches    ${pattern}

Source Matches
    [Arguments]    ${pattern}
    ${src}=    Get Source
    Should Match Regexp    ${src}    ${pattern}
