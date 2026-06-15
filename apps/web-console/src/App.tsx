import { FormEvent, ReactNode, useEffect, useMemo, useState } from "react";

type PageKey = "overview" | "models" | "deployments" | "monitoring" | "rag" | "governance";
type LoadState = "loading" | "live" | "mock" | "error";

type ModelStage = "dev" | "candidate" | "staging" | "approved" | "production" | "deprecated";

type ModelArtifact = {
  id: string;
  name: string;
  version: string;
  framework: string;
  artifact_uri: string;
  training_dataset_id: string;
  metrics_json: Record<string, unknown>;
  lineage_json: Record<string, unknown>;
  stage: ModelStage;
  created_at: string;
};

type Deployment = {
  id: string;
  model_id: string;
  environment: string;
  deployment_type: string;
  endpoint_url: string;
  traffic_percent: number;
  status: string;
  created_at: string;
};

type AuditEvent = {
  id: string;
  actor: string;
  action: string;
  target_type: string;
  target_id: string;
  correlation_id: string;
  metadata_json: Record<string, unknown>;
  created_at: string;
};

type Approval = {
  id: string;
  target_type: string;
  target_id: string;
  approver: string;
  decision: string;
  notes: string;
  created_at: string;
};

type PromptTemplate = {
  id: string;
  name: string;
  version: string;
  template_text?: string;
  owner: string;
  safety_notes: string;
  status: string;
  created_at?: string;
};

type ModelCard = {
  id: string;
  model_id: string;
  intended_use: string;
  prohibited_use: string;
  training_data_summary: string;
  metrics_summary: Record<string, unknown>;
  fairness_summary: Record<string, unknown>;
  explainability_summary: string;
  owner: string;
  reviewer: string;
  approval_status: string;
  created_at: string;
  updated_at: string;
};

type PromptCard = {
  id: string;
  prompt_id: string;
  intended_use: string;
  data_sources: string[];
  safety_constraints: string[];
  known_failure_modes: string[];
  evaluation_summary: Record<string, unknown>;
  owner: string;
  approval_status: string;
  created_at: string;
  updated_at: string;
};

type EvaluationRun = {
  id: string;
  target_type: string;
  target_id: string;
  metrics_json: Record<string, unknown>;
  passed: boolean;
  report_uri: string;
  created_at: string;
};

type MonitoringSummary = {
  model_name: string;
  event_count: number;
  error_count: number;
  avg_latency_ms: number | null;
  p95_latency_ms: number | null;
  high_risk_rate: number | null;
  latest_drift_status: string | null;
  risk_band_counts: Record<string, number>;
};

type RagCitation = {
  source_id: string;
  doc_id: string;
  title: string;
  source_uri: string;
};

type RagResponse = {
  answer: string;
  citations: RagCitation[];
  groundedness_score: number;
  safety_flags: string[];
  human_review_required: boolean;
  provider_metadata: {
    provider: string;
    model_name: string;
    fallback_mode: boolean;
  };
  prompt: {
    prompt_template_id: string;
    prompt_version: string;
    source: string;
  };
  retrieval_metadata: {
    provider: string;
    returned_chunks: number;
    role_filter: string;
    source_ids: string[];
  };
  correlation_id: string;
};

type PlatformData = {
  models: ModelArtifact[];
  deployments: Deployment[];
  auditEvents: AuditEvent[];
  approvals: Approval[];
  prompts: PromptTemplate[];
  modelCards: ModelCard[];
  promptCards: PromptCard[];
  evaluations: EvaluationRun[];
  monitoring: MonitoringSummary;
};

type ApiConfig = {
  controlPlaneUrl: string;
  ragUrl: string;
};

const pages: { key: PageKey; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "models", label: "Models" },
  { key: "deployments", label: "Deployments" },
  { key: "monitoring", label: "Monitoring" },
  { key: "rag", label: "RAG" },
  { key: "governance", label: "Governance" }
];

const stageFlow: ModelStage[] = [
  "dev",
  "candidate",
  "staging",
  "approved",
  "production",
  "deprecated"
];

const config: ApiConfig = {
  controlPlaneUrl:
    import.meta.env.VITE_CONTROL_PLANE_API_URL ?? import.meta.env.VITE_API_BASE_URL ?? "",
  ragUrl: import.meta.env.VITE_RAG_SERVICE_URL ?? ""
};

const resolvedConfig: ApiConfig = {
  controlPlaneUrl: config.controlPlaneUrl || "http://localhost:8000",
  ragUrl: config.ragUrl || "http://localhost:8002"
};

