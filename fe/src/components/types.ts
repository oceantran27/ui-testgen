export interface AnalysisRecord {
  id: number;
  image_path: string;
  scenario_json: string;
  created_at: string;
}

export interface DebateEvent {
  event_id: string;
  sequence: number;
  timestamp: string;
  request_id: string;
  batch_id?: string | null;
  scenario_id?: string | null;
  role: string;
  event_type: string;
  message: string;
  metadata: Record<string, unknown>;
}

export interface DebateEventsPollResponse {
  request_id: string;
  batch_id?: string | null;
  next_seq: number;
  completed: boolean;
  status: string;
  events: DebateEvent[];
}

export type DebateStreamStatus =
  | "idle"
  | "running"
  | "completed"
  | "failed"
  | "expired"
  | "error";
