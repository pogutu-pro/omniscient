import type { PastPaper } from '../../types';
import { PapersIcon } from '../common/icons';

export function PastPaperList({ papers }: { papers: PastPaper[] }) {
  if (papers.length === 0) {
    return (
      <div className="empty-state">
        <p>No past papers matched your search. Try a unit code like "SCS 2101".</p>
      </div>
    );
  }

  return (
    <div className="paper-list">
      {papers.map((paper) => (
        <a key={paper.id} className="card paper-card" href={paper.download_url} target="_blank" rel="noreferrer">
          <PapersIcon width={20} height={20} />
          <div className="paper-card-body">
            <p className="paper-card-title">
              {paper.course_code} &middot; {paper.course_name}
            </p>
            <p className="paper-card-meta">
              {paper.academic_year} &middot; Semester {paper.semester} &middot; {paper.exam_type}
            </p>
          </div>
          <span className="badge badge-info">Download</span>
        </a>
      ))}
    </div>
  );
}
