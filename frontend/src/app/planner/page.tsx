'use client';

import { useState, useCallback, useMemo } from 'react';
import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Plus,
  Loader2,
  Clock,
  CheckCircle2,
  AlertCircle,
  Phone,
  User,
  RefreshCw,
  X,
  PhoneCall,
  MessageSquare,
  GraduationCap,
  AlertTriangle,
  ClipboardCheck,
  Calendar,
  FileText,
} from 'lucide-react';
import { api } from '@/lib/api';
import { useAPI } from '@/lib/useAPI';
import { useAuth } from '@/lib/AuthContext';

const ENTRY_TYPE_CONFIG: Record<string, { label: string; color: string; bgColor: string; borderColor: string; icon: any }> = {
  follow_up: { label: 'Follow Up', color: 'text-cyan-400', bgColor: 'bg-cyan-500/10', borderColor: 'border-cyan-500/20', icon: PhoneCall },
  first_contact: { label: 'First Contact', color: 'text-blue-400', bgColor: 'bg-blue-500/10', borderColor: 'border-blue-500/20', icon: MessageSquare },
  training: { label: 'Training', color: 'text-purple-400', bgColor: 'bg-purple-500/10', borderColor: 'border-purple-500/20', icon: GraduationCap },
  escalation: { label: 'Escalation', color: 'text-red-400', bgColor: 'bg-red-500/10', borderColor: 'border-red-500/20', icon: AlertTriangle },
  review: { label: 'Review', color: 'text-amber-400', bgColor: 'bg-amber-500/10', borderColor: 'border-amber-500/20', icon: ClipboardCheck },
};

