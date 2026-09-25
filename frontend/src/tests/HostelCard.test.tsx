import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
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

describe('HostelCard', () => {
  it('shows a verified badge for verified listings', () => {
    render(<HostelCard hostel={baseHostel} />);
    expect(screen.getByText('Verified')).toBeInTheDocument();
    expect(screen.getByText('KSh 6,500')).toBeInTheDocument();
  });

  it('shows an unverified demo listing badge otherwise', () => {
    render(<HostelCard hostel={{ ...baseHostel, verified: false }} />);
    expect(screen.getByText('Unverified demo listing')).toBeInTheDocument();
  });

  it('reflects availability state', () => {
    render(<HostelCard hostel={{ ...baseHostel, availability: 'full' }} />);
    expect(screen.getByText('Fully booked')).toBeInTheDocument();
  });
});
