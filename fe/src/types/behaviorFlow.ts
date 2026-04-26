export interface BehaviorFlowItem {
  behavior_flow: string;
  screens: string[];
}

export interface BehaviorFlowOrganizeResponse {
  model: string;
  input_id: string;
  flows: BehaviorFlowItem[];
}

/** View model for album: public image paths (leading slash). */
export interface BehaviorFlowViewGroup {
  behavior_flow: string;
  images: string[];
}
