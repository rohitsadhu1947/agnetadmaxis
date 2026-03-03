'use client';

import { useCallback, useEffect, useState } from 'react';
import { Phone, MessageCircle, Send, Clock, Plus, Trash2, ArrowDown, Ban, RotateCcw } from 'lucide-react';
import { api } from '@/lib/api';

export interface WorkflowStep {
  step_number: number;
  channel: string;
  message: string;
  delay_days: number;
}

interface Props {
  strategy: string;
  agentName?: string;
  onChange?: (steps: WorkflowStep[]) => void;
  compact?: boolean;
}

const CHANNEL_OPTIONS = [
  { value: 'whatsapp', label: 'WhatsApp', icon: MessageCircle, color: 'text-green-400' },
  { value: 'phone', label: 'Phone Call', icon: Phone, color: 'text-blue-400' },
  { value: 'telegram', label: 'Telegram', icon: Send, color: 'text-cyan-400' },
  { value: 'sms', label: 'SMS', icon: MessageCircle, color: 'text-yellow-400' },
  { value: 'wait', label: 'Wait', icon: Clock, color: 'text-gray-400' },
];

const MAX_STEPS = 5;

function getChannelMeta(channel: string) {
  return CHANNEL_OPTIONS.find((c) => c.value === channel) || CHANNEL_OPTIONS[4];
}

