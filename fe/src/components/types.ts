export interface AnalysisRecord {
  id: number;
  image_path: string;
  scenario_json: string;
  created_at: string;
}

export interface BddFeatureBlock {
  /** Short generic page/screen name; no product/brand instance. Letter case is not prescribed. */
  name: string;
  description?: string;
  /** Inferred business goals for this screen (may be ""). */
  business_intent: string;
}

export interface BddScenarioItem {
  id: string;
  /** Imperative (2–6 words); generic object only; specifics live in test_scenario. Case not prescribed. */
  title: string;
  test_scenario: string;
}

export interface BddHappyPathResult {
  model: string;
  feature: BddFeatureBlock;
  scenarios: BddScenarioItem[];
  combined_test_scenario: string;
}
