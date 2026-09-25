import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ExecutionTrace } from '../components/chat/ExecutionTrace';
import type { TraceEvent } from '../types';

describe('ExecutionTrace', () => {
  it('shows a placeholder when there are no events', () => {
    render(<ExecutionTrace events={[]} isStreaming={false} />);
    expect(screen.getByText(/Activity from your next message/)).toBeInTheDocument();
  });

  it('renders status, tool_call, and tool_result steps with their labels', () => {
    const events: TraceEvent[] = [
      { type: 'status', message: 'Checking hostel listings near campus...' },
      { type: 'tool_call', tool: 'search_hostels', status: 'running', message: 'Filtering hostels...' },
      { type: 'tool_result', tool: 'search_hostels', status: 'completed', summary: 'Found 3 matching hostels.' },
    ];
    render(<ExecutionTrace events={events} isStreaming={false} />);

    expect(screen.getByText('Checking hostel listings near campus...')).toBeInTheDocument();
    expect(screen.getByText('Filtering hostels...')).toBeInTheDocument();
    expect(screen.getByText('Found 3 matching hostels.')).toBeInTheDocument();
    expect(screen.getByText('search_hostels')).toBeInTheDocument();
  });

  it('never renders raw answer_chunk or done events as trace steps', () => {
    const events: TraceEvent[] = [
      { type: 'answer_chunk', message: 'This should not appear as a step' },
      { type: 'done', data: { intent: 'housing' } },
    ];
    render(<ExecutionTrace events={events} isStreaming={false} />);
    expect(screen.queryByText('This should not appear as a step')).not.toBeInTheDocument();
  });

  it('shows a writing indicator while streaming', () => {
    render(<ExecutionTrace events={[{ type: 'status', message: 'Thinking...' }]} isStreaming={true} />);
    expect(screen.getByText('Writing a response...')).toBeInTheDocument();
  });
});
