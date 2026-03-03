'use client';

import { useState, useCallback, useMemo, useEffect } from 'react';
import {
  Send,
  Loader2,
  CheckCircle2,
  AlertCircle,
  Phone,
  MessageCircle,
  XCircle,
  Download,
  Filter,
  Users,
  Check,
  ChevronDown,
  ChevronUp,
  ShieldAlert,
  RotateCcw,
  Workflow,
  Save,
} from 'lucide-react';
import { api } from '@/lib/api';
import { useAPI } from '@/lib/useAPI';
import { useAuth } from '@/lib/AuthContext';
import { SEGMENT_DISPLAY } from '@/components/CohortSegmentCard';
import WorkflowStepBuilder, { type WorkflowStep } from '@/components/WorkflowStepBuilder';

// ─── Types ─────────────────────────────────────────────────────────────────────

interface PlanAgent {
  id: number;
  name: string;
  phone: string;
  location: string;
  segment: string;
  score: number;
  first_message: string;
}

interface StrategyGroup {
  strategy: string;
  agents: PlanAgent[];
}

interface CohortSegmentSummary {
  segment: string;
  count: number;
  avg_score: number;
  strategy: string;
}

interface OutreachResult {
  sent: number;
  failed: number;
  skipped_no_telegram: number;
  total_requested: number;
  errors: any[];
  sent_agents: any[];
}

type TabKey = 'plan' | 'workflow' | 'results';

// ─── Strategy display helpers ──────────────────────────────────────────────────

const STRATEGY_OPTIONS = [
  { key: 'all', label: 'All', icon: Users },
  { key: 'direct_call', label: 'Direct Call', icon: Phone },
  { key: 'whatsapp_first', label: 'WhatsApp First', icon: MessageCircle },
  { key: 'telegram_only', label: 'Telegram Only', icon: Send },
] as const;

const STRATEGY_DISPLAY: Record<string, string> = {
  direct_call: 'Direct Call',
  whatsapp_first: 'WhatsApp First',
  telegram_only: 'Telegram Only',
  no_contact: 'No Contact',
};

// ─── Page Component ────────────────────────────────────────────────────────────

