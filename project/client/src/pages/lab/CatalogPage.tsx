import { useEffect, useState } from "react";

import { labApi } from "../../api/lab";
import type { ModelInfo, Topic } from "../../api/types";
import { Badge, Card, ErrorBox, Loading } from "../../components/ui";
import { DOMAIN_LABELS } from "../../labels";

export default function CatalogPage() {
  const [models, setModels] = useState<ModelInfo[] | null>(null);
  const [topics, setTopics] = useState<Topic[] | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    labApi.models().then(setModels).catch(setError);
    labApi.topics().then(setTopics).catch(setError);
  }, []);

  return (
    <div className="stack">
      <ErrorBox error={error} />
      <Card title="Models (registry of the Generator)">
        {!models ? <Loading /> : (
          <div className="table-scroll"><table className="table">
            <thead><tr><th>Model</th><th>Model ID</th><th>Host</th><th>Size</th><th>Price / M tokens</th><th>Status</th></tr></thead>
            <tbody>
              {models.map((m) => (
                <tr key={m.alias}>
                  <td><strong>{m.label}</strong> <span className="muted">{m.alias}</span></td>
                  <td><code>{m.model_id}</code></td>
                  <td>{m.provider}</td>
                  <td>{m.params ?? "–"}</td>
                  <td>{m.paid ? `$${m.price_per_m.input} in / $${m.price_per_m.output} out` : "free"}</td>
                  <td>{m.available ? <Badge tone="best">available</Badge> : <Badge tone="weak">needs {m.requires}</Badge>}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
        <p className="muted small">The four thesis models are pinned to one host each, so every request runs on the same backend.</p>
      </Card>
      <Card title="Topics">
        {!topics ? <Loading /> : (
          <div className="table-scroll"><table className="table">
            <thead><tr><th>Topic</th><th>Domain</th><th>Origin</th><th>Source text</th></tr></thead>
            <tbody>
              {topics.map((t) => (
                <tr key={t.topic_id}>
                  <td><strong>{t.title}</strong> <span className="muted">{t.topic_id}</span></td>
                  <td>{DOMAIN_LABELS[t.domain] ?? t.domain}</td>
                  <td><Badge tone={t.origin === "thesis" ? "info" : "neutral"}>{t.origin}</Badge></td>
                  <td>{t.has_source_text ? `${t.source_length} characters` : <span className="muted">not published (thesis)</span>}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
      </Card>
    </div>
  );
}
