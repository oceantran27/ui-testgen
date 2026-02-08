from app.api.v1.endpoints.analyze import _extract_and_minify_json

cases = {
    "labeled_fence": (
        """
        ## Thinking Process
        Some analysis here...
        
        ## Final JSON
        ```json
        {
          "user_intents": [
            {"intent_name": "Log in", "related_elements": ["Username", "Password", "Login"], "type": "Action"}
          ]
        }
        ```
        """,
        '{"user_intents":[{"intent_name":"Log in","related_elements":["Username","Password","Login"],"type":"Action"}]}'
    ),
    "generic_fence": (
        """
        Thoughts...
        ```
        {
          // comment to remove
          "user_intents": [
            {"intent_name": "Search", "related_elements": ["Search Bar", "Go"], "type": "Action",}
          ],
        }
        ```
        """,
        '{"user_intents":[{"intent_name":"Search","related_elements":["Search Bar","Go"],"type":"Action"}]}'
    ),
    "inline_no_fence": (
        'Thinking... Final JSON: {"user_intents": [{"intent_name": "View Cart", "related_elements": ["Cart Icon"], "type": "Navigation"}]}',
        '{"user_intents":[{"intent_name":"View Cart","related_elements":["Cart Icon"],"type":"Navigation"}]}'
    ),
}

for name, (inp, expected) in cases.items():
    out = _extract_and_minify_json(inp)
    print(name, "=>", out)
    assert out == expected, f"Case {name} failed: {out} != {expected}"

print("All cases passed.")
