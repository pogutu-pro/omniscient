import { useState } from 'react';
import type { Hostel } from '../../types';
import { MapPinIcon } from '../common/icons';

const availabilityLabel: Record<string, string> = {
  available: 'Available',
  limited: 'Limited spots',
  full: 'Fully booked',
};

const availabilityTone: Record<string, string> = {
  available: 'badge-verified',
  limited: 'badge-warning',
  full: 'badge-error',
};

/**
 * A listing carries far more than a card can show without becoming a wall of
 * text: agent-written descriptions run to several sentences, and a single
 * hostel can list a dozen amenities. Both are clamped by default and expand
 * in place on request, so the grid stays scannable without any of the
 * information becoming unreachable.
 */
const AMENITIES_COLLAPSED = 3;

/** "0 km" is technically right but reads like missing data. Rumia marks
 *  truly in-campus listings explicitly, so say what it means. */
function distanceLabel(km: number): string {
  if (km <= 0) return 'on campus';
  if (km < 0.1) return `${Math.round(km * 1000)} m`;
  return `${km} km`;
}

export function HostelCard({ hostel }: { hostel: Hostel }) {
  const [showAllAmenities, setShowAllAmenities] = useState(false);
  const [showFullDescription, setShowFullDescription] = useState(false);

  const amenities = hostel.amenities ?? [];
  const hiddenAmenities = Math.max(0, amenities.length - AMENITIES_COLLAPSED);
  const visibleAmenities = showAllAmenities ? amenities : amenities.slice(0, AMENITIES_COLLAPSED);
  const isLongDescription = hostel.description.length > 150;

  return (
    <article className="card hostel-card">
      <div className="hostel-card-media">
        {hostel.image_url ? (
          <img src={hostel.image_url} alt="" className="hostel-card-image" loading="lazy" />
        ) : (
          <div className="hostel-card-image hostel-card-image-placeholder" aria-hidden="true" />
        )}
        <span className={`badge ${availabilityTone[hostel.availability] ?? 'badge-neutral'} hostel-card-status`}>
          {availabilityLabel[hostel.availability] ?? hostel.availability}
        </span>
      </div>

      <div className="hostel-card-body">
        <div className="hostel-card-heading">
          <h3 title={hostel.name}>{hostel.name}</h3>
          {hostel.verified ? (
            <span className="badge badge-verified" title="Verified listing">
              Verified
            </span>
          ) : (
            // "demo" is only true for Omniscient's own seeded data - calling a
            // live Rumia listing a demo listing would misdescribe it.
            <span className="badge badge-neutral">
              {hostel.source === 'rumia' ? 'Unverified' : 'Unverified demo'}
            </span>
          )}
        </div>

        <p className="hostel-card-location">
          <MapPinIcon width={12} height={12} />
          <span className="hostel-card-area">{hostel.area}</span>
          <span className="hostel-card-dot" aria-hidden="true">
            &middot;
          </span>
          <span>{distanceLabel(hostel.distance_from_campus_km)}</span>
        </p>

        {hostel.description && (
          <p className={`hostel-card-description${showFullDescription ? ' is-expanded' : ''}`}>
            {hostel.description}
          </p>
        )}

        {isLongDescription && (
          <button type="button" className="hostel-card-link" onClick={() => setShowFullDescription((v) => !v)}>
            {showFullDescription ? 'Show less' : 'Read more'}
          </button>
        )}

        {amenities.length > 0 && (
          <div className="hostel-card-amenities">
            {/* The badge list is clipped and faded; the "+N" control sits
                outside it so the affordance itself is never faded out. */}
            <div className="hostel-card-amenities-list">
              {visibleAmenities.map((a) => (
                <span key={a} className="badge badge-neutral">
                  {a}
                </span>
              ))}
            </div>
            {hiddenAmenities > 0 && (
              <button
                type="button"
                className="badge badge-neutral hostel-card-more"
                onClick={() => setShowAllAmenities((v) => !v)}
                aria-expanded={showAllAmenities}
              >
                {showAllAmenities ? 'Fewer' : `+${hiddenAmenities}`}
              </button>
            )}
          </div>
        )}
      </div>

      <div className="hostel-card-footer">
        <div className="hostel-card-price">
          {/* Same "KSh 8,000" shape the chat table renders, so a price read
              in a chat answer matches the card it came from. */}
          <span className="hostel-price">KSh {hostel.price_ksh.toLocaleString()}</span>
          <span className="hostel-price-unit">/month</span>
        </div>
        {hostel.contact_phone && (
          <a className="hostel-card-contact" href={`tel:${hostel.contact_phone}`}>
            {hostel.contact_phone}
          </a>
        )}
      </div>
    </article>
  );
}