export default function WorkflowStepBuilder({ strategy, agentName, onChange, compact }: Props) {
  const [steps, setSteps] = useState<WorkflowStep[]>([]);
  const [loading, setLoading] = useState(true);
  const [defaultSteps, setDefaultSteps] = useState<WorkflowStep[]>([]);

  // Load defaults from backend
  useEffect(() => {
    if (!strategy || strategy === 'no_contact') {
      setSteps([]);
      setDefaultSteps([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    api
      .getWorkflowDefaults(strategy)
      .then((res) => {
        const loaded: WorkflowStep[] = (res.steps || []).map((s: any) => ({
          step_number: s.step_number,
          channel: s.channel,
          message: agentName ? s.message.replace(/\{name\}/g, agentName) : s.message,
          delay_days: s.delay_days,
        }));
        setSteps(loaded);
        setDefaultSteps(loaded);
      })
      .catch(() => {
        setSteps([]);
        setDefaultSteps([]);
      })
      .finally(() => setLoading(false));
  }, [strategy, agentName]);

  // Notify parent on change
  useEffect(() => {
    onChange?.(steps);
  }, [steps, onChange]);

  const updateStep = useCallback((idx: number, field: keyof WorkflowStep, value: any) => {
    setSteps((prev) => {
      const next = [...prev];
      next[idx] = { ...next[idx], [field]: value };
      return next;
    });
  }, []);

  const removeStep = useCallback((idx: number) => {
    setSteps((prev) => {
      const next = prev.filter((_, i) => i !== idx);
      return next.map((s, i) => ({ ...s, step_number: i + 1 }));
    });
  }, []);

  const addStep = useCallback(() => {
    setSteps((prev) => {
      if (prev.length >= MAX_STEPS) return prev;
      return [
        ...prev,
        {
          step_number: prev.length + 1,
          channel: 'whatsapp',
          message: '',
          delay_days: 3,
        },
      ];
    });
  }, []);

  const resetToDefaults = useCallback(() => {
    setSteps([...defaultSteps]);
  }, [defaultSteps]);

  if (strategy === 'no_contact') {
    return (
      <div className="flex items-center gap-2 text-gray-500 text-sm py-4">
        <Ban className="w-4 h-4" />
        No outreach workflow — strategy is &quot;No Contact&quot;
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-gray-400 text-sm py-4">
        <Clock className="w-4 h-4 animate-spin" />
        Loading workflow...
      </div>
    );
  }

  return (
    <div className="space-y-0">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs text-gray-500 uppercase tracking-wider">
          Outreach Workflow ({steps.length}/{MAX_STEPS} steps)
        </p>
        <button
          onClick={resetToDefaults}
          className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-300 transition-colors"
        >
          <RotateCcw className="w-3 h-3" />
          Reset to Defaults
        </button>
      </div>

      {/* Steps */}
      {steps.map((step, idx) => {
        const ch = getChannelMeta(step.channel);
        const Icon = ch.icon;
        return (
          <div key={idx}>
            {/* Connector arrow */}
            {idx > 0 && (
              <div className="flex items-center gap-2 py-1 pl-5">
                <ArrowDown className="w-4 h-4 text-gray-600" />
                <span className="text-[10px] text-gray-600">
                  {step.delay_days > 0 ? `Wait ${step.delay_days} day${step.delay_days !== 1 ? 's' : ''}` : 'Immediately'}
                </span>
              </div>
            )}

            {/* Step card */}
            <div className={`border border-surface-border/30 rounded-lg p-3 bg-[#0B1120] ${compact ? '' : ''}`}>
              <div className="flex items-start gap-3">
                {/* Step number badge */}
                <div className={`flex-shrink-0 w-7 h-7 rounded-full bg-surface-card flex items-center justify-center text-xs font-bold ${ch.color}`}>
                  {step.step_number}
                </div>

                <div className="flex-1 min-w-0 space-y-2">
                  {/* Channel + Delay row */}
                  <div className="flex items-center gap-2 flex-wrap">
                    <select
                      value={step.channel}
                      onChange={(e) => updateStep(idx, 'channel', e.target.value)}
                      className="bg-surface-card border border-surface-border/30 rounded px-2 py-1 text-xs text-gray-200 focus:outline-none focus:ring-1 focus:ring-brand-red/50"
                    >
                      {CHANNEL_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>

                    {idx > 0 && (
                      <div className="flex items-center gap-1">
                        <span className="text-[10px] text-gray-500">after</span>
                        <input
                          type="number"
                          min={0}
                          max={30}
                          value={step.delay_days}
                          onChange={(e) => updateStep(idx, 'delay_days', Math.max(0, parseInt(e.target.value) || 0))}
                          className="w-12 bg-surface-card border border-surface-border/30 rounded px-1.5 py-1 text-xs text-gray-200 text-center focus:outline-none focus:ring-1 focus:ring-brand-red/50"
                        />
                        <span className="text-[10px] text-gray-500">days</span>
                      </div>
                    )}

                    {steps.length > 1 && (
                      <button
                        onClick={() => removeStep(idx)}
                        className="ml-auto text-gray-600 hover:text-red-400 transition-colors"
                        title="Remove step"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>

                  {/* Message textarea */}
                  {step.channel !== 'wait' && (
                    <textarea
                      value={step.message}
                      onChange={(e) => updateStep(idx, 'message', e.target.value)}
                      placeholder="Enter outreach message..."
                      rows={compact ? 2 : 3}
                      className="w-full bg-surface-card border border-surface-border/30 rounded px-2 py-1.5 text-xs text-gray-300 resize-none focus:outline-none focus:ring-1 focus:ring-brand-red/50 placeholder:text-gray-600"
                    />
                  )}
                  {step.channel === 'wait' && (
                    <p className="text-[10px] text-gray-500 italic">Waiting period — no message sent</p>
                  )}
                </div>
              </div>
            </div>
          </div>
        );
      })}

      {/* Add step button */}
      {steps.length < MAX_STEPS && (
        <div className="flex items-center gap-2 py-1 pl-5">
          <ArrowDown className="w-4 h-4 text-gray-600" />
          <button
            onClick={addStep}
            className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-300 border border-dashed border-gray-700 rounded px-2 py-1 hover:border-gray-500 transition-colors"
          >
            <Plus className="w-3 h-3" />
            Add Step
          </button>
        </div>
      )}

      {/* Final dormancy marker */}
      {steps.length > 0 && (
        <>
          <div className="flex items-center gap-2 py-1 pl-5">
            <ArrowDown className="w-4 h-4 text-gray-600" />
            <span className="text-[10px] text-gray-600">If no response</span>
          </div>
          <div className="border border-red-900/30 rounded-lg p-3 bg-red-950/20 opacity-60">
            <div className="flex items-center gap-2 text-xs text-red-400">
              <Ban className="w-4 h-4" />
              Mark as Permanently Dormant
            </div>
          </div>
        </>
      )}
    </div>
  );
}
