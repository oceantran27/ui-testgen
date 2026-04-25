export interface AnalysisRecord {
  id: number;
  image_path: string;
  scenario_json: string;
  created_at: string;
}

export interface BddFeatureBlock {
  name: string;
  description?: string;
}

export interface BddScenarioItem {
  id: string;
  title: string;
  gherkin: string;
}

export interface BddHappyPathResult {
  model: string;
  feature: BddFeatureBlock;
  scenarios: BddScenarioItem[];
  combined_gherkin: string;
}
