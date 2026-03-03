'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  Users,
  BarChart3,
  MessageSquare,
  GraduationCap,
  Activity,
  ChevronLeft,
  ChevronRight,
  UserPlus,
  Package,
  CalendarDays,
  BookOpen,
  MessageCircle,
  Shuffle,
  UserCog,
  Ticket,
  PieChart,
  Send,
} from 'lucide-react';
import { useAuth } from '@/lib/AuthContext';

const adminNavItems = [
  { href: '/', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/agents', label: 'Agents', icon: Users },
  { href: '/adm', label: 'ADM Performance', icon: BarChart3 },
  { href: '/feedback-tickets', label: 'Feedback Intelligence', icon: Ticket },
  { href: '/feedback', label: 'Feedback Analytics', icon: MessageSquare },
  { href: '/training', label: 'Training', icon: GraduationCap },
  { href: '/activity', label: 'Live Activity', icon: Activity },
  { href: '/onboarding', label: 'Onboarding', icon: UserPlus },
  { href: '/products', label: 'Products', icon: Package },
  { href: '/assignment', label: 'Assignment', icon: Shuffle },
  { href: '/adm-onboarding', label: 'ADM Onboarding', icon: UserCog },
  { href: '/cohort', label: 'Cohort Analysis', icon: PieChart },
  { href: '/outreach', label: 'Agent Outreach', icon: Send },
];

const admNavItems = [
  { href: '/', label: 'My Dashboard', icon: LayoutDashboard },
  { href: '/my-agents', label: 'My Agents', icon: Users },
  { href: '/planner', label: 'Daily Planner', icon: CalendarDays },
  { href: '/feedback-tickets', label: 'Feedback Tickets', icon: Ticket },
  { href: '/playbooks', label: 'Action Plans', icon: BookOpen },
  { href: '/comms', label: 'Communication Hub', icon: MessageCircle },
  { href: '/training', label: 'Training Center', icon: GraduationCap },
  { href: '/activity', label: 'My Activity', icon: Activity },
];

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const pathname = usePathname();
  const { isAdmin } = useAuth();

  const navItems = isAdmin ? adminNavItems : admNavItems;

  return (
    <aside
      className={`fixed left-0 top-0 h-screen z-40 flex flex-col transition-all duration-300 ease-in-out ${
        collapsed ? 'w-[72px]' : 'w-[240px]'
      }`}
      style={{
        background: 'var(--sidebar-bg)',
        borderRight: '1px solid var(--sidebar-border)',
      }}
    >
      {/* Logo */}
      <div className="flex items-center h-16 px-4 border-b border-surface-border/60">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-9 h-9 rounded-lg bg-brand-red flex items-center justify-center flex-shrink-0">
            <span className="text-white font-bold text-sm">A</span>
          </div>
          {!collapsed && (
            <div className="overflow-hidden">
              <p className="text-white font-bold text-sm leading-tight whitespace-nowrap">
                Axis Max Life
              </p>
              <p className="text-gray-500 text-[10px] leading-tight whitespace-nowrap">
                ADM Platform
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4 px-3 space-y-1 overflow-y-auto">
        {navItems.map((item) => {
          const isActive = pathname === item.href;
          const Icon = item.icon;

          return (
            <Link
              key={item.href}
              href={item.href}
              className={`group flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 relative ${
                isActive
                  ? 'bg-brand-red/10 text-white border border-brand-red/20'
                  : 'text-gray-400 hover:text-white hover:bg-white/5 border border-transparent'
              }`}
              title={collapsed ? item.label : undefined}
            >
              {isActive && (
                <div className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-brand-red rounded-r" />
              )}
              <Icon
                className={`w-5 h-5 flex-shrink-0 transition-colors duration-200 ${
                  isActive ? 'text-brand-red' : 'text-gray-400 group-hover:text-white'
                }`}
              />
              {!collapsed && (
                <span className="text-sm font-medium whitespace-nowrap">{item.label}</span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Collapse Button */}
      <div className="p-3 border-t border-surface-border/60">
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-gray-400 hover:text-white hover:bg-white/5 transition-all duration-200"
        >
          {collapsed ? (
            <ChevronRight className="w-4 h-4" />
          ) : (
            <>
              <ChevronLeft className="w-4 h-4" />
              <span className="text-xs">Collapse</span>
            </>
          )}
        </button>
      </div>
    </aside>
  );
}
