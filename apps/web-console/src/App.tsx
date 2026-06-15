const services = [
  {
    name: "Control Plane API",
    port: 8000,
    purpose: "Governance, registry metadata, promotion, audit, and orchestration."
  },
  {
    name: "Inference Service",
    port: 8001,
    purpose: "Synthetic claims-risk model serving, monitoring hooks, and rollback path."
  },
  {
    name: "RAG Service",
    port: 8002,
    purpose: "Synthetic document retrieval, prompt lifecycle, safety checks, and evaluation."
  }
];

const milestones = [
  "Synthetic data only",
  "Audit-ready metadata",
  "Deterministic demos",
  "Azure Container Apps target"
];

export function App() {
  return (
    <main className="shell">
      <section className="intro">
        <p className="eyebrow">Enterprise MLOps and LLMOps demo</p>
        <h1>careai-platform</h1>
        <p className="summary">
          Local-first healthcare-style platform workflows using synthetic data, clear governance,
          and Azure-ready deployment boundaries.
        </p>
      </section>

      <section className="status-grid" aria-label="Platform services">
        {services.map((service) => (
          <article className="service-card" key={service.name}>
            <div>
              <h2>{service.name}</h2>
              <p>{service.purpose}</p>
            </div>
            <a href={`http://localhost:${service.port}/healthz`}>:{service.port}/healthz</a>
          </article>
        ))}
      </section>

      <section className="milestones" aria-label="Demo principles">
        {milestones.map((milestone) => (
          <span key={milestone}>{milestone}</span>
        ))}
      </section>
    </main>
  );
}

