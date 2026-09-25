import type { ReactNode } from 'react';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { BottomNav } from './BottomNav';
import './layout.css';

interface Props {
  children: ReactNode;
  title: string;
  /** Desktop-only contextual right panel (e.g. the chat activity trace).
   * Rendered inside the same structural row as the sidebar and main
   * content so its border lines meet theirs under one continuous navbar,
   * rather than floating as a separate block. Pass nothing to let main
   * content use the full remaining width. */
  rightPanel?: ReactNode;
}

export function AppShell({ children, title, rightPanel }: Props) {
  return (
    <div className="app-shell">
      <TopBar title={title} />
      <div className="app-shell-body">
        <Sidebar />
        <main className="app-shell-content">{children}</main>
        {rightPanel}
      </div>
      <BottomNav />
    </div>
  );
}