const mockData: PlatformData = {
  models: [
    {
      id: "model-claims-risk-001",
      name: "claims-risk",
      version: "0.1.0",
      framework: "scikit-learn",
      artifact_uri: "mlruns:/claims-risk/0.1.0",
      training_dataset_id: "synthetic-claims-v1",
      metrics_json: { auc: 0.87, precision: 0.74, recall: 0.69, f1: 0.71 },
      lineage_json: {
        training_data_hash: "synthetic-hash-placeholder",
        feature_list: ["age_bucket", "plan_type", "prior_claim_count"]
      },
      stage: "candidate",
      created_at: "2026-06-15T06:30:00Z"
    },
    {
      id: "model-claims-risk-000",
      name: "claims-risk",
      version: "0.0.9",
      framework: "scikit-learn",
      artifact_uri: "mlruns:/claims-risk/0.0.9",
      training_dataset_id: "synthetic-claims-v0",
      metrics_json: { auc: 0.82, precision: 0.7, recall: 0.64, f1: 0.67 },
      lineage_json: { promoted_by: "demo-operator", rollback_ready: true },
      stage: "production",
      created_at: "2026-06-14T17:15:00Z"
    },
    {
      id: "prompt-rag-001",
      name: "healthcare-ops-rag-prompt",
      version: "local-v1",
      framework: "prompt-template",
      artifact_uri: "control-plane:/prompts/local-healthcare-ops-rag",
      training_dataset_id: "synthetic-docs-2026.06",
      metrics_json: { groundedness: 1.0, citation_coverage: 0.975 },
      lineage_json: { eval_set: "data/eval/rag_eval_set.jsonl" },
      stage: "approved",
      created_at: "2026-06-15T07:20:00Z"
    }
  ],
  deployments: [
    {
      id: "dep-prod-claims-risk",
      model_id: "model-claims-risk-000",
      environment: "prod",
      deployment_type: "blue-green",
      endpoint_url: "http://localhost:8001/predict/claims-risk",
      traffic_percent: 100,
      status: "active",
      created_at: "2026-06-15T06:45:00Z"
    },
    {
      id: "dep-rag-local",
      model_id: "prompt-rag-001",
      environment: "demo",
      deployment_type: "local-fallback",
      endpoint_url: "http://localhost:8002/rag/query",
      traffic_percent: 100,
      status: "active",
      created_at: "2026-06-15T07:21:00Z"
    }
  ],
  auditEvents: [
    {
      id: "audit-1004",
      actor: "rag-service",
      action: "rag.query_answered",
      target_type: "rag_query",
      target_id: "demo-rag-001",
      correlation_id: "demo-rag-001",
      metadata_json: { prompt_version: "local-v1", safety_flags: [] },
      created_at: "2026-06-15T07:25:00Z"
    },
    {
      id: "audit-1003",
      actor: "inference-service",
      action: "prediction_event.ingested",
      target_type: "prediction_event",
      target_id: "pred-001",
      correlation_id: "demo-inference-001",
      metadata_json: { model_name: "claims-risk", risk_band: "high" },
      created_at: "2026-06-15T07:05:00Z"
    },
    {
      id: "audit-1002",
      actor: "model-risk-reviewer",
      action: "model.promoted",
      target_type: "model",
      target_id: "model-claims-risk-000",
      correlation_id: "promotion-demo-001",
      metadata_json: { from_stage: "approved", to_stage: "production" },
      created_at: "2026-06-15T06:40:00Z"
    }
  ],
  approvals: [
    {
      id: "approval-001",
      target_type: "model",
      target_id: "model-claims-risk-000",
      approver: "model-risk-reviewer",
      decision: "approved",
      notes: "Synthetic metrics pass demo thresholds.",
      created_at: "2026-06-15T06:35:00Z"
    }
  ],
  prompts: [
    {
      id: "local-healthcare-ops-rag",
      name: "Healthcare Operations RAG",
      version: "local-v1",
      owner: "careai-platform",
      safety_notes: "Requires citations and human review for clinical advice.",
      status: "approved"
    }
  ],
  modelCards: [
    {
      id: "model-card-claims-risk-000",
      model_id: "model-claims-risk-000",
      intended_use:
        "Synthetic claims-risk prioritization for operations review and interview demos.",
      prohibited_use:
        "Clinical diagnosis, benefit determination, automated denial, or real patient decisions.",
      training_data_summary:
        "Deterministic synthetic claims-like records with no real PHI or PII.",
      metrics_summary: { auc: 0.82, f1: 0.67, calibration: "demo-reviewed" },
      fairness_summary: { age_bucket_review: "no material synthetic segment gap observed" },
      explainability_summary: "Reason codes are derived from aggregate utilization features.",
      owner: "ml-platform-demo",
      reviewer: "model-risk-reviewer",
      approval_status: "approved",
      created_at: "2026-06-15T06:34:00Z",
      updated_at: "2026-06-15T06:36:00Z"
    },
    {
      id: "model-card-claims-risk-001",
      model_id: "model-claims-risk-001",
      intended_use: "Candidate synthetic claims-risk model awaiting governance review.",
      prohibited_use: "Production use before review, approval, and deployment checks.",
      training_data_summary: "Synthetic claims-like records generated for local demo testing.",
      metrics_summary: { auc: 0.87, f1: 0.71 },
      fairness_summary: { age_bucket_review: "pending" },
      explainability_summary: "Reason-code review is pending model-risk signoff.",
      owner: "ml-platform-demo",
      reviewer: "model-risk-reviewer",
      approval_status: "draft",
      created_at: "2026-06-15T07:10:00Z",
      updated_at: "2026-06-15T07:10:00Z"
    }
  ],
  promptCards: [
    {
      id: "prompt-card-rag-001",
      prompt_id: "local-healthcare-ops-rag",
      intended_use:
        "Answer synthetic healthcare operations policy questions with citations and safety flags.",
      data_sources: ["synthetic policy documents", "synthetic RAG evaluation set"],
      safety_constraints: [
        "Require citations",
        "Reject secret requests",
        "Flag diagnosis or treatment questions for human review"
      ],
      known_failure_modes: ["Missing citation coverage", "Role-filtered document gaps"],
      evaluation_summary: {
        retrieval_hit_rate: 1.0,
        citation_coverage: 0.975,
        groundedness: 1.0
      },
      owner: "llmops-demo",
      approval_status: "approved",
      created_at: "2026-06-15T07:18:00Z",
      updated_at: "2026-06-15T07:19:00Z"
    }
  ],
  evaluations: [
    {
      id: "eval-rag-001",
      target_type: "rag",
      target_id: "http://localhost:8002",
      metrics_json: {
        retrieval_hit_rate: 1.0,
        citation_coverage: 0.975,
        keyword_relevance: 0.9,
        groundedness: 1.0,
        safety_flag_rate: 0.0
      },
      passed: true,
      report_uri: "data/local/rag-eval-report.json",
      created_at: "2026-06-15T07:18:00Z"
    }
  ],
  monitoring: {
    model_name: "claims-risk",
    event_count: 128,
    error_count: 1,
    avg_latency_ms: 37,
    p95_latency_ms: 82,
    high_risk_rate: 0.18,
    latest_drift_status: "green",
    risk_band_counts: { low: 76, medium: 29, high: 23 }
  }
};

