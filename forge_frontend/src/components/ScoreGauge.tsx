/** A 0-100 score as a labeled bar. goodDirection "up" = higher is better (quality),
 * "down" = lower is better (risk). */
export function ScoreGauge({
  label,
  value,
  goodDirection = "up",
}: {
  label: string;
  value: number;
  goodDirection?: "up" | "down";
}) {
  const pct = Math.max(0, Math.min(100, value));
  const good = goodDirection === "up" ? pct >= 70 : pct <= 30;
  const bad = goodDirection === "up" ? pct < 40 : pct > 60;
  const tone = good ? "good" : bad ? "bad" : "warn";

  return (
    <div className="score-gauge">
      <div className="score-gauge__top">
        <span className="score-gauge__label">{label}</span>
        <span className={`score-gauge__value score-gauge__value--${tone}`}>{value.toFixed(0)}</span>
      </div>
      <div className="score-gauge__track">
        <div className={`score-gauge__fill score-gauge__fill--${tone}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
