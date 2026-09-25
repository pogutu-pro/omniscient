import type { ReactNode } from 'react';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { BottomNav } from './BottomNav';
import './layout.css';

export function AppShell({ children, title }: { children: ReactNode; title: string }) {
  return (
    <div className="app-shell">
      <Sidebar />
      <div className="app-shell-main">
        <TopBar title={title} />
        <main className="app-shell-content">{children}</main>
      </div>
      <BottomNav />
    </div>
  );
}
