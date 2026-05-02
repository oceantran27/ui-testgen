import json
import unittest

from app.core.exceptions import AIProcessingError
from app.services.ui_hierarchy_payload import (
    collect_verbatim_literals_from_dump,
    count_control_nodes,
    parse_ui_hierarchy_payload,
    ui_hierarchy_to_minified_json,
)

MINIMAL = """
{
  "schema_version": "ui-hierarchy-v1",
  "overview": {
    "page_summary": "Test page",
    "business_intent": "",
    "interactive_element_count": 1
  },
  "root": {
    "id": "root",
    "kind": "root",
    "children": [
      {
        "id": "c1",
        "kind": "control",
        "visible_text": "Go",
        "verbatim_label_for_steps": "Go",
        "children": []
      }
    ]
  },
  "derived": {}
}
"""


class TestUiHierarchyPayload(unittest.TestCase):
    def test_parse_minimal(self) -> None:
        r = parse_ui_hierarchy_payload(MINIMAL)
        self.assertEqual(r.schema_version, "ui-hierarchy-v1")
        self.assertEqual(count_control_nodes(r.root), 1)

    def test_minified_json_roundtrip(self) -> None:
        r = parse_ui_hierarchy_payload(MINIMAL)
        s = ui_hierarchy_to_minified_json(r)
        data = json.loads(s)
        self.assertEqual(data["root"]["id"], "root")

    def test_collect_literals(self) -> None:
        r = parse_ui_hierarchy_payload(MINIMAL)
        lit: set[str] = set()
        collect_verbatim_literals_from_dump(r.model_dump(mode="json"), lit)
        self.assertIn("Go", lit)

    def test_invalid_json_raises(self) -> None:
        with self.assertRaises(AIProcessingError):
            parse_ui_hierarchy_payload("not json")

    def test_omitted_derived_defaults(self) -> None:
        raw = """
        {
          "schema_version": "ui-hierarchy-v1",
          "overview": {"page_summary": "x", "business_intent": "", "interactive_element_count": 0},
          "root": {"id": "root", "kind": "root", "children": []}
        }
        """
        r = parse_ui_hierarchy_payload(raw)
        self.assertEqual(r.derived.cohesive_forms, [])


if __name__ == "__main__":
    unittest.main()
