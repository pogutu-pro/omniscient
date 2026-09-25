import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ComplaintForm } from '../components/complaints/ComplaintForm';

describe('ComplaintForm', () => {
  it('rejects a description that is too short instead of calling onSubmit', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<ComplaintForm onSubmit={onSubmit} submitting={false} />);

    await user.type(screen.getByLabelText("What's wrong?"), 'too short');
    await user.click(screen.getByText('File complaint'));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText(/at least 10 characters/)).toBeInTheDocument();
  });

  it('submits category, details, and location when valid', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<ComplaintForm onSubmit={onSubmit} submitting={false} />);

    await user.selectOptions(screen.getByLabelText('Category'), 'security');
    await user.type(screen.getByLabelText('Location (optional)'), 'Main gate');
    await user.type(screen.getByLabelText("What's wrong?"), 'Suspicious person loitering near the gate at night');
    await user.click(screen.getByText('File complaint'));

    expect(onSubmit).toHaveBeenCalledWith({
      category: 'security',
      details: 'Suspicious person loitering near the gate at night',
      location: 'Main gate',
    });
  });

  it('disables the submit button while submitting', () => {
    render(<ComplaintForm onSubmit={vi.fn()} submitting={true} />);
    expect(screen.getByText('Filing complaint...')).toBeDisabled();
  });
});
