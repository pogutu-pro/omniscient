import { Link } from 'react-router-dom';
import type { CardBlock } from '../../../types';

const BADGE_CLASS: Record<CardBlock['badge_tone'], string> = {
  neutral: 'badge-neutral',
  verified: 'badge-verified',
  warning: 'badge-warning',
  error: 'badge-error',
  info: 'badge-info',
};

export function CardBlockView({ block }: { block: CardBlock }) {
  return (
    <div className="card block-card">
      {block.image_url && <img src={block.image_url} alt="" className="block-card-image" />}
      <div className="block-card-header">
        <div>
          <div className="block-card-title">{block.title}</div>
          {block.subtitle && <div className="block-card-subtitle">{block.subtitle}</div>}
        </div>
        {block.badge && <span className={`badge ${BADGE_CLASS[block.badge_tone]}`}>{block.badge}</span>}
      </div>
      {block.fields.length > 0 && (
        <div className="block-card-fields">
          {block.fields.map((field, idx) => (
            <div key={idx} className="block-card-field">
              <span className="block-card-field-label">{field.label}</span>
              <span className="block-card-field-value">{field.value}</span>
            </div>
          ))}
        </div>
      )}
      {block.actions.length > 0 && (
        <div className="block-card-actions">
          {block.actions.map((action, idx) =>
            action.href.startsWith('/') ? (
              <Link key={idx} to={action.href} className="btn btn-secondary btn-sm">
                {action.label}
              </Link>
            ) : (
              <a key={idx} href={action.href} target="_blank" rel="noreferrer" className="btn btn-secondary btn-sm">
                {action.label}
              </a>
            ),
          )}
        </div>
      )}
    </div>
  );
}
