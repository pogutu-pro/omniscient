import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { BlockRenderer } from '../components/chat/blocks/BlockRenderer';
import type { ContentBlock } from '../types';

function renderBlocks(blocks: ContentBlock[]) {
  return render(
    <MemoryRouter>
      <BlockRenderer blocks={blocks} />
    </MemoryRouter>,
  );
}

describe('BlockRenderer', () => {
  it('renders nothing for an empty list', () => {
    const { container } = renderBlocks([]);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders a table block with rows', () => {
    renderBlocks([
      {
        type: 'table',
        title: 'Hostels near campus',
        columns: [
          { key: 'name', label: 'Name', align: 'left' },
          { key: 'price', label: 'Price', align: 'right' },
        ],
        rows: [{ name: 'Boma View Hostel', price: 'KSh 6,500' }],
      },
    ]);
    expect(screen.getByText('Hostels near campus')).toBeInTheDocument();
    expect(screen.getByText('Boma View Hostel')).toBeInTheDocument();
    expect(screen.getByText('KSh 6,500')).toBeInTheDocument();
  });

  it('renders a list block with badges', () => {
    renderBlocks([
      {
        type: 'list',
        items: [{ title: 'Fee clearance', description: 'Clear at least 60%', meta: '2027-01-01', badge: 'fees' }],
      },
    ]);
    expect(screen.getByText('Fee clearance')).toBeInTheDocument();
    expect(screen.getByText('fees')).toBeInTheDocument();
  });

  it('renders a card block with fields, badge and an internal action link', () => {
    renderBlocks([
      {
        type: 'card',
        title: 'Complaint filed',
        subtitle: 'Maintenance',
        badge: 'submitted',
        badge_tone: 'info',
        fields: [{ label: 'Reference', value: 'OMN-ABC123' }],
        actions: [{ label: 'File a complaint', href: '/complaints' }],
      },
    ]);
    expect(screen.getByText('Complaint filed')).toBeInTheDocument();
    expect(screen.getByText('OMN-ABC123')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'File a complaint' })).toHaveAttribute('href', '/complaints');
  });

  it('renders a comparison block as multiple cards', () => {
    renderBlocks([
      {
        type: 'comparison',
        items: [
          { type: 'card', title: 'Hostel A', badge_tone: 'neutral', fields: [], actions: [] },
          { type: 'card', title: 'Hostel B', badge_tone: 'neutral', fields: [], actions: [] },
        ],
      },
    ]);
    expect(screen.getByText('Hostel A')).toBeInTheDocument();
    expect(screen.getByText('Hostel B')).toBeInTheDocument();
  });

  it('renders a file block with a download link', () => {
    renderBlocks([
      {
        type: 'file',
        files: [{ name: 'scs2101.pdf', url: 'http://x/download', kind: 'pdf', description: 'SCS 2101 · 2023/2024' }],
      },
    ]);
    const link = screen.getByRole('link', { name: /scs2101\.pdf/ });
    expect(link).toHaveAttribute('href', 'http://x/download');
  });

  it('renders an image block with caption', () => {
    renderBlocks([{ type: 'image', url: 'http://x/photo.png', alt: 'photo', caption: 'Uploaded photo' }]);
    expect(screen.getByAltText('photo')).toHaveAttribute('src', 'http://x/photo.png');
    expect(screen.getByText('Uploaded photo')).toBeInTheDocument();
  });

  it('renders a chart block with bars sized relative to the max value', () => {
    renderBlocks([
      {
        type: 'chart',
        chart_type: 'bar',
        unit: 'KSh/month',
        series: [
          { label: 'Hostel A', value: 5000 },
          { label: 'Hostel B', value: 10000 },
        ],
      },
    ]);
    expect(screen.getByText('Hostel A')).toBeInTheDocument();
    expect(screen.getByText('10,000 KSh/month')).toBeInTheDocument();
  });
});
