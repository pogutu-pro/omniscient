import { NavLink } from 'react-router-dom';
import { AcademicsIcon, ComplaintsIcon, HomeIcon, HousingIcon, PapersIcon } from '../common/icons';

const items = [
  { to: '/', label: 'Home', icon: HomeIcon, end: true },
  { to: '/housing', label: 'Housing', icon: HousingIcon, end: false },
  { to: '/academics', label: 'Academics', icon: AcademicsIcon, end: false },
  { to: '/past-papers', label: 'Papers', icon: PapersIcon, end: false },
  { to: '/complaints', label: 'More', icon: ComplaintsIcon, end: false },
];

export function BottomNav() {
  return (
    <nav className="bottom-nav" aria-label="Primary">
      {items.map(({ to, label, icon: Icon, end }) => (
        <NavLink key={to} to={to} end={end} className={({ isActive }) => `bottom-nav-link${isActive ? ' active' : ''}`}>
          <Icon />
          {label}
        </NavLink>
      ))}
    </nav>
  );
}
