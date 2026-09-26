import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ExecutionTrace } from '../components/chat/ExecutionTrace';
import type { TraceEvent } from '../types';

const events: TraceEvent[] = [
  { type: 'status', message: 'Reading your message...', data: { provider: 'Mock Assistant' }, receivedAt: 1 },
  {
    type: 'status',
    message: 'Checking hostel listings near campus...',
    data: { intent: 'housing', confidence: 0.85 },
    receivedAt: 2,
  },
  {
    type: 'tool_call',
    tool: 'search_hostels',
    status: 'running',
    message: 'Filtering hostels by your budget and area...',
    arguments: { max_budget_ksh: 8000, area: 'Boma' },
    receivedAt: 3,
  },
  {
    type: 'tool_result',
    tool: 'search_hostels',
    status: 'completed',
    summary: 'Found 10 matching hostels.',
    duration_ms: 412,
    receivedAt: 4,
  },
  {
    type: 'content_block',
    tool: 'search_hostels',
    data: { type: 'table', title: 'Hostels near campus', rows: [{ name: 'A' }, { name: 'B' }] } as never,
    receivedAt: 5,
  },
];

describe('ExecutionTrace', () => {
  it('explains itself when there is nothing to show', () => {
    render(<ExecutionTrace events={[]} isStreaming={false} isWriting={false} />);
    expect(screen.getByText('No activity yet')).toBeInTheDocument();
  });

  it('groups steps into the three phases a person recognises', () => {
    render(<ExecutionTrace events={events} isStreaming={false} isWriting={false} />);
    expect(screen.getByText('Understanding your question')).toBeInTheDocument();
    expect(screen.getByText('Finding the answer')).toBeInTheDocument();
  });

  it('shows what was searched for, not just that a search ran', () => {
    render(<ExecutionTrace events={events} isStreaming={false} isWriting={false} />);
    expect(screen.getByText('max budget')).toBeInTheDocument();
    expect(screen.getByText('KSh 8,000')).toBeInTheDocument();
    expect(screen.getByText('area')).toBeInTheDocument();
    expect(screen.getByText('Boma')).toBeInTheDocument();
  });

  it('shows the confidence the router assigned', () => {
    render(<ExecutionTrace events={events} isStreaming={false} isWriting={false} />);
    expect(screen.getByText('read as')).toBeInTheDocument();
    expect(screen.getByText('housing')).toBeInTheDocument();
    expect(screen.getByText('85%')).toBeInTheDocument();
  });

  it('shows how long each step took, and how long the phase took in total', () => {
    const { container } = render(<ExecutionTrace events={events} isStreaming={false} isWriting={false} />);
    expect(container.querySelector('.trace-item-duration')?.textContent).toBe('412ms');
    expect(container.querySelector('.trace-group-duration')?.textContent).toBe('412ms');
  });

  it('merges a tool call and its result into one step that states the outcome', () => {
    render(<ExecutionTrace events={events} isStreaming={false} isWriting={false} />);
    // The attempt and its outcome are one piece of work, so one row.
    expect(screen.getByText('Filtering hostels by your budget and area...')).toBeInTheDocument();
    expect(screen.getByText('Found 10 matching hostels.')).toBeInTheDocument();
    expect(screen.getAllByRole('listitem')).toHaveLength(3);
  });

  it('describes the rich content it rendered instead of leaving a blank row', () => {
    render(<ExecutionTrace events={events} isStreaming={false} isWriting={false} />);
    expect(screen.getByText('Built a results table')).toBeInTheDocument();
    // A blank label is exactly what the previous renderer produced for these
    // frames, so assert none of the rendered steps has an empty one.
    const labels = [...document.querySelectorAll('.trace-item-label')].map((el) => el.textContent?.trim());
    expect(labels.length).toBeGreaterThan(0);
    expect(labels.every((l) => l && l.length > 0)).toBe(true);
  });

  it('never renders raw answer_chunk or done events as trace steps', () => {
    render(
      <ExecutionTrace
        events={[
          { type: 'answer_chunk', message: 'This should not appear as a step' },
          { type: 'done', data: { intent: 'housing' } },
        ]}
        isStreaming={false}
        isWriting={false}
      />,
    );
    expect(screen.queryByText('This should not appear as a step')).not.toBeInTheDocument();
  });

  it('shows a writing step once the answer starts streaming', () => {
    render(<ExecutionTrace events={events} isStreaming={true} isWriting={true} />);
    expect(screen.getByText('Writing the reply')).toBeInTheDocument();
    expect(screen.getByText('Composing the answer')).toBeInTheDocument();
  });

  it('shows no writing step before the answer has started', () => {
    render(<ExecutionTrace events={events} isStreaming={true} isWriting={false} />);
    expect(screen.queryByText('Composing the answer')).not.toBeInTheDocument();
  });

  it('marks a failed step as failed and keeps the reason visible', () => {
    render(
      <ExecutionTrace
        events={[
          { type: 'tool_call', tool: 'file_complaint', status: 'running', message: 'Filing your complaint...' },
          { type: 'tool_result', tool: 'file_complaint', status: 'failed', summary: 'You need to be signed in.' },
        ]}
        isStreaming={false}
        isWriting={false}
      />,
    );
    expect(screen.getByText('You need to be signed in.')).toBeInTheDocument();
  });

  it('surfaces a stream error as a step', () => {
    render(
      <ExecutionTrace events={[{ type: 'error', message: 'I could not reach the listings service.' }]} isStreaming={false} isWriting={false} />,
    );
    expect(screen.getByText('I could not reach the listings service.')).toBeInTheDocument();
  });
});
