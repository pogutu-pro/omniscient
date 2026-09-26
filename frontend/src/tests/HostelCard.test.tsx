import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HostelCard } from '../components/housing/HostelCard';
import type { Hostel } from '../types';

const baseHostel: Hostel = {
  id: '1',
  name: 'Boma View Hostel',
  area: 'Boma',
  latitude: null,
  longitude: null,
  distance_from_campus_km: 0.4,
  price_ksh: 6500,
  verified: true,
  amenities: ['wifi', 'water'],
  availability: 'available',
  description: 'Popular hostel near the main gate.',
  contact_phone: null,
  source: 'mock',
  image_key: null,
  image_url: null,
};

const longDescription =
  'All rooms are the same size and of good quality with enough space. The hostel is fully furnished so beds, ' +
  'chairs and other furniture are included in the monthly charge, and there is a shared study area on each floor ' +
  'that students use during the exam season.';

describe('HostelCard', () => {
  it('shows a verified badge for verified listings', () => {
    render(<HostelCard hostel={baseHostel} />);
    expect(screen.getByText('Verified')).toBeInTheDocument();
    expect(screen.getByText('KSh 6,500')).toBeInTheDocument();
  });

  it('marks an unverified listing as unverified without calling live data a demo', () => {
    const { unmount } = render(<HostelCard hostel={{ ...baseHostel, verified: false, source: 'rumia' }} />);
    expect(screen.getByText('Unverified')).toBeInTheDocument();
    expect(screen.queryByText('Unverified demo')).not.toBeInTheDocument();
    unmount();

    render(<HostelCard hostel={{ ...baseHostel, verified: false, source: 'mock' }} />);
    expect(screen.getByText('Unverified demo')).toBeInTheDocument();
  });

  it('reflects availability state', () => {
    render(<HostelCard hostel={{ ...baseHostel, availability: 'full' }} />);
    expect(screen.getByText('Fully booked')).toBeInTheDocument();
  });

  it('collapses a long list of amenities and expands it on request', async () => {
    const user = userEvent.setup();
    render(
      <HostelCard
        hostel={{
          ...baseHostel,
          amenities: ['wifi', 'water', 'security', 'furnished', 'parking', 'gym'],
        }}
      />,
    );

    // Only the first few fit; the rest are summarised rather than pushing
    // the card taller than its neighbours.
    expect(screen.getByText('wifi')).toBeInTheDocument();
    expect(screen.getByText('security')).toBeInTheDocument();
    expect(screen.queryByText('gym')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '+3' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '+3' }));
    expect(screen.getByText('gym')).toBeInTheDocument();
  });

  it('collapses a long description behind a read-more toggle', async () => {
    const user = userEvent.setup();
    render(<HostelCard hostel={{ ...baseHostel, description: longDescription }} />);

    expect(screen.getByRole('button', { name: 'Read more' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Read more' }));
    expect(screen.getByRole('button', { name: 'Show less' })).toBeInTheDocument();
  });

  it('offers no read-more toggle for a short description', () => {
    render(<HostelCard hostel={{ ...baseHostel, description: 'Short and sweet.' }} />);
    expect(screen.queryByRole('button', { name: 'Read more' })).not.toBeInTheDocument();
  });

  it('makes the contact number tappable when one is listed', () => {
    render(<HostelCard hostel={{ ...baseHostel, contact_phone: '+254700100001' }} />);
    expect(screen.getByRole('link', { name: '+254700100001' })).toHaveAttribute('href', 'tel:+254700100001');
  });
});
