import type { AcademicTerm } from '../../types';

interface AcademicCalendarViewProps {
  terms: AcademicTerm[];
  currentAcademicYear?: string;
  currentTrimester?: number;
}

export function AcademicCalendarView({
  terms,
  currentAcademicYear,
  currentTrimester,
}: AcademicCalendarViewProps) {
  // Sort terms by trimester order (1, 2, 3)
  const sortedTerms = [...terms].sort((a, b) => a.trimester - b.trimester);

  const currentTerm = terms.find((t) => t.trimester === currentTrimester);

  const getTrimesterPeriod = (trimester: number): string => {
    switch (trimester) {
      case 1:
        return 'January – April';
      case 2:
        return 'May – August';
      case 3:
        return 'September – December';
      default:
        return '';
    }
  };

  const formatDate = (dateStr?: string | null): string => {
    if (!dateStr) return 'To be announced';
    try {
      const d = new Date(dateStr);
      return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
    } catch {
      return dateStr;
    }
  };

  return (
    <div className="academic-structure-view">
      <div className="card academic-overview-card">
        <div className="academic-overview-header">
          <div>
            <h2>DeKUT Trimester Structure</h2>
            <p className="academic-overview-description">
              Dedan Kimathi University of Technology (DeKUT) operates on a <strong>trimester system</strong> with its academic
              year starting in September and divided into three semesters of roughly four months each.
            </p>
          </div>
          {currentTrimester && (
            <div className="current-term-badge">
              <span className="pulse-dot" />
              <span>
                Semester {currentTrimester} Active ({currentAcademicYear ?? 'Current Year'})
              </span>
            </div>
          )}
        </div>

        {currentTerm && (
          <div className="current-term-highlight">
            <div className="current-term-info">
              <span className="current-term-label">CURRENT TRIMESTER</span>
              <h3 className="current-term-title">
                {currentTerm.label || `Semester ${currentTerm.trimester}`} &middot; {getTrimesterPeriod(currentTerm.trimester)}
              </h3>
              <p className="current-term-dates">
                <span>Period: {formatDate(currentTerm.start_date)} &ndash; {formatDate(currentTerm.end_date)}</span>
                {currentTerm.reporting_date && (
                  <span> &bull; Reporting Date: <strong>{formatDate(currentTerm.reporting_date)}</strong></span>
                )}
              </p>
            </div>
            {currentTerm.provisional && (
              <span className="badge badge-warning" title="Subject to confirmation with department notices">
                Provisional Dates
              </span>
            )}
          </div>
        )}
      </div>

      <h3 className="section-title">Academic Year Schedule ({currentAcademicYear ?? '2026/2027'})</h3>

      <div className="trimester-grid">
        {sortedTerms.map((term) => {
          const isCurrent = term.trimester === currentTrimester;
          const period = getTrimesterPeriod(term.trimester);

          return (
            <div
              key={term.id || `${term.academic_year}-${term.trimester}`}
              className={`card trimester-card${isCurrent ? ' trimester-card-active' : ''}`}
            >
              <div className="trimester-card-header">
                <div>
                  <span className="trimester-number">SEMESTER {term.trimester}</span>
                  <h4 className="trimester-title">{term.label || `Semester ${term.trimester}`}</h4>
                  <p className="trimester-period">{period}</p>
                </div>
                {isCurrent && <span className="badge badge-verified">Running Now</span>}
              </div>

              <div className="trimester-card-body">
                <div className="trimester-detail-row">
                  <span className="detail-label">Start Date:</span>
                  <span className="detail-value">{formatDate(term.start_date)}</span>
                </div>
                <div className="trimester-detail-row">
                  <span className="detail-label">End Date:</span>
                  <span className="detail-value">{formatDate(term.end_date)}</span>
                </div>
                <div className="trimester-detail-row">
                  <span className="detail-label">Reporting Date:</span>
                  <span className="detail-value">
                    {term.reporting_date ? formatDate(term.reporting_date) : 'Announced per cohort'}
                  </span>
                </div>
                {term.notes && <p className="trimester-notes">{term.notes}</p>}
              </div>

              <div className="trimester-card-footer">
                <span className={`badge ${term.provisional ? 'badge-neutral' : 'badge-verified'}`}>
                  {term.provisional ? 'Published Plan' : 'Confirmed'}
                </span>
                <span className="trimester-duration">~4 Months</span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="card calendar-notice-box">
        <h4>Important Note on Reporting &amp; Resumption</h4>
        <p>
          While the general academic calendar runs on the three trimesters above, actual reporting, unit registration, and
          resumption dates vary by <strong>school, department, programme, intake, and year of study</strong>. Dates are
          confirmed by departmental notices and the Registrar&apos;s office.
        </p>
      </div>
    </div>
  );
}
