import type { ChartBlock } from '../../../types';

// A handful of comparison bars doesn't justify pulling in a charting
// library - this is plain CSS (bar width as a percentage of the max
// value), which keeps it dependency-free, fast, and on-brand.
export function ChartBlockView({ block }: { block: ChartBlock }) {
  const max = Math.max(...block.series.map((s) => s.value), 1);
  return (
    <div>
      {block.title && <div className="block-title" style={{ marginBottom: 'var(--space-2)' }}>{block.title}</div>}
      <div className="block-chart">
        {block.series.map((item, idx) => (
          <div key={idx} className="block-chart-row">
            <span className="block-chart-label">{item.label}</span>
            <span className="block-chart-track">
              <span className="block-chart-bar" style={{ width: `${(item.value / max) * 100}%` }} />
            </span>
            <span className="block-chart-value">
              {item.value.toLocaleString()}
              {block.unit ? ` ${block.unit}` : ''}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
