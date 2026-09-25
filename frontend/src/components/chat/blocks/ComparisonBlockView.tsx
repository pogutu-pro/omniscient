import type { ComparisonBlock } from '../../../types';
import { CardBlockView } from './CardBlockView';

export function ComparisonBlockView({ block }: { block: ComparisonBlock }) {
  return (
    <div>
      {block.title && <div className="block-title" style={{ marginBottom: 'var(--space-2)' }}>{block.title}</div>}
      <div className="block-comparison-row">
        {block.items.map((item, idx) => (
          <CardBlockView key={idx} block={item} />
        ))}
      </div>
    </div>
  );
}
