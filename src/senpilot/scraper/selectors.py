"""FileMaker layout objects inspected on 2026-10-27; IDs are layout-specific.

These are not global field identifiers. Read matter fields BEFORE changing tabs.
Use semantic locators for category buttons, rows, and download dialogs.
"""

URL = "https://uarb.novascotia.ca/fmi/webd/UARB15"
DIRECT_INPUT = ".fm_object_254 .text"
DIRECT_EDITOR = ".fm_object_254 [contenteditable=true]"
MATTER_FIELDS = {
    "matter_number": ".fm_object_286 .text",
    "title": "[id='b0p0o290i0i0r1']",
    "matter_type": ".fm_object_287 .text",
    "status": ".fm_object_289 .text",
    "date_received": ".fm_object_292 .text",
    "decision_date": ".fm_object_294 .text",
    "outcome": ".fm_object_295 .text",
    "category": ".fm_object_298 .text",
}
OTHER_DOCUMENT_FIELDS = {
    "document_number": ".fm_object_201 .text",
    "title": ".fm_object_202 .text",
    "date": ".fm_object_203 .text",
    "security": ".fm_object_204 .text",
    "extension": ".fm_object_308 .text",
}
