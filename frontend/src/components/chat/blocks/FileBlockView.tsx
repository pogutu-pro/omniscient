import type { FileBlock, FileItem } from '../../../types';
import { DownloadIcon, GenericFileIcon, ImageFileIcon, PapersIcon } from '../../common/icons';

const ICON_BY_KIND: Record<FileItem['kind'], typeof PapersIcon> = {
  pdf: PapersIcon,
  image: ImageFileIcon,
  document: GenericFileIcon,
  other: GenericFileIcon,
};

export function FileBlockView({ block }: { block: FileBlock }) {
  return (
    <div>
      {block.title && <div className="block-title" style={{ marginBottom: 'var(--space-2)' }}>{block.title}</div>}
      <div className="block-file-list">
        {block.files.map((file, idx) => {
          const Icon = ICON_BY_KIND[file.kind];
          return (
            <a key={idx} href={file.url} target="_blank" rel="noreferrer" className="block-file-item">
              <span className="block-file-icon">
                <Icon size={18} />
              </span>
              <span className="block-file-info">
                <span className="block-file-name">{file.name}</span>
                {file.description && <span className="block-file-description">{file.description}</span>}
              </span>
              <DownloadIcon size={16} />
            </a>
          );
        })}
      </div>
    </div>
  );
}
