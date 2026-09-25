import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ChatComposer } from '../components/chat/ChatComposer';
import { uploadFile } from '../api/client';

vi.mock('../api/client', () => ({
  uploadFile: vi.fn(),
}));

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

  it('uploads an attached image and sends it alongside the message', async () => {
    vi.mocked(uploadFile).mockResolvedValue({
      key: 'uploads/student-1/abc123.png',
      url: 'http://localhost:8000/api/files/uploads/student-1/abc123.png',
    });
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<ChatComposer {...baseProps} onSend={onSend} disabled={false} />);

    const file = new File(['fake-bytes'], 'hostel-photo.png', { type: 'image/png' });
    const input = screen.getByLabelText('Attach a file', { selector: 'input' });
    await user.upload(input, file);

    await waitFor(() => expect(screen.getByText('hostel-photo.png')).toBeInTheDocument());
    expect(uploadFile).toHaveBeenCalledWith(file);

    await user.type(screen.getByLabelText('Message Omniscient'), 'What do you think of this hostel?');
    await user.click(screen.getByLabelText('Send message'));

    expect(onSend).toHaveBeenCalledWith('What do you think of this hostel?', [
      {
        key: 'uploads/student-1/abc123.png',
        content_type: 'image/png',
        file_name: 'hostel-photo.png',
        url: 'http://localhost:8000/api/files/uploads/student-1/abc123.png',
      },
    ]);
  });

  it('disables the send button while an attachment is still uploading', async () => {
    let resolveUpload: (value: { key: string; url: string }) => void = () => {};
    vi.mocked(uploadFile).mockReturnValue(
      new Promise((resolve) => {
        resolveUpload = resolve;
      }),
    );
    const user = userEvent.setup();
    render(<ChatComposer {...baseProps} onSend={vi.fn()} disabled={false} />);

    const file = new File(['fake-bytes'], 'notes.pdf', { type: 'application/pdf' });
    const input = screen.getByLabelText('Attach a file', { selector: 'input' });
    await user.upload(input, file);

    await user.type(screen.getByLabelText('Message Omniscient'), 'See attached');
    expect(screen.getByLabelText('Send message')).toBeDisabled();

    resolveUpload({ key: 'uploads/x.pdf', url: 'http://localhost:8000/api/files/uploads/x.pdf' });
    await waitFor(() => expect(screen.getByLabelText('Send message')).not.toBeDisabled());
  });
});
