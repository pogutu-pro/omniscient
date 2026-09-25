import type { Hostel } from '../../types';
import { MapPinIcon } from '../common/icons';

const availabilityLabel: Record<string, string> = {
  available: 'Available',
  limited: 'Limited spots',
  full: 'Fully booked',
};

export function HostelCard({ hostel }: { hostel: Hostel }) {
  return (
    <div className="card hostel-card">
      <div className="hostel-card-header">
        <div>
          <h3>{hostel.name}</h3>
          <p className="hostel-card-location">
            <MapPinIcon width={14} height={14} />
            {hostel.area} &middot; {hostel.distance_from_campus_km} km from campus
          </p>
        </div>
        {hostel.verified ? (
          <span className="badge badge-verified">Verified</span>
        ) : (
          <span className="badge badge-neutral">Unverified demo listing</span>
        )}
      </div>

      <p className="hostel-card-description">{hostel.description}</p>

      <div className="hostel-card-amenities">
        {hostel.amenities.map((a) => (
          <span key={a} className="badge badge-neutral">
            {a}
          </span>
        ))}
      </div>

      <div className="hostel-card-footer">
        <div>
          <span className="hostel-price">KSh {hostel.price_ksh.toLocaleString()}</span>
          <span className="hostel-price-unit">/month</span>
        </div>
        <span
          className={`badge ${hostel.availability === 'available' ? 'badge-verified' : hostel.availability === 'limited' ? 'badge-warning' : 'badge-error'}`}
        >
          {availabilityLabel[hostel.availability] ?? hostel.availability}
        </span>
      </div>
    </div>
  );
}
