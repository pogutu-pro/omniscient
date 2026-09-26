import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TimetableView } from '../components/academics/TimetableView';
import type { TimetableEntry } from '../types';

function entry(overrides: Partial<TimetableEntry>): TimetableEntry {
  return {
    id: overrides.id ?? '1',
    course_id: 'c1',
    course_code: 'SCS 2101',
    course_name: 'Database Systems',
    day_of_week: 0,
    start_time: '08:00',
    end_time: '10:00',
    venue: 'Block C - LT1',
    session_type: 'lecture',
    ...overrides,
  };
}

describe('TimetableView', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows an empty state with no entries', () => {
    render(<TimetableView entries={[]} />);
    expect(screen.getByText(/no timetable entries/i)).toBeInTheDocument();
  });

  it('marks the current weekday as Today and the in-progress class as Now', () => {
    // 2026-09-28 is a Monday; 09:00 falls inside the 08:00-10:00 entry.
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-09-28T09:00:00'));

    render(
      <TimetableView
        entries={[
          entry({ id: '1', day_of_week: 0, start_time: '08:00', end_time: '10:00' }),
          entry({ id: '2', day_of_week: 1, start_time: '08:00', end_time: '10:00', course_code: 'SCS 3110' }),
        ]}
      />,
    );

    expect(screen.getByText('Today')).toBeInTheDocument();
    expect(screen.getByText('Now')).toBeInTheDocument();
    // Tuesday's entry (day_of_week 1) is a different day and must not be marked.
    const tuesdayCard = screen.getByText('SCS 3110').closest('.timetable-entry');
    expect(tuesdayCard).not.toHaveClass('is-now');
  });

  it('does not mark anything when the current day has no entries', () => {
    // 2026-09-26 is a Saturday; the only entry is on Monday.
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-09-26T09:00:00'));

    render(<TimetableView entries={[entry({ day_of_week: 0 })]} />);

    expect(screen.queryByText('Today')).not.toBeInTheDocument();
    expect(screen.queryByText('Now')).not.toBeInTheDocument();
  });

  it('does not mark a class on today that has not started or has already ended', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-09-28T07:00:00')); // before the 08:00 start

    render(<TimetableView entries={[entry({ day_of_week: 0, start_time: '08:00', end_time: '10:00' })]} />);

    expect(screen.getByText('Today')).toBeInTheDocument();
    expect(screen.queryByText('Now')).not.toBeInTheDocument();
  });
});
