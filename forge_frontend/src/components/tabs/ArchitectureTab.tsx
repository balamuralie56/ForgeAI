import { useReport } from "../../useReport";
import { ReportGate } from "../ReportGate";
import { MermaidDiagram } from "../MermaidDiagram";
import type { ArchitectureSpecification } from "../../types";

export function ArchitectureTab({ enabled }: { enabled: boolean }) {
  const state = useReport<ArchitectureSpecification>("architecture_specification", enabled);

  return (
    <div className="tab-panel">
      <ReportGate state={state} waitingLabel="The architecture appears once the Architect stage completes.">
        {(spec) => (
          <div className="architecture">
            {spec.rationale && (
              <section className="arch__section">
                <h3>Rationale</h3>
                <p>{spec.rationale}</p>
              </section>
            )}

            {spec.decisions.length > 0 && (
              <section className="arch__section">
                <h3>Technology decisions</h3>
                <div className="decision-grid">
                  {spec.decisions.map((d, i) => (
                    <div key={i} className="decision-card">
                      <div className="decision-card__category">{d.category}</div>
                      <div className="decision-card__tech">{d.technology}</div>
                      <div className="decision-card__rationale">{d.rationale}</div>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {spec.directory_structure && (
              <section className="arch__section">
                <h3>Directory structure</h3>
                <pre className="arch__tree">{spec.directory_structure}</pre>
              </section>
            )}

            {spec.modules.length > 0 && (
              <section className="arch__section">
                <h3>Modules</h3>
                {spec.modules.map((m) => (
                  <div key={m.name} className="module-card">
                    <div className="module-card__header">
                      <span className="module-card__name">{m.name}</span>
                      {m.dependencies.length > 0 && (
                        <span className="module-card__deps">depends on {m.dependencies.join(", ")}</span>
                      )}
                    </div>
                    <p className="module-card__purpose">{m.purpose}</p>
                    {m.apis.length > 0 && (
                      <table className="api-table">
                        <tbody>
                          {m.apis.map((a, i) => (
                            <tr key={i}>
                              <td className="api-table__method">{a.method}</td>
                              <td className="api-table__path">{a.path}</td>
                              <td className="api-table__desc">{a.description}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                ))}
              </section>
            )}

            {spec.database_design.length > 0 && (
              <section className="arch__section">
                <h3>Database schema</h3>
                {spec.database_design.map((t) => (
                  <div key={t.table_name} className="table-card">
                    <div className="table-card__name">{t.table_name}</div>
                    {t.description && <p className="table-card__desc">{t.description}</p>}
                    <table className="columns-table">
                      <tbody>
                        {Object.entries(t.columns).map(([col, type]) => (
                          <tr key={col}>
                            <td className="columns-table__col">
                              {col}
                              {t.primary_key === col && <span className="columns-table__pk">PK</span>}
                            </td>
                            <td className="columns-table__type">{type}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ))}
              </section>
            )}

            {Object.keys(spec.mermaid_diagrams).length > 0 && (
              <section className="arch__section">
                <h3>Diagrams</h3>
                {Object.entries(spec.mermaid_diagrams).map(([title, def]) => (
                  <MermaidDiagram key={title} title={title} definition={def} />
                ))}
              </section>
            )}

            {spec.adrs.length > 0 && (
              <section className="arch__section">
                <h3>Architecture decision records</h3>
                {spec.adrs.map((adr) => (
                  <details key={adr.adr_id} className="adr">
                    <summary>
                      <span className="adr__id">{adr.adr_id}</span>
                      {adr.title}
                      <span className="adr__status">{adr.status}</span>
                    </summary>
                    <div className="adr__body">
                      <p>
                        <strong>Context:</strong> {adr.context}
                      </p>
                      <p>
                        <strong>Decision:</strong> {adr.decision}
                      </p>
                      <p>
                        <strong>Consequences:</strong> {adr.consequences}
                      </p>
                    </div>
                  </details>
                ))}
              </section>
            )}
          </div>
        )}
      </ReportGate>
    </div>
  );
}
