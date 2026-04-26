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

export type BddScenarioPriority = "primary" | "secondary" | "utility";
/** @deprecated Use BddScenarioPriority */
export type BddScenarioTier = BddScenarioPriority;

export interface BddScenarioItem {
  id: string;
  title: string;
  gherkin: string;
  /** 0–1: model confidence for Then-clause assertions (API always sends for new runs). */
  confidence?: number;
  /** Layout-based order (main body vs chrome); API sorts primary → secondary → utility. */
  priority?: BddScenarioPriority;
  /** Legacy stored JSON / older API responses */
  tier?: BddScenarioPriority;
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
