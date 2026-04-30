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
  /** Inferred business goals for this screen; used for the ranked BDD step (may be ""). */
  business_intent: string;
}

export interface BddScenarioItem {
  id: string;
  /** Imperative (2–6 words); generic object only; specifics live in gherkin. Case not prescribed. */
  title: string;
  gherkin: string;
}

export interface BddHappyPathResult {
  model: string;
  feature: BddFeatureBlock;
  scenarios: BddScenarioItem[];
  combined_gherkin: string;
}

/** Optional vision summary (placeholder in ranked response) */
export interface VisionScenarioSummary {
  id: string;
  user_goal: string;
  goal_tier?: string | null;
  structural_region?: string | null;
}

export interface VisionPageOverviewSummary {
  functionality: string;
  primary_scenario_ids?: string[] | null;
}

export interface VisionExtractionSummary {
  page_overview: VisionPageOverviewSummary;
  scenarios: VisionScenarioSummary[];
}

export interface BddHappyPathRankedResponse {
  bdd: BddHappyPathResult;
  vision_model: string;
  vision: VisionExtractionSummary;
}