const STATUS_CONFIG: Record<string, { label: string; className: string }> = {
  pending: { label: 'Pending', className: 'bg-amber-500/10 text-amber-400 border border-amber-500/20' },
  scheduled: { label: 'Scheduled', className: 'bg-amber-500/10 text-amber-400 border border-amber-500/20' },
  completed: { label: 'Completed', className: 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' },
  overdue: { label: 'Overdue', className: 'bg-red-500/10 text-red-400 border border-red-500/20' },
  rescheduled: { label: 'Rescheduled', className: 'bg-blue-500/10 text-blue-400 border border-blue-500/20' },
};

function formatDate(date: Date): string {
  return date.toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
}

function formatDateISO(date: Date): string {
  return date.toISOString().split('T')[0];
}

function formatTime(timeStr: string): string {
  if (!timeStr) return '';
  try {
    const [hours, minutes] = timeStr.split(':');
    const h = parseInt(hours);
    const ampm = h >= 12 ? 'PM' : 'AM';
    const h12 = h % 12 || 12;
    return `${h12}:${minutes} ${ampm}`;
  } catch {
    return timeStr;
  }
}

export default function PlannerPage() {
  const { user } = useAuth();
  const admId = user?.adm_id;

  const [selectedDate, setSelectedDate] = useState(new Date());
  const [showAddForm, setShowAddForm] = useState(false);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  const [actionLoading, setActionLoading] = useState<number | null>(null);
  const [rescheduleId, setRescheduleId] = useState<number | null>(null);
  const [rescheduleDate, setRescheduleDate] = useState('');
  const [rescheduleTime, setRescheduleTime] = useState('');

  // Form state
  const [formData, setFormData] = useState({
    agent_id: '',
    entry_type: 'follow_up',
    scheduled_date: formatDateISO(new Date()),
    scheduled_time: '10:00',
    notes: '',
  });
  const [submitting, setSubmitting] = useState(false);

  // Fetch diary entries for selected date
  const selectedDateISO = formatDateISO(selectedDate);
  const { data: todayEntries, loading: loadingToday, refetch: refetchToday } = useAPI(
    () => admId ? api.getDiaryToday(admId, selectedDateISO) : Promise.resolve([]),
    undefined,
    [selectedDateISO],
  );

  // Fetch upcoming entries
  const { data: upcomingEntries, loading: loadingUpcoming, refetch: refetchUpcoming } = useAPI(
    () => admId ? api.getDiaryUpcoming(admId, 7) : Promise.resolve([]),
  );

  // Fetch ADM's agents for the dropdown
  const { data: agentsData, loading: loadingAgents } = useAPI(
    () => admId ? api.getADMAgents(admId) : Promise.resolve({ agents: [] }),
  );

  const agents = agentsData?.agents || agentsData || [];

  // Extract schedule array from backend response
  // Backend returns { schedule: [...], total_entries, completed, pending } for today
  // and { entries: [...] } for upcoming
  const todaySchedule = useMemo(() => {
    if (!todayEntries) return [];
    if (Array.isArray(todayEntries)) return todayEntries;
    // Backend returns { schedule: [...] } with items having time/type/status fields
    const schedule = (todayEntries as any)?.schedule || [];
    // Normalize field names: backend uses time/type, frontend expects scheduled_time/entry_type
    return schedule.map((e: any) => ({
      ...e,
      scheduled_time: e.time || e.scheduled_time,
      entry_type: e.type || e.entry_type,
      status: e.status === 'scheduled' ? 'pending' : e.status,
    }));
  }, [todayEntries]);

  // Compute stats
  const stats = useMemo(() => {
    const total = todaySchedule.length;
    const completed = todaySchedule.filter((e: any) => e.status === 'completed').length;
    const pending = todaySchedule.filter((e: any) => e.status === 'pending' || e.status === 'scheduled').length;
    const overdue = todaySchedule.filter((e: any) => e.status === 'overdue' || e.status === 'missed').length;
    return { total, completed, pending, overdue };
  }, [todaySchedule]);

  // Sort entries by time
  const sortedEntries = useMemo(() => {
    return [...todaySchedule].sort((a: any, b: any) => {
      const timeA = a.scheduled_time || a.time || '23:59';
      const timeB = b.scheduled_time || b.time || '23:59';
      return timeA.localeCompare(timeB);
    });
  }, [todaySchedule]);

  // Group upcoming by date
  const upcomingGrouped = useMemo(() => {
    if (!upcomingEntries) return [];
    // Backend returns { entries: [...] } with items having date/time/type fields
    const raw = Array.isArray(upcomingEntries) ? upcomingEntries : (upcomingEntries as any)?.entries || [];
    // Normalize field names
    const entries = raw.map((e: any) => ({
      ...e,
      scheduled_date: e.date || e.scheduled_date,
      scheduled_time: e.time || e.scheduled_time,
      entry_type: e.type || e.entry_type,
    }));
    const groups: Record<string, any[]> = {};
    entries.forEach((entry: any) => {
      const date = entry.scheduled_date || 'Unknown';
      if (!groups[date]) groups[date] = [];
      groups[date].push(entry);
    });
    return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b));
  }, [upcomingEntries]);

  // Date navigation
  const goToPreviousDay = () => {
    const d = new Date(selectedDate);
    d.setDate(d.getDate() - 1);
    setSelectedDate(d);
  };

  const goToNextDay = () => {
    const d = new Date(selectedDate);
    d.setDate(d.getDate() + 1);
    setSelectedDate(d);
  };

  const goToToday = () => {
    setSelectedDate(new Date());
  };

  // Handle mark complete
  const handleComplete = useCallback(async (entryId: number) => {
    setActionLoading(entryId);
    try {
      await api.completeDiaryEntry(entryId, 'Completed');
      setFeedback({ type: 'success', message: 'Entry marked as completed' });
      refetchToday();
      refetchUpcoming();
    } catch (e: any) {
      setFeedback({ type: 'error', message: e.message || 'Failed to complete entry' });
    } finally {
      setActionLoading(null);
      setTimeout(() => setFeedback(null), 3000);
    }
  }, [refetchToday, refetchUpcoming]);

  // Handle reschedule
  const handleReschedule = useCallback(async () => {
    if (!rescheduleId || !rescheduleDate) return;
    setActionLoading(rescheduleId);
    try {
      await api.rescheduleDiaryEntry(rescheduleId, {
        new_date: rescheduleDate,
        new_time: rescheduleTime || undefined,
      });
      setFeedback({ type: 'success', message: 'Entry rescheduled successfully' });
      setRescheduleId(null);
      setRescheduleDate('');
      setRescheduleTime('');
      refetchToday();
      refetchUpcoming();
    } catch (e: any) {
      setFeedback({ type: 'error', message: e.message || 'Failed to reschedule entry' });
    } finally {
      setActionLoading(null);
      setTimeout(() => setFeedback(null), 3000);
    }
  }, [rescheduleId, rescheduleDate, rescheduleTime, refetchToday, refetchUpcoming]);

  // Handle add entry
  const handleAddEntry = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    if (!admId) return;
    setSubmitting(true);
    try {
      const entryData: any = {
        adm_id: admId,
        entry_type: formData.entry_type,
        scheduled_date: formData.scheduled_date,
        scheduled_time: formData.scheduled_time || undefined,
        notes: formData.notes || undefined,
      };
      if (formData.agent_id) {
        entryData.agent_id = parseInt(formData.agent_id);
      }
      await api.createDiaryEntry(entryData);
      setFeedback({ type: 'success', message: 'Diary entry created successfully' });
      setShowAddForm(false);
      setFormData({ agent_id: '', entry_type: 'follow_up', scheduled_date: formatDateISO(new Date()), scheduled_time: '10:00', notes: '' });
      refetchToday();
      refetchUpcoming();
    } catch (e: any) {
      setFeedback({ type: 'error', message: e.message || 'Failed to create entry' });
    } finally {
      setSubmitting(false);
      setTimeout(() => setFeedback(null), 3000);
    }
  }, [admId, formData, refetchToday, refetchUpcoming]);

  if (!admId) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-gray-400">ADM access required to view the planner.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Feedback Toast */}
      {feedback && (
        <div className={`fixed top-4 right-4 z-50 flex items-center gap-2 px-4 py-3 rounded-lg text-sm font-medium shadow-lg transition-all ${
          feedback.type === 'success'
            ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
            : 'bg-red-500/10 text-red-400 border border-red-500/20'
        }`}>
          {feedback.type === 'success' ? <CheckCircle2 className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
          {feedback.message}
        </div>
      )}

      {/* Top Bar */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-gradient-to-br from-brand-red/20 to-orange-500/20 border border-brand-red/20">
            <CalendarDays className="w-6 h-6 text-brand-red" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-white">Daily Planner</h1>
            <p className="text-sm text-gray-500">Manage your schedule and diary entries</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Date Navigation */}
          <div className="flex items-center gap-2">
            <button
              onClick={goToPreviousDay}
              className="p-2 rounded-lg bg-surface-card border border-surface-border text-gray-400 hover:text-white transition-colors"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              onClick={goToToday}
              className="px-4 py-2 rounded-lg bg-surface-card border border-surface-border text-white text-sm font-medium hover:bg-surface-card/80 transition-colors min-w-[220px] text-center"
            >
              {formatDate(selectedDate)}
            </button>
            <button
              onClick={goToNextDay}
              className="p-2 rounded-lg bg-surface-card border border-surface-border text-gray-400 hover:text-white transition-colors"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>

          {/* Add Entry Button */}
          <button
            onClick={() => setShowAddForm(true)}
            className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-brand-red hover:bg-brand-red/90 text-white text-sm font-medium transition-colors"
          >
            <Plus className="w-4 h-4" />
            Add Entry
          </button>
        </div>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Total Today', value: stats.total, icon: CalendarDays, color: 'text-blue-400', bg: 'bg-blue-500/10', border: 'border-blue-500/20' },
          { label: 'Completed', value: stats.completed, icon: CheckCircle2, color: 'text-emerald-400', bg: 'bg-emerald-500/10', border: 'border-emerald-500/20' },
          { label: 'Pending', value: stats.pending, icon: Clock, color: 'text-amber-400', bg: 'bg-amber-500/10', border: 'border-amber-500/20' },
          { label: 'Overdue', value: stats.overdue, icon: AlertCircle, color: stats.overdue > 0 ? 'text-red-400' : 'text-gray-400', bg: stats.overdue > 0 ? 'bg-red-500/10' : 'bg-surface-card/40', border: stats.overdue > 0 ? 'border-red-500/20' : 'border-surface-border/30' },
        ].map((stat) => {
          const Icon = stat.icon;
          return (
            <div key={stat.label} className={`p-4 rounded-xl ${stat.bg} border ${stat.border} backdrop-blur-sm`}>
              <div className="flex items-center gap-2 mb-2">
                <Icon className={`w-4 h-4 ${stat.color}`} />
                <span className="text-xs text-gray-400">{stat.label}</span>
              </div>
              <p className={`text-2xl font-bold ${stat.color}`}>{stat.value}</p>
            </div>
          );
        })}
      </div>

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Timeline - Main Section */}
        <div className="lg:col-span-2 space-y-4">
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            <Clock className="w-5 h-5 text-gray-400" />
            {formatDateISO(selectedDate) === formatDateISO(new Date()) ? "Today\u2019s Timeline" : `Timeline \u2014 ${selectedDate.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}`}
          </h2>

          {loadingToday ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="w-8 h-8 text-gray-500 animate-spin" />
            </div>
          ) : sortedEntries.length === 0 ? (
            <div className="text-center py-16 bg-surface-card/40 border border-surface-border/30 rounded-xl">
              <CalendarDays className="w-12 h-12 mx-auto mb-3 text-gray-600" />
              <p className="text-gray-400 text-sm">No entries for today</p>
              <p className="text-gray-600 text-xs mt-1">Click &quot;Add Entry&quot; to create one</p>
            </div>
          ) : (
            <div className="space-y-3">
              {sortedEntries.map((entry: any) => {
                const typeConfig = ENTRY_TYPE_CONFIG[entry.entry_type] || ENTRY_TYPE_CONFIG.follow_up;
                const statusConfig = STATUS_CONFIG[entry.status] || STATUS_CONFIG.pending;
                const TypeIcon = typeConfig.icon;
                const isCompleted = entry.status === 'completed';

                return (
                  <div
                    key={entry.id}
                    className={`flex items-start gap-4 p-4 rounded-xl border transition-all ${
                      isCompleted
                        ? 'bg-surface-card/20 border-surface-border/20 opacity-60'
                        : 'bg-surface-card/40 border-surface-border/30 hover:border-surface-border/50'
                    }`}
                  >
                    {/* Left: Type Icon */}
                    <div className={`p-2.5 rounded-lg ${typeConfig.bgColor} border ${typeConfig.borderColor} flex-shrink-0`}>
                      <TypeIcon className={`w-5 h-5 ${typeConfig.color}`} />
                    </div>

                    {/* Center: Details */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`font-medium ${isCompleted ? 'text-gray-500 line-through' : 'text-white'}`}>
                          {entry.agent_name || entry.notes || 'Diary Entry'}
                        </span>
                        {entry.agent_phone && (
                          <span className="flex items-center gap-1 text-xs text-gray-500">
                            <Phone className="w-3 h-3" />
                            {entry.agent_phone}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 mt-1">
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${typeConfig.bgColor} ${typeConfig.color} border ${typeConfig.borderColor}`}>
                          {typeConfig.label}
                        </span>
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${statusConfig.className}`}>
                          {statusConfig.label}
                        </span>
                      </div>
                      {entry.agent_name && entry.notes && (
                        <p className={`text-xs mt-2 ${isCompleted ? 'text-gray-600 line-through' : 'text-gray-400'}`}>
                          {entry.notes}
                        </p>
                      )}
                    </div>

                    {/* Right: Time + Actions */}
                    <div className="flex flex-col items-end gap-2 flex-shrink-0">
                      {entry.scheduled_time && (
                        <span className="text-sm font-medium text-gray-300">
                          {formatTime(entry.scheduled_time)}
                        </span>
                      )}
                      {!isCompleted && (
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => handleComplete(entry.id)}
                            disabled={actionLoading === entry.id}
                            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-medium hover:bg-emerald-500/20 transition-colors disabled:opacity-50"
                          >
                            {actionLoading === entry.id ? (
                              <Loader2 className="w-3 h-3 animate-spin" />
                            ) : (
                              <CheckCircle2 className="w-3 h-3" />
                            )}
                            Complete
                          </button>
                          <button
                            onClick={() => { setRescheduleId(entry.id); setRescheduleDate(''); setRescheduleTime(''); }}
                            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-surface-card border border-surface-border text-gray-400 text-xs font-medium hover:text-white transition-colors"
                          >
                            <RefreshCw className="w-3 h-3" />
                            Reschedule
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Side Panel - This Week */}
        <div className="space-y-4">
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            <Calendar className="w-5 h-5 text-gray-400" />
            This Week
          </h2>

          {loadingUpcoming ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-6 h-6 text-gray-500 animate-spin" />
            </div>
          ) : upcomingGrouped.length === 0 ? (
            <div className="text-center py-12 bg-surface-card/40 border border-surface-border/30 rounded-xl">
              <FileText className="w-10 h-10 mx-auto mb-2 text-gray-600" />
              <p className="text-gray-400 text-xs">No upcoming entries</p>
            </div>
          ) : (
            <div className="space-y-4">
              {upcomingGrouped.map(([date, entries]) => {
                const dateObj = new Date(date + 'T00:00:00');
                const dayLabel = dateObj.toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' });
                return (
                  <div key={date} className="bg-surface-card/40 border border-surface-border/30 rounded-xl p-4">
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-sm font-medium text-white">{dayLabel}</span>
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-brand-red/10 text-brand-red-light border border-brand-red/20">
                        {entries.length} {entries.length === 1 ? 'entry' : 'entries'}
                      </span>
                    </div>
                    <div className="space-y-2">
                      {entries.map((entry: any) => {
                        const typeConfig = ENTRY_TYPE_CONFIG[entry.entry_type] || ENTRY_TYPE_CONFIG.follow_up;
                        const TypeIcon = typeConfig.icon;
                        const isEntryCompleted = entry.status === 'completed';
                        return (
                          <div key={entry.id} className={`flex items-center gap-2 ${isEntryCompleted ? 'opacity-50' : ''}`}>
                            <TypeIcon className={`w-3.5 h-3.5 ${typeConfig.color} flex-shrink-0`} />
                            <span className={`text-xs truncate flex-1 ${isEntryCompleted ? 'text-gray-500 line-through' : 'text-gray-300'}`}>
                              {entry.agent_name || entry.notes || 'Diary Entry'}
                            </span>
                            {entry.scheduled_time && (
                              <span className="text-[10px] text-gray-500 flex-shrink-0">
                                {formatTime(entry.scheduled_time)}
                              </span>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Add Entry Modal */}
      {showAddForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-lg bg-surface-card border border-surface-border rounded-2xl p-6 shadow-2xl mx-4">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                <Plus className="w-5 h-5 text-brand-red" />
                Add Diary Entry
              </h2>
              <button
                onClick={() => setShowAddForm(false)}
                className="p-1.5 rounded-lg hover:bg-white/5 text-gray-400 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleAddEntry} className="space-y-4">
              {/* Agent Selector */}
              <div>
                <label className="block text-xs text-gray-400 mb-1.5 uppercase tracking-wider">Agent *</label>
                <select
                  required
                  value={formData.agent_id}
                  onChange={(e) => setFormData({ ...formData, agent_id: e.target.value })}
                  className="w-full bg-surface-card border border-surface-border rounded-lg px-4 py-2.5 text-white text-sm focus:border-brand-red/40 focus:outline-none"
                >
                  <option value="">Select an agent...</option>
                  {(Array.isArray(agents) ? agents : []).map((agent: any) => (
                    <option key={agent.id} value={agent.id}>
                      {agent.name} {agent.phone ? `(${agent.phone})` : ''}
                    </option>
                  ))}
                </select>
                {loadingAgents && <p className="text-xs text-gray-500 mt-1">Loading agents...</p>}
              </div>

              {/* Entry Type */}
              <div>
                <label className="block text-xs text-gray-400 mb-1.5 uppercase tracking-wider">Entry Type *</label>
                <div className="grid grid-cols-3 gap-2">
                  {Object.entries(ENTRY_TYPE_CONFIG).map(([key, config]) => {
                    const Icon = config.icon;
                    const isSelected = formData.entry_type === key;
                    return (
                      <button
                        key={key}
                        type="button"
                        onClick={() => setFormData({ ...formData, entry_type: key })}
                        className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-all border ${
                          isSelected
                            ? `${config.bgColor} ${config.color} ${config.borderColor}`
                            : 'bg-surface-card border-surface-border text-gray-400 hover:text-white'
                        }`}
                      >
                        <Icon className="w-3.5 h-3.5" />
                        {config.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Date and Time */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs text-gray-400 mb-1.5 uppercase tracking-wider">Date *</label>
                  <input
                    required
                    type="date"
                    value={formData.scheduled_date}
                    onChange={(e) => setFormData({ ...formData, scheduled_date: e.target.value })}
                    className="w-full bg-surface-card border border-surface-border rounded-lg px-4 py-2.5 text-white text-sm focus:border-brand-red/40 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1.5 uppercase tracking-wider">Time *</label>
                  <input
                    required
                    type="time"
                    value={formData.scheduled_time}
                    onChange={(e) => setFormData({ ...formData, scheduled_time: e.target.value })}
                    className="w-full bg-surface-card border border-surface-border rounded-lg px-4 py-2.5 text-white text-sm focus:border-brand-red/40 focus:outline-none"
                  />
                </div>
              </div>

              {/* Notes */}
              <div>
                <label className="block text-xs text-gray-400 mb-1.5 uppercase tracking-wider">Notes</label>
                <textarea
                  value={formData.notes}
                  onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                  rows={3}
                  placeholder="Add notes about this entry..."
                  className="w-full bg-surface-card border border-surface-border rounded-lg px-4 py-2.5 text-white text-sm focus:border-brand-red/40 focus:outline-none resize-none placeholder:text-gray-600"
                />
              </div>

              {/* Actions */}
              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowAddForm(false)}
                  className="flex-1 py-2.5 rounded-lg bg-surface-card border border-surface-border text-gray-400 hover:text-white text-sm transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="flex-1 py-2.5 rounded-lg bg-brand-red hover:bg-brand-red/90 text-white text-sm font-medium disabled:opacity-50 flex items-center justify-center gap-2 transition-colors"
                >
                  {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                  Create Entry
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Reschedule Modal */}
      {rescheduleId !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-sm bg-surface-card border border-surface-border rounded-2xl p-6 shadow-2xl mx-4">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                <RefreshCw className="w-5 h-5 text-blue-400" />
                Reschedule Entry
              </h2>
              <button
                onClick={() => setRescheduleId(null)}
                className="p-1.5 rounded-lg hover:bg-white/5 text-gray-400 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-xs text-gray-400 mb-1.5 uppercase tracking-wider">New Date *</label>
                <input
                  type="date"
                  value={rescheduleDate}
                  onChange={(e) => setRescheduleDate(e.target.value)}
                  className="w-full bg-surface-card border border-surface-border rounded-lg px-4 py-2.5 text-white text-sm focus:border-brand-red/40 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1.5 uppercase tracking-wider">New Time</label>
                <input
                  type="time"
                  value={rescheduleTime}
                  onChange={(e) => setRescheduleTime(e.target.value)}
                  className="w-full bg-surface-card border border-surface-border rounded-lg px-4 py-2.5 text-white text-sm focus:border-brand-red/40 focus:outline-none"
                />
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setRescheduleId(null)}
                  className="flex-1 py-2.5 rounded-lg bg-surface-card border border-surface-border text-gray-400 hover:text-white text-sm transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleReschedule}
                  disabled={!rescheduleDate || actionLoading === rescheduleId}
                  className="flex-1 py-2.5 rounded-lg bg-blue-500 hover:bg-blue-500/90 text-white text-sm font-medium disabled:opacity-50 flex items-center justify-center gap-2 transition-colors"
                >
                  {actionLoading === rescheduleId ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
                  Reschedule
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
