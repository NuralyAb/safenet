import type { Report } from "../../api/client";
import { RiskGauge } from "./RiskGauge";
import { CheckIcon } from "../../components/icons";

export function RiskReport({ report }: { report: Report }) {
  const { accounts, sites, wallets } = report.links;
  return (
    <div className="report fade-in">
      <div className="report-top">
        <RiskGauge score={report.risk_score} level={report.threat_level} />
        <div className="report-meta">
          <div className="eyebrow">Target</div>
          <div className="target">{report.target}</div>
          <div className="row">
            <span className={`badge threat ${report.threat_level}`}>{report.threat_level}</span>
            <span className="badge">{report.category}</span>
          </div>
        </div>
      </div>

      <div className="stat-grid">
        <div className="stat">
          <b style={{ color: "var(--node-account)" }}>{accounts}</b>
          <span>Accounts</span>
        </div>
        <div className="stat">
          <b style={{ color: "var(--node-infra)" }}>{sites}</b>
          <span>Sites</span>
        </div>
        <div className="stat">
          <b style={{ color: "var(--node-wallet)" }}>{wallets}</b>
          <span>Wallets</span>
        </div>
      </div>

      <div>
        <div className="eyebrow" style={{ marginBottom: 10 }}>
          Key findings · {report.findings.length}
        </div>
        <ul className="findings">
          {report.findings.map((f, i) => (
            <li key={i}>
              <CheckIcon size={16} className="mk" />
              <span>{f}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
