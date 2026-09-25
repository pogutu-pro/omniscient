import type { ImageBlock } from '../../../types';

export function ImageBlockView({ block }: { block: ImageBlock }) {
  return (
    <div className="block-image-wrap">
      <img src={block.url} alt={block.alt} className="block-image" />
      {block.caption && <div className="block-image-caption">{block.caption}</div>}
    </div>
  );
}
