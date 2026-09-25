import type { TableBlock } from '../../../types';

export function TableBlockView({ block }: { block: TableBlock }) {
  return (
    <div>
      {block.title && <div className="block-title" style={{ marginBottom: 'var(--space-2)' }}>{block.title}</div>}
      <div className="block-table-wrap">
        <table className="block-table">
          <thead>
            <tr>
              {block.columns.map((col) => (
                <th key={col.key} className={col.align === 'right' ? 'align-right' : undefined}>
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {block.rows.map((row, idx) => (
              <tr key={idx}>
                {block.columns.map((col) => (
                  <td key={col.key} className={col.align === 'right' ? 'align-right' : undefined}>
                    {row[col.key] ?? ''}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
