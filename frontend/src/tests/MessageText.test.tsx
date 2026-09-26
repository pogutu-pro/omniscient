import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MessageText } from '../components/chat/MessageText';

describe('MessageText', () => {
  it('renders bold and italic instead of showing the asterisks', () => {
    const { container } = render(<MessageText text="This is **important** and *emphasised*." />);
    expect(screen.getByText('important').tagName).toBe('STRONG');
    expect(screen.getByText('emphasised').tagName).toBe('EM');
    expect(container.textContent).not.toContain('*');
  });

  it('renders bullet lines as a real list', () => {
    const { container } = render(<MessageText text={'Options:\n- Boma View\n- Kamakwa Court'} />);
    expect(container.querySelectorAll('li')).toHaveLength(2);
    expect(container.textContent).not.toContain('- Boma');
  });

  it('renders numbered lines as an ordered list', () => {
    const { container } = render(<MessageText text={'Steps:\n1. Register\n2. Pay fees'} />);
    expect(container.querySelectorAll('ol li')).toHaveLength(2);
    expect(container.textContent).not.toContain('1. Register');
  });

  it('renders inline code without the backticks', () => {
    const { container } = render(<MessageText text="Run `npm test` now." />);
    expect(screen.getByText('npm test').tagName).toBe('CODE');
    expect(container.textContent).not.toContain('`');
  });
});
