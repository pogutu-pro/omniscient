import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ChatComposer } from '../components/chat/ChatComposer';

const baseProps = {
  hasActivity: false,
  isStreaming: false,
  statusLabel: null,
  onToggleActivity: vi.fn(),
};

describe('ChatComposer', () => {
  it('sends the trimmed message and clears the input on submit', async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<ChatComposer {...baseProps} onSend={onSend} disabled={false} />);

    const textarea = screen.getByLabelText('Message Omniscient');
    await user.type(textarea, '  Find me a hostel  ');
    await user.click(screen.getByLabelText('Send message'));

    expect(onSend).toHaveBeenCalledWith('Find me a hostel');
    expect(textarea).toHaveValue('');
  });

  it('submits on Enter but not on Shift+Enter', async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<ChatComposer {...baseProps} onSend={onSend} disabled={false} />);

    const textarea = screen.getByLabelText('Message Omniscient');
    await user.type(textarea, 'Hello');
    await user.keyboard('{Shift>}{Enter}{/Shift}');
    expect(onSend).not.toHaveBeenCalled();

    await user.keyboard('{Enter}');
    expect(onSend).toHaveBeenCalledWith('Hello');
  });

  it('disables the send button while streaming or when empty', () => {
    render(<ChatComposer {...baseProps} onSend={vi.fn()} disabled={true} isStreaming={true} />);
    expect(screen.getByLabelText('Send message')).toBeDisabled();
  });

  it('hides the mobile status strip until there is activity to show', () => {
    const { rerender } = render(<ChatComposer {...baseProps} onSend={vi.fn()} disabled={false} />);
    expect(screen.queryByLabelText('View activity details')).not.toBeInTheDocument();

    rerender(<ChatComposer {...baseProps} onSend={vi.fn()} disabled={false} hasActivity={true} statusLabel="Checking hostel listings..." />);
    expect(screen.getByLabelText('View activity details')).toBeInTheDocument();
    expect(screen.getByText('Checking hostel listings...')).toBeInTheDocument();
  });
});
