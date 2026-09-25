import type { ListBlock } from '../../../types';

export function ListBlockView({ block }: { block: ListBlock }) {
  return (
    <div>
      {block.title && <div className="block-title" style={{ marginBottom: 'var(--space-2)' }}>{block.title}</div>}
      <div className="block-list">
        {block.items.map((item, idx) => (
          <div key={idx} className="block-list-item">
            <div>
              <div className="block-list-item-title">{item.title}</div>
              {item.description && <div className="block-list-item-description">{item.description}</div>}
            </div>
            {(item.meta || item.badge) && (
              <div className="block-list-item-meta">
                {item.badge && <span className="badge badge-neutral">{item.badge}</span>}
                {item.meta && <span>{item.meta}</span>}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
