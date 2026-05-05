export interface AnalysisRecord {
  id: number;
  image_path: string;
  scenario_json: string;
  created_at: string;
}

export interface ScreenFeatureSummary {
  /** Short generic page/screen name; no product/brand instance. Letter case is not prescribed. */
  name: string;
  description?: string;
  /** Inferred business goals for this screen (may be ""). */
  business_intent: string;
}

export interface TestScenarioItem {
  id: string;
  /** Imperative (2–6 words); generic object only; specifics live in test_scenario. Case not prescribed. */
  title: string;
  test_scenario: string;
}

export interface TestScenarioSuite {
  model: string;
  feature: ScreenFeatureSummary;
  scenarios: TestScenarioItem[];
  combined_test_scenario: string;
}
