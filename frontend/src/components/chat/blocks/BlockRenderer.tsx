import type { ContentBlock } from '../../../types';
import { CardBlockView } from './CardBlockView';
import { ChartBlockView } from './ChartBlockView';
import { ComparisonBlockView } from './ComparisonBlockView';
import { FileBlockView } from './FileBlockView';
import { ImageBlockView } from './ImageBlockView';
import { ListBlockView } from './ListBlockView';
import { TableBlockView } from './TableBlockView';
import './blocks.css';

/** The single dispatch point from a block's `type` to its renderer - a
 * fixed, closed set (see types/index.ts:ContentBlock). An unrecognised
 * type renders nothing rather than guessing at a fallback presentation. */
export function BlockRenderer({ blocks }: { blocks: ContentBlock[] }) {
  if (!blocks || blocks.length === 0) return null;
  return (
    <div className="block-stack">
      {blocks.map((block, idx) => {
        switch (block.type) {
          case 'table':
            return <TableBlockView key={idx} block={block} />;
          case 'list':
            return <ListBlockView key={idx} block={block} />;
          case 'card':
            return <CardBlockView key={idx} block={block} />;
          case 'comparison':
            return <ComparisonBlockView key={idx} block={block} />;
          case 'file':
            return <FileBlockView key={idx} block={block} />;
          case 'image':
            return <ImageBlockView key={idx} block={block} />;
          case 'chart':
            return <ChartBlockView key={idx} block={block} />;
          default:
            return null;
        }
      })}
    </div>
  );
}
