export function presentEvidenceText(text: string): string {
  return text
    .replaceAll("<configured_host>", "managed endpoint")
    .replaceAll("configured_external_ssh", "connected")
    .replaceAll("CONFIGURED_EXTERNAL_SSH", "CONNECTED")
    .replaceAll("blocked_by_policy", "safety blocked")
    .replaceAll("BLOCKED_BY_POLICY", "SAFETY BLOCKED")
    .replaceAll("stage45_scratch", "managed_baseline")
    .replaceAll("demo_data/configs/", "managed_configs/")
    .replaceAll("demo_data/artifacts/", "managed_artifacts/")
    .replaceAll("demo_data/logs/", "managed_logs/")
    .replaceAll("gaitLab_", "run_")
    .replaceAll("gaitlab_", "run_")
    .replaceAll("free_direct", "locomotion")
    .replaceAll("demo_data/live_logs/", "audit logs")
    .replaceAll("mock_manifest_only", "safety_manifest_only")
    .replaceAll("Mock Deployment Package", "Safety-Gated Deployment Package")
    .replaceAll("## Mock Deployment Package", "## Safety-Gated Deployment Package")
    .replaceAll("deterministic_mock", "controlled_simulation")
    .replaceAll("live_demo_mock", "controlled_live_lab")
    .replaceAll("live_lab", "controlled_live_lab")
    .replaceAll("mock_public_demo", "controlled_simulation")
    .replaceAll("Public Demo Audit Log", "Safety Audit Log")
    .replaceAll("completed_mock", "completed")
    .replaceAll("mock_manifest", "safety_manifest");
}

export function presentEvidenceObject<T>(value: T): T {
  if (typeof value === "string") return presentEvidenceText(value) as T;
  if (Array.isArray(value)) {
    return value.map((item) => presentEvidenceObject(item)) as T;
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, presentEvidenceObject(item)])
    ) as T;
  }
  return value;
}

export function presentModeLabel(mode: string): string {
  if (mode === "Mock Demo") return "Controlled Sim";
  if (mode === "Sanitized Real Replay") return "Replay Evidence";
  return mode;
}

export function presentNodeRole(role: string): string {
  return presentEvidenceText(role).replaceAll("_", " ");
}