export default function OutreachPage() {
  const { isAdmin } = useAuth();

  // ── Tab state ──
  const [activeTab, setActiveTab] = useState<TabKey>('plan');

  // ── Strategy filter ──
  const [strategyFilter, setStrategyFilter] = useState<string>('all');

  // ── Segment filter (set of selected segment keys) ──
  const [selectedSegments, setSelectedSegments] = useState<Set<string>>(new Set());
  const [segmentFilterInitialised, setSegmentFilterInitialised] = useState(false);

  // ── Agent selection ──
  const [selectedAgentIds, setSelectedAgentIds] = useState<Set<number>>(new Set());

  // ── Editable messages (agent_id → edited message text) ──
  const [editedMessages, setEditedMessages] = useState<Record<number, string>>({});

  // ── Send state ──
  const [sending, setSending] = useState(false);
  const [sendResult, setSendResult] = useState<OutreachResult | null>(null);

  // ── Feedback toast ──
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // ── Expand first‑message column ──
  const [expandedMessageId, setExpandedMessageId] = useState<number | null>(null);

  // ── Workflow tab state ──
  const [workflowSteps, setWorkflowSteps] = useState<WorkflowStep[]>([]);
  const [workflowStrategy, setWorkflowStrategy] = useState<string>('direct_call');
  const [savingWorkflow, setSavingWorkflow] = useState(false);
  const [workflowSaved, setWorkflowSaved] = useState(false);

  // ── Data fetching ──
  const { data: engagementPlan, loading: loadingPlan } = useAPI(() => api.getCohortEngagementPlan());
  const { data: cohortSummary, loading: loadingSummary } = useAPI(() => api.getCohortSummary());

  // ── Derived: all segments from summary ──
  const allSegments: CohortSegmentSummary[] = useMemo(() => {
    if (!cohortSummary) return [];
    return (cohortSummary as any)?.segments || [];
  }, [cohortSummary]);

  // Initialise segment filter to all once data loads
  if (allSegments.length > 0 && !segmentFilterInitialised) {
    const all = new Set(allSegments.map((s) => s.segment));
    setSelectedSegments(all);
    setSegmentFilterInitialised(true);
  }

  // ── Derived: flat list of agents matching filters ──
  const filteredAgents: PlanAgent[] = useMemo(() => {
    if (!engagementPlan || !Array.isArray(engagementPlan)) return [];
    const groups: StrategyGroup[] = engagementPlan;
    let agents: PlanAgent[] = [];

    groups.forEach((g) => {
      if (strategyFilter !== 'all' && g.strategy !== strategyFilter) return;
      g.agents.forEach((a) => {
        if (selectedSegments.size > 0 && !selectedSegments.has(a.segment)) return;
        agents.push(a);
      });
    });

    return agents;
  }, [engagementPlan, strategyFilter, selectedSegments]);

  // Initialize edited messages from agent first_message when plan loads
  useEffect(() => {
    if (!engagementPlan || !Array.isArray(engagementPlan)) return;
    const msgs: Record<number, string> = {};
    (engagementPlan as StrategyGroup[]).forEach((g) => {
      g.agents.forEach((a) => {
        if (a.first_message && !(a.id in editedMessages)) {
          msgs[a.id] = a.first_message;
        }
      });
    });
    if (Object.keys(msgs).length > 0) {
      setEditedMessages((prev) => ({ ...msgs, ...prev }));
    }
  }, [engagementPlan]);

  // ── Derived: unique segment keys from plan data ──
  const uniqueSegmentsInPlan = useMemo(() => {
    if (!engagementPlan || !Array.isArray(engagementPlan)) return new Set<string>();
    const segs = new Set<string>();
    (engagementPlan as StrategyGroup[]).forEach((g) => g.agents.forEach((a) => segs.add(a.segment)));
    return segs;
  }, [engagementPlan]);

  // ── Derived: count selected agents from filtered list ──
  const selectedCount = useMemo(() => {
    return filteredAgents.filter((a) => selectedAgentIds.has(a.id)).length;
  }, [filteredAgents, selectedAgentIds]);

  // ── Derived: strategy for an agent ──
  const agentStrategyMap = useMemo(() => {
    const map: Record<number, string> = {};
    if (!engagementPlan || !Array.isArray(engagementPlan)) return map;
    (engagementPlan as StrategyGroup[]).forEach((g) => {
      g.agents.forEach((a) => {
        map[a.id] = g.strategy;
      });
    });
    return map;
  }, [engagementPlan]);

  // ── Handlers ─────────────────────────────────────────────────────────────────

  const toggleSegment = useCallback((segment: string) => {
    setSelectedSegments((prev) => {
      const next = new Set(prev);
      if (next.has(segment)) {
        next.delete(segment);
      } else {
        next.add(segment);
      }
      return next;
    });
  }, []);

  const toggleAgentSelection = useCallback((id: number) => {
    setSelectedAgentIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const selectAll = useCallback(() => {
    setSelectedAgentIds(new Set(filteredAgents.map((a) => a.id)));
  }, [filteredAgents]);

  const deselectAll = useCallback(() => {
    setSelectedAgentIds(new Set());
  }, []);

  const updateMessage = useCallback((agentId: number, msg: string) => {
    setEditedMessages((prev) => ({ ...prev, [agentId]: msg }));
  }, []);

  const resetMessage = useCallback((agent: PlanAgent) => {
    setEditedMessages((prev) => ({ ...prev, [agent.id]: agent.first_message || '' }));
  }, []);

  const handleSendWhatsApp = useCallback(() => {
    const selectedAgents = filteredAgents.filter((a) => selectedAgentIds.has(a.id));
    if (selectedAgents.length === 0) return;

    let opened = 0;
    selectedAgents.forEach((a) => {
      const message = editedMessages[a.id] || a.first_message || '';
      // Format phone: strip leading 0, ensure country code (default +91 India)
      let phone = a.phone.replace(/[^0-9]/g, '');
      if (phone.startsWith('0')) phone = phone.substring(1);
      if (!phone.startsWith('91') && phone.length === 10) phone = '91' + phone;
      const url = `https://wa.me/${phone}?text=${encodeURIComponent(message)}`;
      window.open(url, '_blank');
      opened++;
    });

    setFeedback({
      type: 'success',
      message: `Opened WhatsApp for ${opened} agent${opened !== 1 ? 's' : ''} — send from your WhatsApp app`,
    });
    setTimeout(() => setFeedback(null), 5000);
  }, [filteredAgents, selectedAgentIds, editedMessages]);

  const handleSendTelegram = useCallback(async () => {
    const selectedAgents = filteredAgents.filter((a) => selectedAgentIds.has(a.id));
    const ids = selectedAgents.map((a) => a.id);
    if (ids.length === 0) return;

    // Build custom_messages from edited messages that differ from originals
    const customMsgs: Record<number, string> = {};
    selectedAgents.forEach((a) => {
      const edited = editedMessages[a.id];
      if (edited && edited !== a.first_message) {
        customMsgs[a.id] = edited;
      }
    });

    setSending(true);
    setFeedback(null);
    try {
      const result = await api.sendTelegramOutreach(
        ids,
        Object.keys(customMsgs).length > 0 ? customMsgs : undefined,
      );
      setSendResult(result);
      setFeedback({
        type: result.failed > 0 ? 'error' : 'success',
        message: `Sent: ${result.sent}, Failed: ${result.failed}, Skipped: ${result.skipped_no_telegram}`,
      });
      setActiveTab('results');
    } catch (e: any) {
      setFeedback({ type: 'error', message: e.message || 'Failed to send outreach' });
    } finally {
      setSending(false);
      setTimeout(() => setFeedback(null), 5000);
    }
  }, [filteredAgents, selectedAgentIds, editedMessages]);

  const handleExportCSV = useCallback(() => {
    const agents = filteredAgents.filter((a) => selectedAgentIds.has(a.id));
    if (agents.length === 0) return;

    const header = 'phone,name,segment,strategy,first_message';
    const rows = agents.map((a) => {
      const strategy = agentStrategyMap[a.id] || '';
      const message = (editedMessages[a.id] || a.first_message || '').replace(/"/g, '""');
      return `"${a.phone}","${a.name}","${a.segment}","${strategy}","${message}"`;
    });

    const csv = [header, ...rows].join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `outreach_plan_${new Date().toISOString().split('T')[0]}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }, [filteredAgents, selectedAgentIds, agentStrategyMap, editedMessages]);

  const handleSaveWorkflow = useCallback(async () => {
    const ids = filteredAgents.filter((a) => selectedAgentIds.has(a.id)).map((a) => a.id);
    if (ids.length === 0 || workflowSteps.length === 0) return;

    setSavingWorkflow(true);
    setWorkflowSaved(false);
    try {
      await api.saveOutreachWorkflow(ids, workflowSteps);
      setWorkflowSaved(true);
      setFeedback({
        type: 'success',
        message: `Workflow saved for ${ids.length} agent${ids.length !== 1 ? 's' : ''} (${workflowSteps.length} steps)`,
      });
    } catch (e: any) {
      setFeedback({ type: 'error', message: e.message || 'Failed to save workflow' });
    } finally {
      setSavingWorkflow(false);
      setTimeout(() => setFeedback(null), 5000);
    }
  }, [filteredAgents, selectedAgentIds, workflowSteps]);

  // ── Admin gate ───────────────────────────────────────────────────────────────

  if (!isAdmin) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <ShieldAlert className="w-12 h-12 text-gray-600" />
        <p className="text-gray-400 text-sm">Admin only — you do not have permission to access this page.</p>
      </div>
    );
  }

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Feedback Toast */}
      {feedback && (
        <div
          className={`fixed top-4 right-4 z-50 flex items-center gap-2 px-4 py-3 rounded-lg text-sm font-medium shadow-lg transition-all ${
            feedback.type === 'success'
              ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
              : 'bg-red-500/10 text-red-400 border border-red-500/20'
          }`}
        >
          {feedback.type === 'success' ? (
            <CheckCircle2 className="w-4 h-4" />
          ) : (
            <AlertCircle className="w-4 h-4" />
          )}
          {feedback.message}
        </div>
      )}

      {/* Page Header */}
      <div className="flex items-center gap-3">
        <div className="p-2.5 rounded-xl bg-gradient-to-br from-brand-red/20 to-orange-500/20 border border-brand-red/20">
          <Send className="w-6 h-6 text-brand-red" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-white">Agent Outreach</h1>
          <p className="text-sm text-gray-500">Plan and execute cohort-based agent outreach campaigns</p>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="flex items-center gap-2">
        {([
          { key: 'plan' as TabKey, label: 'Plan Outreach', icon: Filter },
          { key: 'workflow' as TabKey, label: 'Workflow', icon: Workflow },
          { key: 'results' as TabKey, label: 'Results', icon: CheckCircle2 },
        ]).map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all border ${
                isActive
                  ? 'bg-brand-red/10 text-white border-brand-red/20'
                  : 'bg-surface-card border-surface-border text-gray-400 hover:text-white'
              }`}
            >
              <Icon className="w-4 h-4" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* ═══════════════════════ Plan Outreach Tab ═══════════════════════ */}
      {activeTab === 'plan' && (
        <div className="space-y-6">
          {(loadingPlan || loadingSummary) ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="w-8 h-8 text-gray-500 animate-spin" />
            </div>
          ) : (
            <>
              {/* Strategy filter buttons */}
              <div className="glass-card p-5 space-y-4">
                <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                  <Filter className="w-4 h-4 text-gray-400" />
                  Strategy Filter
                </h3>
                <div className="flex items-center gap-2 flex-wrap">
                  {STRATEGY_OPTIONS.map((opt) => {
                    const Icon = opt.icon;
                    const isActive = strategyFilter === opt.key;
                    return (
                      <button
                        key={opt.key}
                        onClick={() => setStrategyFilter(opt.key)}
                        className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all border ${
                          isActive
                            ? 'bg-brand-red/10 text-white border-brand-red/20'
                            : 'bg-surface-card border-surface-border text-gray-400 hover:text-white'
                        }`}
                      >
                        <Icon className="w-4 h-4" />
                        {opt.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Segment checkboxes */}
              <div className="glass-card p-5 space-y-4">
                <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                  <Users className="w-4 h-4 text-gray-400" />
                  Segment Filter
                </h3>
                <div className="flex flex-wrap gap-2">
                  {allSegments
                    .filter((s) => uniqueSegmentsInPlan.has(s.segment))
                    .map((seg) => {
                      const isChecked = selectedSegments.has(seg.segment);
                      const displayName = SEGMENT_DISPLAY[seg.segment] || seg.segment.replace(/_/g, ' ');
                      return (
                        <button
                          key={seg.segment}
                          onClick={() => toggleSegment(seg.segment)}
                          className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium transition-all border ${
                            isChecked
                              ? 'bg-brand-red/10 text-white border-brand-red/20'
                              : 'bg-surface-card border-surface-border text-gray-400 hover:text-white'
                          }`}
                        >
                          <div
                            className={`w-4 h-4 rounded flex items-center justify-center border transition-all ${
                              isChecked
                                ? 'bg-brand-red border-brand-red'
                                : 'border-surface-border bg-transparent'
                            }`}
                          >
                            {isChecked && <Check className="w-3 h-3 text-white" />}
                          </div>
                          {displayName}
                          <span className="text-gray-500">({seg.count})</span>
                        </button>
                      );
                    })}
                </div>
              </div>

              {/* Summary row */}
              <div className="glass-card p-4 flex items-center justify-between flex-wrap gap-3">
                <div className="flex items-center gap-2 text-sm text-gray-300">
                  <Users className="w-4 h-4 text-gray-400" />
                  <span>
                    <span className="font-semibold text-white">{filteredAgents.length}</span> agents matched
                    {' '}across{' '}
                    <span className="font-semibold text-white">{selectedSegments.size}</span> segments
                    {selectedCount > 0 && (
                      <>
                        {' '}&middot;{' '}
                        <span className="font-semibold text-brand-red-light">{selectedCount}</span> selected
                      </>
                    )}
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={selectAll}
                    className="px-3 py-1.5 rounded-lg bg-surface-card border border-surface-border text-gray-300 hover:text-white text-xs font-medium transition-colors"
                  >
                    Select All
                  </button>
                  <button
                    onClick={deselectAll}
                    className="px-3 py-1.5 rounded-lg bg-surface-card border border-surface-border text-gray-300 hover:text-white text-xs font-medium transition-colors"
                  >
                    Deselect All
                  </button>
                </div>
              </div>

              {/* Agent preview table with editable messages */}
              <div className="glass-card overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-left">
                    <thead>
                      <tr className="border-b border-surface-border/20">
                        <th className="px-4 py-3 text-[11px] uppercase text-gray-500 font-medium w-10"></th>
                        <th className="px-4 py-3 text-[11px] uppercase text-gray-500 font-medium">Name</th>
                        <th className="px-4 py-3 text-[11px] uppercase text-gray-500 font-medium">Phone</th>
                        <th className="px-4 py-3 text-[11px] uppercase text-gray-500 font-medium">Segment</th>
                        <th className="px-4 py-3 text-[11px] uppercase text-gray-500 font-medium">Score</th>
                        <th className="px-4 py-3 text-[11px] uppercase text-gray-500 font-medium">Strategy</th>
                        <th className="px-4 py-3 text-[11px] uppercase text-gray-500 font-medium min-w-[280px]">Message (editable)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredAgents.length === 0 ? (
                        <tr>
                          <td colSpan={7} className="px-4 py-12 text-center text-gray-500 text-sm">
                            No agents match the current filters.
                          </td>
                        </tr>
                      ) : (
                        filteredAgents.map((agent) => {
                          const isSelected = selectedAgentIds.has(agent.id);
                          const strategy = agentStrategyMap[agent.id] || 'unknown';
                          const strategyLabel = STRATEGY_DISPLAY[strategy] || strategy.replace(/_/g, ' ');
                          const segmentLabel = SEGMENT_DISPLAY[agent.segment] || agent.segment.replace(/_/g, ' ');
                          const currentMsg = editedMessages[agent.id] ?? agent.first_message ?? '';
                          const isEdited = currentMsg !== (agent.first_message || '');

                          return (
                            <tr
                              key={agent.id}
                              className={`border-b border-surface-border/20 transition-colors ${
                                isSelected
                                  ? 'bg-brand-red/5'
                                  : 'hover:bg-surface-card/40'
                              }`}
                            >
                              {/* Checkbox */}
                              <td className="px-4 py-3">
                                <div
                                  onClick={() => toggleAgentSelection(agent.id)}
                                  className={`w-4 h-4 rounded flex items-center justify-center border transition-all cursor-pointer ${
                                    isSelected
                                      ? 'bg-brand-red border-brand-red'
                                      : 'border-surface-border bg-transparent'
                                  }`}
                                >
                                  {isSelected && <Check className="w-3 h-3 text-white" />}
                                </div>
                              </td>

                              {/* Name */}
                              <td className="px-4 py-3 text-sm text-white font-medium">{agent.name}</td>

                              {/* Phone */}
                              <td className="px-4 py-3 text-sm text-gray-400 font-mono">{agent.phone}</td>

                              {/* Segment */}
                              <td className="px-4 py-3">
                                <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-brand-red/10 text-brand-red-light border border-brand-red/20">
                                  {segmentLabel}
                                </span>
                              </td>

                              {/* Score */}
                              <td className="px-4 py-3">
                                <span
                                  className={`text-sm font-semibold ${
                                    agent.score >= 70
                                      ? 'text-emerald-400'
                                      : agent.score >= 40
                                      ? 'text-amber-400'
                                      : agent.score >= 20
                                      ? 'text-orange-400'
                                      : 'text-red-400'
                                  }`}
                                >
                                  {agent.score}
                                </span>
                              </td>

                              {/* Strategy */}
                              <td className="px-4 py-3 text-xs text-gray-400">{strategyLabel}</td>

                              {/* Editable Message */}
                              <td className="px-4 py-3 min-w-[280px]">
                                <div className="space-y-1">
                                  <textarea
                                    value={currentMsg}
                                    onChange={(e) => updateMessage(agent.id, e.target.value)}
                                    rows={3}
                                    className="w-full bg-surface-card border border-surface-border/30 rounded px-2 py-1.5 text-xs text-gray-300 resize-none focus:outline-none focus:ring-1 focus:ring-brand-red/50 placeholder:text-gray-600"
                                    placeholder="Enter outreach message..."
                                    onClick={(e) => e.stopPropagation()}
                                  />
                                  {isEdited && (
                                    <button
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        resetMessage(agent);
                                      }}
                                      className="flex items-center gap-1 text-[10px] text-gray-500 hover:text-gray-300 transition-colors"
                                    >
                                      <RotateCcw className="w-2.5 h-2.5" />
                                      Reset to original
                                    </button>
                                  )}
                                </div>
                              </td>
                            </tr>
                          );
                        })
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Action buttons */}
              <div className="flex items-center gap-3 flex-wrap">
                <button
                  onClick={handleSendTelegram}
                  disabled={selectedCount === 0 || sending}
                  className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-brand-red hover:bg-brand-red/90 text-white text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {sending ? (
                    <Loader2 className="w-5 h-5 animate-spin" />
                  ) : (
                    <Send className="w-4 h-4" />
                  )}
                  {sending ? 'Sending...' : `Send via Telegram (${selectedCount})`}
                </button>

                <button
                  onClick={handleSendWhatsApp}
                  disabled={selectedCount === 0 || sending}
                  className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-green-600 hover:bg-green-700 text-white text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <MessageCircle className="w-4 h-4" />
                  Send via WhatsApp ({selectedCount})
                </button>

                <button
                  onClick={handleExportCSV}
                  disabled={selectedCount === 0}
                  className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-surface-card border border-surface-border text-gray-300 hover:text-white text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Download className="w-4 h-4" />
                  Export CSV ({selectedCount})
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {/* ═══════════════════════ Workflow Tab ═══════════════════════ */}
      {activeTab === 'workflow' && (
        <div className="space-y-6">
          {/* Strategy selector for workflow */}
          <div className="glass-card p-5 space-y-4">
            <h3 className="text-sm font-semibold text-white flex items-center gap-2">
              <Workflow className="w-4 h-4 text-gray-400" />
              Outreach Workflow Builder
            </h3>
            <p className="text-xs text-gray-500">
              Design a multi-step outreach sequence. Steps execute in order with configurable delays.
              If the agent doesn&apos;t respond after all steps, they are marked as permanently dormant.
            </p>

            <div className="flex items-center gap-3">
              <label className="text-xs text-gray-400">Strategy template:</label>
              <select
                value={workflowStrategy}
                onChange={(e) => setWorkflowStrategy(e.target.value)}
                className="bg-surface-card border border-surface-border/30 rounded px-3 py-1.5 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-brand-red/50"
              >
                <option value="direct_call">Direct Call</option>
                <option value="whatsapp_first">WhatsApp First</option>
                <option value="telegram_only">Telegram Only</option>
                <option value="no_contact">No Contact</option>
              </select>
            </div>
          </div>

          {/* Workflow step builder */}
          <div className="glass-card p-5">
            <WorkflowStepBuilder
              strategy={workflowStrategy}
              onChange={setWorkflowSteps}
            />
          </div>

          {/* Apply to selected agents */}
          <div className="glass-card p-5 space-y-4">
            <h3 className="text-sm font-semibold text-white">Apply to Agents</h3>
            <p className="text-xs text-gray-500">
              {selectedCount > 0
                ? `${selectedCount} agent${selectedCount !== 1 ? 's' : ''} selected from the Plan tab. The workflow will be saved for these agents.`
                : 'No agents selected. Go to the Plan Outreach tab and select agents first.'}
            </p>

            <div className="flex items-center gap-3">
              <button
                onClick={handleSaveWorkflow}
                disabled={selectedCount === 0 || workflowSteps.length === 0 || savingWorkflow}
                className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-brand-red hover:bg-brand-red/90 text-white text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {savingWorkflow ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : workflowSaved ? (
                  <CheckCircle2 className="w-4 h-4" />
                ) : (
                  <Save className="w-4 h-4" />
                )}
                {savingWorkflow ? 'Saving...' : workflowSaved ? 'Workflow Saved' : `Save Workflow (${selectedCount} agents)`}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ═══════════════════════ Results Tab ═══════════════════════ */}
      {activeTab === 'results' && (
        <div className="space-y-6">
          {!sendResult ? (
            <div className="text-center py-20 glass-card">
              <Send className="w-12 h-12 mx-auto mb-3 text-gray-600" />
              <p className="text-gray-400 text-sm">No outreach results yet.</p>
              <p className="text-gray-600 text-xs mt-1">
                Go to the Plan Outreach tab and send a campaign to see results here.
              </p>
            </div>
          ) : (
            <>
              {/* Stats cards */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {[
                  {
                    label: 'Total Requested',
                    value: sendResult.total_requested,
                    icon: Users,
                    color: 'text-blue-400',
                    bg: 'bg-blue-500/10',
                    border: 'border-blue-500/20',
                  },
                  {
                    label: 'Sent',
                    value: sendResult.sent,
                    icon: CheckCircle2,
                    color: 'text-emerald-400',
                    bg: 'bg-emerald-500/10',
                    border: 'border-emerald-500/20',
                  },
                  {
                    label: 'Failed',
                    value: sendResult.failed,
                    icon: XCircle,
                    color: sendResult.failed > 0 ? 'text-red-400' : 'text-gray-400',
                    bg: sendResult.failed > 0 ? 'bg-red-500/10' : 'bg-surface-card/40',
                    border: sendResult.failed > 0 ? 'border-red-500/20' : 'border-surface-border/30',
                  },
                  {
                    label: 'Skipped (No Telegram)',
                    value: sendResult.skipped_no_telegram,
                    icon: AlertCircle,
                    color: sendResult.skipped_no_telegram > 0 ? 'text-amber-400' : 'text-gray-400',
                    bg: sendResult.skipped_no_telegram > 0 ? 'bg-amber-500/10' : 'bg-surface-card/40',
                    border: sendResult.skipped_no_telegram > 0 ? 'border-amber-500/20' : 'border-surface-border/30',
                  },
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

              {/* Success list */}
              {sendResult.sent_agents && sendResult.sent_agents.length > 0 && (
                <div className="glass-card p-5 space-y-4">
                  <h3 className="text-sm font-semibold text-emerald-400 flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4" />
                    Successfully Sent ({sendResult.sent_agents.length})
                  </h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left">
                      <thead>
                        <tr className="border-b border-surface-border/20">
                          <th className="px-4 py-2 text-[11px] uppercase text-gray-500 font-medium">Name</th>
                          <th className="px-4 py-2 text-[11px] uppercase text-gray-500 font-medium">Phone</th>
                          <th className="px-4 py-2 text-[11px] uppercase text-gray-500 font-medium">Segment</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sendResult.sent_agents.map((agent: any, idx: number) => (
                          <tr key={agent.id || idx} className="border-b border-surface-border/20">
                            <td className="px-4 py-2.5 text-sm text-white">{agent.name || agent.agent_name || '-'}</td>
                            <td className="px-4 py-2.5 text-sm text-gray-400 font-mono">{agent.phone || '-'}</td>
                            <td className="px-4 py-2.5">
                              <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                                {SEGMENT_DISPLAY[agent.segment] || agent.segment || '-'}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Error list */}
              {sendResult.errors && sendResult.errors.length > 0 && (
                <div className="glass-card p-5 space-y-4">
                  <h3 className="text-sm font-semibold text-red-400 flex items-center gap-2">
                    <XCircle className="w-4 h-4" />
                    Errors ({sendResult.errors.length})
                  </h3>
                  <div className="space-y-2">
                    {sendResult.errors.map((err: any, idx: number) => (
                      <div
                        key={idx}
                        className="flex items-start gap-3 p-3 rounded-lg bg-red-500/5 border border-red-500/10"
                      >
                        <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
                        <div className="min-w-0">
                          {err.agent_name && (
                            <p className="text-sm font-medium text-white">{err.agent_name}</p>
                          )}
                          <p className="text-xs text-red-400">
                            {typeof err === 'string' ? err : err.error || err.message || JSON.stringify(err)}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
