// TypeScript types mirroring web/backend/schemas.py.
// Kept in sync manually; the backend is the source of truth.

export type DataMode = "mock" | "real_replay" | "live_lab";

export type SafetyLevel =
  | "candidate_for_free_walking"
  | "supported_test_only"
  | "blocked";

export interface ExperimentPair {
  pair_id: string;
  control: Record<string, unknown>;
  treatment: Record<string, unknown>;
  controlled_variables: string[];
  hypothesis: string;
  warning: string | null;
}

export interface WorkflowResult {
  pair: ExperimentPair;
  nodes: NodeEntry[];
  training_jobs: TrainingJob[];
  artifacts: Record<string, unknown>[];
  evaluations: Record<string, Evaluation>;
  comparison: Comparison;
  failure_analysis: Record<string, unknown>;
  safety: SafetyResult;
  deployment_package: DeploymentPackage;
  robot_action_diff: string;
  report_markdown: string;
  audit_log: string[];
}

export interface NodeEntry {
  name: string;
  role: string;
  status: string;
  host: string | null;
}

export interface TrainingJob {
  job_id?: string;
  node: string;
  run_id: string;
  status?: string;
  progress?: number;
  latest_step?: number;
  latest_reward?: number;
  fall_rate?: number;
  evidence_mode?: string;
}

export interface Evaluation {
  num_rollouts: number;
  fall_free_count: number;
  avg_fall_time_sec: number;
  avg_velocity: number;
  target_velocity: number;
  torso_pitch_rms: number;
  energy_proxy: number;
  joint_limit_max_ratio: number;
  foot_contact_symmetry: number;
  action_jerk: number;
  emergency_stop_dry_run: boolean;
  evidence_mode?: string;
  [k: string]: unknown;
}

export interface MetricRow {
  metric: string;
  control: string;
  treatment: string;
  verdict: string;
}

export interface Comparison {
  decision: string;
  recommendation: string;
  improvements: string[];
  regressions: string[];
  metric_rows: MetricRow[];
}

export interface SafetyResult {
  policy_id: string;
  safety_level: SafetyLevel;
  free_walking_allowed: boolean;
  supported_test_allowed: boolean;
  reasons: string[];
  required_actions: string[];
}

export interface DeploymentPackage {
  manifest_path?: string;
  package_type: string;
  human_approval_required?: boolean;
  free_walking_allowed?: boolean;
  contains?: string[];
  live_deploy_attempted?: boolean;
  live_deploy_allowed?: boolean;
  block_reasons?: string[];
  [k: string]: unknown;
}

// Live lab shapes
export interface GpuSnapshot {
  name: string;
  mem_used: string;
  mem_total: string;
  util: string;
}

export interface ScalarsSnapshot {
  iteration: number;
  reward: number;
  ep_len: number;
}

export interface NodeSnapshot {
  label: string;
  host: string;
  reachable: boolean;
  error?: string;
  ts: number;
  hostname?: string;
  gpu?: GpuSnapshot;
  tmux_sessions?: string[];
  busy?: boolean;
  latest_run_dir?: string;
  scalars?: ScalarsSnapshot;
  training_procs?: TrainingProc[];
}

export interface TrainingProc {
  pid: number;
  cmd: string;
  elapsed_sec?: number;
  task_name?: string;
  num_envs?: number;
  max_iterations?: number;
  seed?: number;
  resume_from?: string;
  label?: string;
}

export interface JobSummary {
  job_id: string;
  node: string;
  run_id: string;
  config_path?: string;
  status: string;
  progress: number;
  latest_step: number;
  estimated_remaining_min: number;
  latest_reward: number;
  fall_rate: number;
  evidence_mode: string;
  stage_name: string;
  tmux_session: string;
  host_masked: string;
  submitted_at: number;
  max_iterations: number;
  status_history: Array<[number, string, Record<string, unknown>]>;
  collected?: boolean;
}

export interface LabConfig {
  mode: string;
  enable_ssh: boolean;
  allow_real_robot: boolean;
  enabled: boolean;
  lab_repo_path: string;
  remote_repo_path: string;
  gpu0_host: string;
  gpu1_host: string;
  ssh_user: string;
  operator_approval_required: boolean;
  live_demo_mock?: boolean;
  [k: string]: unknown;
}

export interface LabState {
  jobs: JobSummary[];
  node_cache: Record<string, NodeSnapshot>;
  node_cache_ts: number;
}

export interface LabUpdateEvent {
  ts: number;
  nodes: Record<string, NodeSnapshot>;
  jobs: JobSummary[];
}

export interface HealthResponse {
  status: string;
  version: string;
  live_lab_enabled: boolean;
}

export interface WorkflowRequestBody {
  request: string;
  num_rollouts?: number;
  safety_strictness?: "standard" | "strict";
  data_mode?: DataMode;
  operator_token?: string | null;
  operator_confirmed?: boolean;
}

export interface SubmitJobBody {
  node: "GPU0" | "GPU1";
  run_id: string;
  parent_stage?: string;
  patch?: Record<string, number | string> | null;
  num_envs?: number;
  max_iterations?: number;
  wall_clock_cap?: string;
  seed?: number;
}

export interface ReplayRun {
  role: string;
  alias: string;
  source_kind: string;
  rows: number;
  duration_sec: number;
  metrics_file: string;
  scalars_file: string;
}

export interface HistoryRun {
  id: number;
  run_dir: string;
  server: string;
  task: string;
  hostname: string;
  max_iteration: number;
  final_reward: number;
  final_ep_len: number;
  num_checkpoints: number;
  num_events: number;
  start_ts: number;
  synced_at: number;
  stage_tag?: string;
  git_commit?: string;
  reward_terms?: string;
}