export function App() {
  const [page, setPage] = useState<PageKey>("overview");
  const [data, setData] = useState<PlatformData>(mockData);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [statusMessage, setStatusMessage] = useState("Loading platform APIs...");
  const [selectedModelId, setSelectedModelId] = useState(mockData.models[0]?.id ?? "");
  const [promotingModelId, setPromotingModelId] = useState<string | null>(null);
  const [ragQuestion, setRagQuestion] = useState(
    "What should reviewers check before escalating a prior authorization request?"
  );
  const [ragRole, setRagRole] = useState("clinical_ops");
  const [ragResponse, setRagResponse] = useState<RagResponse | null>(null);
  const [ragLoading, setRagLoading] = useState(false);
  const [ragError, setRagError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoadState("loading");
      try {
        const loaded = await loadPlatformData(resolvedConfig);
        if (cancelled) return;
        setData(loaded);
        setSelectedModelId(loaded.models[0]?.id ?? "");
        setLoadState("live");
        setStatusMessage("Connected to local APIs.");
      } catch (error) {
        if (cancelled) return;
        setData(mockData);
        setSelectedModelId(mockData.models[0]?.id ?? "");
        setLoadState("mock");
        setStatusMessage(
          error instanceof Error
            ? `API fallback active: ${error.message}`
            : "API fallback active."
        );
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const selectedModel = useMemo(
    () => data.models.find((model) => model.id === selectedModelId) ?? data.models[0],
    [data.models, selectedModelId]
  );
  const stageCounts = useMemo(() => countModelsByStage(data.models), [data.models]);
  const ragEvaluation = useMemo(
    () => data.evaluations.find((evaluation) => evaluation.target_type === "rag"),
    [data.evaluations]
  );

  async function promoteModel(model: ModelArtifact) {
    const nextStage = nextModelStage(model.stage);
    if (!nextStage) return;

    setPromotingModelId(model.id);
    if (loadState === "live") {
      try {
        const promoted = await postJson<ModelArtifact>(
          `${resolvedConfig.controlPlaneUrl}/models/${model.id}/promote`,
          {
            stage: nextStage,
            actor: "web-console",
            notes: "Interview demo promotion from web console."
          }
        );
        setData((current) => ({
          ...current,
          models: current.models.map((item) => (item.id === model.id ? promoted : item))
        }));
      } catch (error) {
        const message = error instanceof Error ? error.message : "Promotion request failed.";
        if (error instanceof TypeError) {
          setLoadState("mock");
          setStatusMessage("Promotion API unavailable; local mock state updated.");
          promoteModelLocally(model.id, nextStage);
        } else {
          setStatusMessage(`Promotion blocked: ${message}`);
        }
      } finally {
        setPromotingModelId(null);
      }
      return;
    }

    promoteModelLocally(model.id, nextStage);
    setPromotingModelId(null);
  }

  function promoteModelLocally(modelId: string, stage: ModelStage) {
    setData((current) => ({
      ...current,
      models: current.models.map((model) => (model.id === modelId ? { ...model, stage } : model))
    }));
  }

  async function submitRagQuery(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setRagLoading(true);
    setRagError("");
    try {
      const response = await postJson<RagResponse>(`${resolvedConfig.ragUrl}/rag/query`, {
        user_id: "web-console-demo-user",
        role: ragRole,
        question: ragQuestion,
        top_k: 4
      });
      setRagResponse(response);
    } catch {
      setRagError("RAG API unavailable; showing local mock response.");
      setRagResponse(mockRagResponse(ragRole));
    } finally {
      setRagLoading(false);
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">careai-platform</p>
          <h1>Interview Demo Console</h1>
        </div>
        <div className={`connection connection-${loadState}`}>
          <span>{loadState.toUpperCase()}</span>
          <p>{statusMessage}</p>
        </div>
      </header>

      <nav className="tabs" aria-label="Console sections">
        {pages.map((item) => (
          <button
            aria-current={page === item.key ? "page" : undefined}
            className={page === item.key ? "active" : ""}
            key={item.key}
            onClick={() => setPage(item.key)}
            type="button"
          >
            {item.label}
          </button>
        ))}
      </nav>

      {loadState === "loading" ? <LoadingPanel /> : null}

      {page === "overview" ? (
        <OverviewPage
          auditEvents={data.auditEvents}
          deployments={data.deployments}
          monitoring={data.monitoring}
          ragEvaluation={ragEvaluation}
          stageCounts={stageCounts}
        />
      ) : null}
      {page === "models" ? (
        <ModelsPage
          models={data.models}
          onPromote={promoteModel}
          promotingModelId={promotingModelId}
          selectedModel={selectedModel}
          selectedModelId={selectedModelId}
          setSelectedModelId={setSelectedModelId}
        />
      ) : null}
      {page === "deployments" ? <DeploymentsPage deployments={data.deployments} /> : null}
      {page === "monitoring" ? <MonitoringPage monitoring={data.monitoring} /> : null}
      {page === "rag" ? (
        <RagPage
          error={ragError}
          loading={ragLoading}
          onSubmit={submitRagQuery}
          question={ragQuestion}
          response={ragResponse}
          role={ragRole}
          setQuestion={setRagQuestion}
          setRole={setRagRole}
        />
      ) : null}
      {page === "governance" ? (
        <GovernancePage
          approvals={data.approvals}
          auditEvents={data.auditEvents}
          evaluations={data.evaluations}
          modelCards={data.modelCards}
          models={data.models}
          promptCards={data.promptCards}
          prompts={data.prompts}
        />
      ) : null}
    </main>
  );
}

function OverviewPage({
  auditEvents,
  deployments,
  monitoring,
  ragEvaluation,
  stageCounts
}: {
  auditEvents: AuditEvent[];
  deployments: Deployment[];
  monitoring: MonitoringSummary;
  ragEvaluation?: EvaluationRun;
  stageCounts: Record<ModelStage, number>;
}) {
  return (
    <section className="page-grid overview-grid">
      <Panel title="Models By Stage">
        <div className="stage-grid">
          {stageFlow.map((stage) => (
            <div className="stage-tile" key={stage}>
              <span>{titleCase(stage)}</span>
              <strong>{stageCounts[stage] ?? 0}</strong>
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="Active Deployments">
        <DataTable
          columns={["Environment", "Endpoint", "Traffic", "Status"]}
          rows={deployments.map((deployment) => [
            deployment.environment,
            deployment.endpoint_url,
            `${deployment.traffic_percent}%`,
            deployment.status
          ])}
        />
      </Panel>

      <Panel title="Monitoring Snapshot">
        <div className="metric-row">
          <Metric label="Drift" value={monitoring.latest_drift_status ?? "unknown"} />
          <Metric label="Predictions" value={monitoring.event_count.toString()} />
          <Metric label="P95 latency" value={formatMs(monitoring.p95_latency_ms)} />
        </div>
      </Panel>

      <Panel title="RAG Evaluation Status">
        <div className="eval-status">
          <StatusPill tone={ragEvaluation?.passed ? "green" : "yellow"}>
            {ragEvaluation?.passed ? "Passed" : "Needs review"}
          </StatusPill>
          <dl>
            <div>
              <dt>Retrieval hit rate</dt>
              <dd>{formatPercent(ragEvaluation?.metrics_json.retrieval_hit_rate)}</dd>
            </div>
            <div>
              <dt>Citation coverage</dt>
              <dd>{formatPercent(ragEvaluation?.metrics_json.citation_coverage)}</dd>
            </div>
            <div>
              <dt>Groundedness</dt>
              <dd>{formatPercent(ragEvaluation?.metrics_json.groundedness)}</dd>
            </div>
          </dl>
        </div>
      </Panel>

      <Panel title="Recent Audit Events" wide>
        <AuditTable events={auditEvents.slice(0, 5)} />
      </Panel>
    </section>
  );
}

function ModelsPage({
  models,
  onPromote,
  promotingModelId,
  selectedModel,
  selectedModelId,
  setSelectedModelId
}: {
  models: ModelArtifact[];
  onPromote: (model: ModelArtifact) => void;
  promotingModelId: string | null;
  selectedModel?: ModelArtifact;
  selectedModelId: string;
  setSelectedModelId: (id: string) => void;
}) {
  return (
    <section className="split-page">
      <Panel title="Model Artifacts">
        <div className="list-stack">
          {models.map((model) => (
            <button
              className={`row-button ${selectedModelId === model.id ? "selected" : ""}`}
              key={model.id}
              onClick={() => setSelectedModelId(model.id)}
              type="button"
            >
              <span>
                <strong>{model.name}</strong>
                <small>{model.version}</small>
              </span>
              <StatusPill tone={stageTone(model.stage)}>{model.stage}</StatusPill>
            </button>
          ))}
        </div>
      </Panel>

      <Panel title="Model Detail" wide>
        {selectedModel ? (
          <div className="detail-stack">
            <div className="detail-header">
              <div>
                <h2>{selectedModel.name}</h2>
                <p>{selectedModel.framework} · {selectedModel.artifact_uri}</p>
              </div>
              <button
                className="primary-action"
                disabled={!nextModelStage(selectedModel.stage) || promotingModelId === selectedModel.id}
                onClick={() => onPromote(selectedModel)}
                type="button"
              >
                {nextModelStage(selectedModel.stage)
                  ? `Promote to ${nextModelStage(selectedModel.stage)}`
                  : "No promotion target"}
              </button>
            </div>

            <div className="metric-row">
              {Object.entries(selectedModel.metrics_json).map(([key, value]) => (
                <Metric key={key} label={key} value={formatMetricValue(value)} />
              ))}
            </div>

            <div className="json-grid">
              <JsonBlock title="Lineage" value={selectedModel.lineage_json} />
              <JsonBlock
                title="Registry Metadata"
                value={{
                  id: selectedModel.id,
                  version: selectedModel.version,
                  stage: selectedModel.stage,
                  training_dataset_id: selectedModel.training_dataset_id,
                  created_at: selectedModel.created_at
                }}
              />
            </div>
          </div>
        ) : (
          <EmptyState message="No model artifacts found." />
        )}
      </Panel>
    </section>
  );
}

function DeploymentsPage({ deployments }: { deployments: Deployment[] }) {
  return (
    <section className="page-grid">
      <Panel title="Active Endpoints" wide>
        <DataTable
          columns={["Environment", "Type", "Endpoint", "Traffic", "Status"]}
          rows={deployments.map((deployment) => [
            deployment.environment,
            deployment.deployment_type,
            deployment.endpoint_url,
            `${deployment.traffic_percent}%`,
            deployment.status
          ])}
        />
      </Panel>
      <Panel title="Rollback Controls">
        <div className="rollback-box">
          <StatusPill tone="yellow">Placeholder</StatusPill>
          <p>
            Rollback will point traffic back to the last approved production model after
            deployment health, SLO, or drift triggers fail.
          </p>
          <button className="secondary-action" type="button">Stage rollback plan</button>
        </div>
      </Panel>
    </section>
  );
}

function MonitoringPage({ monitoring }: { monitoring: MonitoringSummary }) {
  const totalBands = Object.values(monitoring.risk_band_counts).reduce((sum, value) => sum + value, 0);
  return (
    <section className="page-grid">
      <Panel title="Production Signals" wide>
        <div className="metric-row">
          <Metric label="Prediction count" value={monitoring.event_count.toString()} />
          <Metric label="Error count" value={monitoring.error_count.toString()} />
          <Metric label="Avg latency" value={formatMs(monitoring.avg_latency_ms)} />
          <Metric label="P95 latency" value={formatMs(monitoring.p95_latency_ms)} />
          <Metric label="High risk rate" value={formatPercent(monitoring.high_risk_rate)} />
          <Metric label="Drift status" value={monitoring.latest_drift_status ?? "unknown"} />
        </div>
      </Panel>

      <Panel title="Risk Band Mix">
        <div className="bar-list">
          {Object.entries(monitoring.risk_band_counts).map(([band, count]) => (
            <div className="bar-row" key={band}>
              <span>{titleCase(band)}</span>
              <div className="bar-track">
                <div style={{ width: `${totalBands ? (count / totalBands) * 100 : 0}%` }} />
              </div>
              <strong>{count}</strong>
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="Feature Missingness Summary">
        <DataTable
          columns={["Feature", "Missing", "Freshness"]}
          rows={[
            ["age_bucket", "0.0%", "current"],
            ["plan_type", "0.0%", "current"],
            ["prior_claim_count", "0.8%", "current"],
            ["recent_visit_count", "0.4%", "current"],
            ["medication_count", "0.2%", "current"]
          ]}
        />
      </Panel>
    </section>
  );
}

function RagPage({
  error,
  loading,
  onSubmit,
  question,
  response,
  role,
  setQuestion,
  setRole
}: {
  error: string;
  loading: boolean;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  question: string;
  response: RagResponse | null;
  role: string;
  setQuestion: (question: string) => void;
  setRole: (role: string) => void;
}) {
  return (
    <section className="page-grid rag-grid">
      <Panel title="Ask Synthetic Policy Documents">
        <form className="rag-form" onSubmit={onSubmit}>
          <label>
            Role
            <select onChange={(event) => setRole(event.target.value)} value={role}>
              <option value="clinical_ops">Clinical Ops</option>
              <option value="claims_ops">Claims Ops</option>
              <option value="member_support">Member Support</option>
              <option value="pharmacy_ops">Pharmacy Ops</option>
              <option value="model_risk_reviewer">Model Risk Reviewer</option>
              <option value="platform_admin">Platform Admin</option>
            </select>
          </label>
          <label>
            Question
            <textarea
              onChange={(event) => setQuestion(event.target.value)}
              rows={5}
              value={question}
            />
          </label>
          <button className="primary-action" disabled={loading} type="submit">
            {loading ? "Querying..." : "Run RAG Query"}
          </button>
          {error ? <p className="inline-error">{error}</p> : null}
        </form>
      </Panel>

      <Panel title="Answer With Citations" wide>
        {response ? (
          <div className="answer-stack">
            <p className="answer-text">{response.answer}</p>
            <div className="metric-row">
              <Metric label="Groundedness" value={formatPercent(response.groundedness_score)} />
              <Metric label="Retrieved chunks" value={response.retrieval_metadata.returned_chunks.toString()} />
              <Metric label="Provider" value={response.provider_metadata.provider} />
              <Metric label="Prompt" value={response.prompt.prompt_version} />
            </div>
            <div className="flag-row">
              {response.safety_flags.length ? (
                response.safety_flags.map((flag) => (
                  <StatusPill key={flag} tone="yellow">{flag}</StatusPill>
                ))
              ) : (
                <StatusPill tone="green">No safety flags</StatusPill>
              )}
              {response.human_review_required ? (
                <StatusPill tone="red">Human review</StatusPill>
              ) : null}
            </div>
            <DataTable
              columns={["Citation", "Document", "Source"]}
              rows={response.citations.map((citation) => [
                citation.source_id,
                citation.title,
                citation.doc_id
              ])}
            />
          </div>
        ) : (
          <EmptyState message="Run a RAG query to see answer, citations, and safety checks." />
        )}
      </Panel>
    </section>
  );
}

function GovernancePage({
  approvals,
  auditEvents,
  evaluations,
  modelCards,
  models,
  promptCards,
  prompts
}: {
  approvals: Approval[];
  auditEvents: AuditEvent[];
  evaluations: EvaluationRun[];
  modelCards: ModelCard[];
  models: ModelArtifact[];
  promptCards: PromptCard[];
  prompts: PromptTemplate[];
}) {
  const approvalsByTarget = new Set(
    approvals
      .filter((approval) => approval.decision === "approved")
      .map((approval) => `${approval.target_type}:${approval.target_id}`)
  );
  const modelCardsByModel = new Map(modelCards.map((card) => [card.model_id, card]));
  const promptCardsByPrompt = new Map(promptCards.map((card) => [card.prompt_id, card]));

  return (
    <section className="page-grid">
      <Panel title="Release Gates" wide>
        <DataTable
          columns={["Asset", "Card", "Approval", "Production Ready"]}
          rows={[
            ...models.map((model) => {
              const card = modelCardsByModel.get(model.id);
              const cardApproved = card?.approval_status === "approved";
              const approvalReady = approvalsByTarget.has(`model:${model.id}`);
              return [
                `${model.name} ${model.version}`,
                cardApproved ? "approved" : card ? card.approval_status : "missing",
                approvalReady ? "approved" : "missing",
                cardApproved && approvalReady ? "yes" : "blocked"
              ];
            }),
            ...prompts.map((prompt) => {
              const card = promptCardsByPrompt.get(prompt.id);
              const cardApproved = card?.approval_status === "approved";
              const promptApproved = prompt.status === "approved";
              return [
                `${prompt.name} ${prompt.version}`,
                cardApproved ? "approved" : card ? card.approval_status : "missing",
                promptApproved ? "approved prompt" : prompt.status,
                cardApproved && promptApproved ? "yes" : "blocked"
              ];
            })
          ]}
        />
      </Panel>

      <Panel title="Approvals">
        <DataTable
          columns={["Target", "Approver", "Decision", "Notes"]}
          rows={approvals.map((approval) => [
            `${approval.target_type}:${approval.target_id}`,
            approval.approver,
            approval.decision,
            approval.notes
          ])}
        />
      </Panel>

      <Panel title="Audit Events" wide>
        <AuditTable events={auditEvents} />
      </Panel>

      <Panel title="Model Cards Summary">
        <DataTable
          columns={["Model", "Owner", "Reviewer", "Status", "Use"]}
          rows={modelCards.map((card) => {
            const model = models.find((item) => item.id === card.model_id);
            return [
              model ? `${model.name} ${model.version}` : card.model_id,
              card.owner,
              card.reviewer,
              card.approval_status,
              card.intended_use
            ];
          })}
        />
      </Panel>

      <Panel title="Prompt Cards Summary">
        <DataTable
          columns={["Prompt", "Owner", "Status", "Sources", "Safety"]}
          rows={promptCards.map((card) => {
            const prompt = prompts.find((item) => item.id === card.prompt_id);
            return [
              prompt ? `${prompt.name} ${prompt.version}` : card.prompt_id,
              card.owner,
              card.approval_status,
              card.data_sources.join(", "),
              card.safety_constraints.join(", ")
            ];
          })}
        />
      </Panel>

      <Panel title="Evaluation Runs">
        <DataTable
          columns={["Target", "Passed", "Report"]}
          rows={evaluations.map((evaluation) => [
            evaluation.target_type,
            evaluation.passed ? "yes" : "no",
            evaluation.report_uri
          ])}
        />
      </Panel>
    </section>
  );
}

function Panel({
  children,
  title,
  wide = false
}: {
  children: ReactNode;
  title: string;
  wide?: boolean;
}) {
  return (
    <section className={`panel ${wide ? "wide" : ""}`}>
      <h2>{title}</h2>
      {children}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function DataTable({ columns, rows }: { columns: string[]; rows: string[][] }) {
  if (!rows.length) {
    return <EmptyState message="No records available." />;
  }
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={`${row.join("-")}-${rowIndex}`}>
              {row.map((cell, cellIndex) => (
                <td key={`${cell}-${cellIndex}`}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AuditTable({ events }: { events: AuditEvent[] }) {
  return (
    <DataTable
      columns={["Time", "Actor", "Action", "Target", "Correlation"]}
      rows={events.map((event) => [
        formatDate(event.created_at),
        event.actor,
        event.action,
        `${event.target_type}:${event.target_id}`,
        event.correlation_id
      ])}
    />
  );
}

function JsonBlock({ title, value }: { title: string; value: unknown }) {
  return (
    <div className="json-block">
      <h3>{title}</h3>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </div>
  );
}

function StatusPill({
  children,
  tone
}: {
  children: ReactNode;
  tone: "green" | "yellow" | "red" | "blue";
}) {
  return <span className={`status-pill ${tone}`}>{children}</span>;
}

function EmptyState({ message }: { message: string }) {
  return <p className="empty-state">{message}</p>;
}

function LoadingPanel() {
  return (
    <section className="loading-panel">
      <div className="loading-dot" />
      <span>Loading console data...</span>
    </section>
  );
}

async function loadPlatformData(apiConfig: ApiConfig): Promise<PlatformData> {
  const [
    models,
    deployments,
    auditEvents,
    approvals,
    prompts,
    modelCards,
    promptCards,
    evaluations
  ] = await Promise.all([
    fetchJson<ModelArtifact[]>(`${apiConfig.controlPlaneUrl}/models`),
    fetchJson<Deployment[]>(`${apiConfig.controlPlaneUrl}/deployments`),
    fetchJson<AuditEvent[]>(`${apiConfig.controlPlaneUrl}/audit-events`),
    fetchJson<Approval[]>(`${apiConfig.controlPlaneUrl}/approvals`),
    fetchJson<PromptTemplate[]>(`${apiConfig.controlPlaneUrl}/prompts`),
    fetchJson<ModelCard[]>(`${apiConfig.controlPlaneUrl}/model-cards`),
    fetchJson<PromptCard[]>(`${apiConfig.controlPlaneUrl}/prompt-cards`),
    fetchJson<EvaluationRun[]>(`${apiConfig.controlPlaneUrl}/evaluations`)
  ]);
  const modelName = models.find((model) => model.stage === "production")?.name ?? "claims-risk";
  const monitoring = await fetchJson<MonitoringSummary>(
    `${apiConfig.controlPlaneUrl}/monitoring/models/${encodeURIComponent(modelName)}/summary`
  ).catch(() => mockData.monitoring);

  return {
    models: models.length ? models : mockData.models,
    deployments: deployments.length ? deployments : mockData.deployments,
    auditEvents: auditEvents.length ? auditEvents : mockData.auditEvents,
    approvals: approvals.length ? approvals : mockData.approvals,
    prompts: prompts.length ? prompts : mockData.prompts,
    modelCards: modelCards.length ? modelCards : mockData.modelCards,
    promptCards: promptCards.length ? promptCards : mockData.promptCards,
    evaluations: evaluations.length ? evaluations : mockData.evaluations,
    monitoring
  };
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response));
  }
  return response.json() as Promise<T>;
}

async function postJson<T>(url: string, payload: unknown): Promise<T> {
  const response = await fetch(url, {
    body: JSON.stringify(payload),
    headers: { "content-type": "application/json" },
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response));
  }
  return response.json() as Promise<T>;
}

async function responseErrorMessage(response: Response): Promise<string> {
  const fallback = `${response.status} ${response.statusText}`;
  try {
    const body = (await response.json()) as {
      detail?: string | { message?: string; missing_controls?: string[] };
      message?: string;
      missing_controls?: string[];
    };
    const detail = body.detail;
    if (typeof detail === "string") return `${fallback}: ${detail}`;
    const message = detail?.message ?? body.message;
    const missingControls = detail?.missing_controls ?? body.missing_controls ?? [];
    if (message && missingControls.length) {
      return `${message} Missing controls: ${missingControls.join(", ")}`;
    }
    if (message) return message;
  } catch {
    return fallback;
  }
  return fallback;
}

function countModelsByStage(models: ModelArtifact[]): Record<ModelStage, number> {
  return stageFlow.reduce(
    (counts, stage) => ({
      ...counts,
      [stage]: models.filter((model) => model.stage === stage).length
    }),
    {} as Record<ModelStage, number>
  );
}

function nextModelStage(stage: ModelStage): ModelStage | null {
  const index = stageFlow.indexOf(stage);
  if (index < 0 || index >= stageFlow.length - 1) return null;
  return stageFlow[index + 1];
}

function stageTone(stage: ModelStage): "green" | "yellow" | "red" | "blue" {
  if (stage === "production" || stage === "approved") return "green";
  if (stage === "deprecated") return "red";
  if (stage === "staging" || stage === "candidate") return "yellow";
  return "blue";
}

function titleCase(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatMs(value: number | null): string {
  return value === null ? "unknown" : `${value} ms`;
}

function formatPercent(value: unknown): string {
  return typeof value === "number" ? `${Math.round(value * 1000) / 10}%` : "unknown";
}

function formatMetricValue(value: unknown): string {
  if (typeof value === "number") return value.toFixed(value < 1 ? 3 : 0);
  if (typeof value === "string") return value;
  if (typeof value === "boolean") return value ? "yes" : "no";
  return JSON.stringify(value);
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en-US", {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "short"
  }).format(new Date(value));
}

function mockRagResponse(role: string): RagResponse {
  return {
    answer:
      "Based on Prior Authorization Policy, reviewers should confirm documentation, urgency, " +
      "safe reason codes, and human-review triggers before escalation [prior_authorization_policy-0000].",
    citations: [
      {
        source_id: "prior_authorization_policy-0000",
        doc_id: "prior_authorization_policy",
        title: "Prior Authorization Policy",
        source_uri: "file:///synthetic/prior_authorization_policy.md"
      }
    ],
    groundedness_score: 0.92,
    safety_flags: [],
    human_review_required: false,
    provider_metadata: {
      provider: "local-mock",
      model_name: "local-deterministic-rag",
      fallback_mode: true
    },
    prompt: {
      prompt_template_id: "local-healthcare-ops-rag",
      prompt_version: "local-v1",
      source: "local"
    },
    retrieval_metadata: {
      provider: "mock",
      returned_chunks: 1,
      role_filter: role,
      source_ids: ["prior_authorization_policy-0000"]
    },
    correlation_id: "web-console-mock-rag"
  };
}
