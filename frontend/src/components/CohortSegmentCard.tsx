'use client';

import { Phone, MessageCircle, Send, XCircle } from 'lucide-react';

const SEGMENT_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  promising_rookies:      { bg: 'bg-emerald-500/10', border: 'border-emerald-500/20', text: 'text-emerald-400' },
  stalled_starters:       { bg: 'bg-amber-500/10', border: 'border-amber-500/20', text: 'text-amber-400' },
  sleeping_giants:        { bg: 'bg-blue-500/10', border: 'border-blue-500/20', text: 'text-blue-400' },
  fading_stars:           { bg: 'bg-orange-500/10', border: 'border-orange-500/20', text: 'text-orange-400' },
  weekend_warriors:       { bg: 'bg-purple-500/10', border: 'border-purple-500/20', text: 'text-purple-400' },
  economic_defectors:     { bg: 'bg-red-500/10', border: 'border-red-500/20', text: 'text-red-400' },
  system_frustrated:      { bg: 'bg-rose-500/10', border: 'border-rose-500/20', text: 'text-rose-400' },
  abandoned_by_adm:       { bg: 'bg-yellow-500/10', border: 'border-yellow-500/20', text: 'text-yellow-400' },
  chronic_never_activators: { bg: 'bg-gray-500/10', border: 'border-gray-500/20', text: 'text-gray-400' },
  life_event_paused:      { bg: 'bg-cyan-500/10', border: 'border-cyan-500/20', text: 'text-cyan-400' },
  regulatory_blocked:     { bg: 'bg-indigo-500/10', border: 'border-indigo-500/20', text: 'text-indigo-400' },
  digital_orphans:        { bg: 'bg-teal-500/10', border: 'border-teal-500/20', text: 'text-teal-400' },
  high_potential_unpolished: { bg: 'bg-lime-500/10', border: 'border-lime-500/20', text: 'text-lime-400' },
  competitor_poached:     { bg: 'bg-pink-500/10', border: 'border-pink-500/20', text: 'text-pink-400' },
  satisfied_passives:     { bg: 'bg-sky-500/10', border: 'border-sky-500/20', text: 'text-sky-400' },
  lost_causes:            { bg: 'bg-zinc-500/10', border: 'border-zinc-500/20', text: 'text-zinc-400' },
};

const SEGMENT_DISPLAY: Record<string, string> = {
  promising_rookies: 'Promising Rookies',
  stalled_starters: 'Stalled Starters',
  sleeping_giants: 'Sleeping Giants',
  fading_stars: 'Fading Stars',
  weekend_warriors: 'Weekend Warriors',
  economic_defectors: 'Economic Defectors',
  system_frustrated: 'System Frustrated',
  abandoned_by_adm: 'Abandoned by ADM',
  chronic_never_activators: 'Chronic Never-Activators',
  life_event_paused: 'Life-Event Paused',
  regulatory_blocked: 'Regulatory Blocked',
  digital_orphans: 'Digital Orphans',
  high_potential_unpolished: 'High-Potential Unpolished',
  competitor_poached: 'Competitor Poached',
  satisfied_passives: 'Satisfied Passives',
  lost_causes: 'Lost Causes',
};

const STRATEGY_ICONS: Record<string, { icon: any; label: string }> = {
  direct_call: { icon: Phone, label: 'Direct Call' },
  whatsapp_first: { icon: MessageCircle, label: 'WhatsApp First' },
  telegram_only: { icon: Send, label: 'Telegram Only' },
  no_contact: { icon: XCircle, label: 'No Contact' },
};

interface CohortSegmentCardProps {
  segment: string;
  count: number;
  avgScore: number;
  strategy: string;
  description?: string;
  onClick?: () => void;
  selected?: boolean;
}

export default function CohortSegmentCard({
  segment,
  count,
  avgScore,
  strategy,
  description,
  onClick,
  selected = false,
}: CohortSegmentCardProps) {
  const colors = SEGMENT_COLORS[segment] || SEGMENT_COLORS.lost_causes;
  const displayName = SEGMENT_DISPLAY[segment] || segment.replace(/_/g, ' ');
  const strategyInfo = STRATEGY_ICONS[strategy] || STRATEGY_ICONS.no_contact;
  const StrategyIcon = strategyInfo.icon;

  return (
    <button
      onClick={onClick}
      className={`w-full text-left p-4 rounded-xl border transition-all duration-200 ${
        selected
          ? `${colors.bg} ${colors.border} ring-1 ring-offset-0`
          : `bg-surface-card/60 border-surface-border/30 hover:border-surface-border/60 hover:bg-surface-card`
      }`}
      style={selected ? { ['--tw-ring-color' as any]: colors.text } : undefined}
    >
      <div className="flex items-start justify-between mb-2">
        <h3 className={`text-sm font-semibold ${colors.text}`}>
          {displayName}
        </h3>
        <span className="text-lg font-bold text-white">{count}</span>
      </div>

      {description && (
        <p className="text-xs text-gray-500 mb-3 line-clamp-2">{description}</p>
      )}

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <StrategyIcon className={`w-3.5 h-3.5 ${colors.text}`} />
          <span className="text-[10px] text-gray-400">{strategyInfo.label}</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="text-[10px] text-gray-500">Avg Score:</span>
          <span className={`text-xs font-semibold ${
            avgScore >= 70 ? 'text-emerald-400' :
            avgScore >= 40 ? 'text-amber-400' :
            avgScore >= 20 ? 'text-orange-400' : 'text-red-400'
          }`}>
            {avgScore.toFixed(0)}
          </span>
        </div>
      </div>
    </button>
  );
}

export { SEGMENT_COLORS, SEGMENT_DISPLAY, STRATEGY_ICONS };
