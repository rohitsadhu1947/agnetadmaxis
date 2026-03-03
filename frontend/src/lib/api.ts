const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

async function fetchAPI<T>(path: string, options?: RequestInit): Promise<T> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('adm_token') : null;
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options?.headers,
    },
  });
  if (!res.ok) {
    if (res.status === 401) {
      // Token expired or invalid - clear and redirect
      if (typeof window !== 'undefined') {
        localStorage.removeItem('adm_token');
        localStorage.removeItem('adm_user');
        window.location.href = '/login';
      }
    }
    const errorData = await res.json().catch(() => ({}));
    let message = `API error: ${res.status}`;
    if (errorData.detail) {
      if (typeof errorData.detail === 'string') {
        message = errorData.detail;
      } else if (Array.isArray(errorData.detail)) {
        // Pydantic validation errors: [{loc: [...], msg: "...", type: "..."}, ...]
        message = errorData.detail.map((e: any) => {
          const field = e.loc?.slice(-1)[0] || 'unknown';
          return `${field}: ${e.msg}`;
        }).join('; ');
      }
    }
    throw new Error(message);
  }
  return res.json();
}

export const api = {
  // Auth
  login: (username: string, password: string) =>
    fetchAPI<{ token: string; token_type: string; user: any }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  getMe: () => fetchAPI<any>('/auth/me'),

  // Analytics / Dashboard
  getDashboardKPIs: () => fetchAPI<any>('/analytics/dashboard'),
  getActivationFunnel: () => fetchAPI<any>('/analytics/funnel'),
  getDormancyReasons: () => fetchAPI<any>('/analytics/dormancy-reasons'),
  getRegionalData: () => fetchAPI<any[]>('/analytics/regional'),
  getADMPerformance: () => fetchAPI<any[]>('/analytics/adm-performance'),
  getFeedbackTrends: (period?: string) =>
    fetchAPI<any>(`/analytics/feedback-trends?period=${period || 'weekly'}`),
  getActivityFeed: (limit: number = 20) =>
    fetchAPI<any[]>(`/analytics/activity-feed?limit=${limit}`),

  // Agents
  listAgents: (params?: Record<string, string>) => {
    const qs = params ? `?${new URLSearchParams(params).toString()}` : '';
    return fetchAPI<any>(`/agents/${qs}`);
  },
  getAgent: (id: number) => fetchAPI<any>(`/agents/${id}`),
  createAgent: (data: any) =>
    fetchAPI<any>('/agents/', { method: 'POST', body: JSON.stringify(data) }),
  updateAgent: (id: number, data: any) =>
    fetchAPI<any>(`/agents/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  transitionAgent: (id: number, state: string) =>
    fetchAPI<any>(`/agents/${id}/transition?new_state=${state}`, { method: 'POST' }),

  // ADMs
  listADMs: () => fetchAPI<any[]>('/adms/'),
  getADM: (id: number) => fetchAPI<any>(`/adms/${id}`),
  getADMAgents: (id: number) => fetchAPI<any>(`/adms/${id}/agents`),
  createADM: (data: any) =>
    fetchAPI<any>('/adms/', { method: 'POST', body: JSON.stringify(data) }),
  updateADM: (id: number, data: any) =>
    fetchAPI<any>(`/adms/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteADM: (id: number) =>
    fetchAPI<any>(`/adms/${id}`, { method: 'DELETE' }),
  bulkImportADMs: (adms: any[]) =>
    fetchAPI<any>('/adms/bulk-import', { method: 'POST', body: JSON.stringify({ adms }) }),

  // Interactions
  listInteractions: (params?: Record<string, string>) => {
    const qs = params ? `?${new URLSearchParams(params).toString()}` : '';
    return fetchAPI<any>(`/interactions/${qs}`);
  },
  getOverdueFollowups: () => fetchAPI<any>('/interactions/overdue'),

  // Feedback
  listFeedback: (params?: Record<string, string>) => {
    const qs = params ? `?${new URLSearchParams(params).toString()}` : '';
    return fetchAPI<any>(`/feedback/${qs}`);
  },
  getFeedbackAnalytics: () => fetchAPI<any>('/feedback/analytics'),
  getTopReasons: () => fetchAPI<any>('/feedback/top-reasons'),

  // Products
  listProducts: (category?: string) => {
    const qs = category ? `?category=${category}` : '';
    return fetchAPI<any[]>(`/products/${qs}`);
  },
  getProductCategories: () => fetchAPI<Record<string, number>>('/products/categories'),
  createProduct: (data: any) =>
    fetchAPI<any>('/products/', { method: 'POST', body: JSON.stringify(data) }),
  updateProduct: (id: number, data: any) =>
    fetchAPI<any>(`/products/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteProduct: (id: number) =>
    fetchAPI<any>(`/products/${id}`, { method: 'DELETE' }),

  // Onboarding
  getOnboardingPipeline: () => fetchAPI<any>('/onboarding/pipeline'),
  startOnboarding: (data: any) =>
    fetchAPI<any>('/onboarding/start', { method: 'POST', body: JSON.stringify(data) }),
  advanceOnboarding: (agentId: number, newStatus: string) =>
    fetchAPI<any>(`/onboarding/${agentId}/advance`, {
      method: 'PUT',
      body: JSON.stringify({ new_status: newStatus }),
    }),
  assignADMOnboarding: (agentId: number, admId: number) =>
    fetchAPI<any>(`/onboarding/${agentId}/assign-adm?adm_id=${admId}`, { method: 'POST' }),
  getOnboardingStats: () => fetchAPI<any>('/onboarding/stats'),

  // Training
  listTrainingCategories: () => fetchAPI<any>('/training/categories'),
  getTrainingProducts: (category: string) =>
    fetchAPI<any>(`/training/categories/${category}/products`),

  // Diary
  getDiaryToday: (admId: number, date?: string) => {
    const params = date ? `?date=${date}` : '';
    return fetchAPI<any>(`/diary/today/${admId}${params}`);
  },
  getDiaryUpcoming: (admId: number, days: number = 7) => fetchAPI<any>(`/diary/upcoming/${admId}?days=${days}`),
  createDiaryEntry: (data: any) => fetchAPI<any>('/diary/', { method: 'POST', body: JSON.stringify(data) }),
  completeDiaryEntry: (id: number, notes?: string) => {
    const params = notes ? `?completion_notes=${encodeURIComponent(notes)}` : '';
    return fetchAPI<any>(`/diary/${id}/complete${params}`, { method: 'POST' });
  },
  rescheduleDiaryEntry: (id: number, data: any) => {
    const params = new URLSearchParams();
    params.set('new_date', data.new_date);
    if (data.new_time) params.set('new_time', data.new_time);
    return fetchAPI<any>(`/diary/${id}/reschedule?${params.toString()}`, { method: 'POST' });
  },

  // Briefings
  getBriefing: (admId: number) => fetchAPI<any>(`/briefings/${admId}`),
  generateBriefing: (admId: number) => fetchAPI<any>(`/briefings/generate/${admId}`, { method: 'POST' }),
  getBriefingHistory: (admId: number) => fetchAPI<any>(`/briefings/history/${admId}`),

  // Interactions CREATE
  createInteraction: (data: any) => fetchAPI<any>('/interactions/', { method: 'POST', body: JSON.stringify(data) }),
  completeFollowup: (id: number, notes: string) => fetchAPI<any>(`/interactions/${id}/complete-followup`, { method: 'POST', body: JSON.stringify({ notes }) }),

  // Training (expanded)
  getTrainingModules: () => fetchAPI<any>('/training/modules'),
  getTrainingModule: (name: string) => fetchAPI<any>(`/training/modules/${name}`),
  submitQuiz: (data: any) => fetchAPI<any>('/training/quiz/submit', { method: 'POST', body: JSON.stringify(data) }),
  getTrainingProgress: (admId: number) => fetchAPI<any>(`/training/progress/${admId}`),
  getTrainingLeaderboard: () => fetchAPI<any>('/training/leaderboard'),

  // Assignment
  autoAssign: (data: any) => fetchAPI<any>('/assignment/auto-assign', { method: 'POST', body: JSON.stringify(data) }),
  rebalance: () => fetchAPI<any>('/assignment/rebalance', { method: 'POST' }),
  getAssignmentStats: () => fetchAPI<any>('/assignment/stats'),
  assignAgentToADM: (agentId: number, admId: number) =>
    fetchAPI<any>(`/agents/${agentId}/assign/${admId}`, { method: 'POST' }),
  unassignAgent: (agentId: number) =>
    fetchAPI<any>(`/agents/${agentId}/unassign`, { method: 'POST' }),
  bulkImportAgents: (agents: any[]) =>
    fetchAPI<any>('/agents/bulk-import', { method: 'POST', body: JSON.stringify({ agents }) }),
  deleteAgent: (id: number) =>
    fetchAPI<any>(`/agents/${id}`, { method: 'DELETE' }),

  // Agent states summary
  getAgentStatesSummary: () => fetchAPI<any>('/agents/states-summary'),

  // Playbooks + Communication (new backend routes)
  getPlaybooks: () => fetchAPI<any[]>('/playbooks/'),
  getPlaybook: (name: string) => fetchAPI<any>(`/playbooks/${name}`),
  getPlaybookRecommendation: (agentId: number) => fetchAPI<any>(`/playbooks/recommend/${agentId}`),
  getCommTemplates: () => fetchAPI<any[]>('/communication/templates'),
  getCommTemplate: (name: string) => fetchAPI<any>(`/communication/templates/${name}`),
  getCallScripts: () => fetchAPI<any[]>('/communication/call-scripts'),

  // Feedback Tickets (Intelligence Workflow)
  getReasonTaxonomy: () => fetchAPI<any[]>('/feedback-tickets/reasons'),
  getReasonsByBucket: () => fetchAPI<any>('/feedback-tickets/reasons/by-bucket'),
  submitFeedbackTicket: (data: any) =>
    fetchAPI<any>('/feedback-tickets/submit', { method: 'POST', body: JSON.stringify(data) }),
  listFeedbackTickets: (params?: Record<string, string>) => {
    const qs = params ? `?${new URLSearchParams(params).toString()}` : '';
    return fetchAPI<any>(`/feedback-tickets/${qs}`);
  },
  getFeedbackTicket: (ticketId: string) => fetchAPI<any>(`/feedback-tickets/${ticketId}`),
  respondToTicket: (ticketId: string, data: any) =>
    fetchAPI<any>(`/feedback-tickets/${ticketId}/respond`, { method: 'POST', body: JSON.stringify(data) }),
  markScriptSent: (ticketId: string) =>
    fetchAPI<any>(`/feedback-tickets/${ticketId}/script-sent`, { method: 'POST' }),
  rateScript: (ticketId: string, data: any) =>
    fetchAPI<any>(`/feedback-tickets/${ticketId}/rate-script`, { method: 'POST', body: JSON.stringify(data) }),
  getDepartmentQueue: (department: string) => fetchAPI<any>(`/feedback-tickets/queue/${department}`),
  getTicketAnalytics: () => fetchAPI<any>('/feedback-tickets/analytics/summary'),
  getAggregationAlerts: () => fetchAPI<any>('/feedback-tickets/alerts'),
  closeTicket: (ticketId: string) =>
    fetchAPI<any>(`/feedback-tickets/${ticketId}/close`, { method: 'POST' }),
  reopenTicket: (ticketId: string) =>
    fetchAPI<any>(`/feedback-tickets/${ticketId}/reopen`, { method: 'POST' }),
  getVoiceNoteUrl: (ticketId: string) =>
    `${API_BASE}/feedback-tickets/${ticketId}/voice`,
  getTicketMessages: (ticketId: string) =>
    fetchAPI<any>(`/feedback-tickets/${ticketId}/messages`),
  addTicketMessage: (ticketId: string, data: any) =>
    fetchAPI<any>(`/feedback-tickets/${ticketId}/messages`, { method: 'POST', body: JSON.stringify(data) }),

  // ======================== Cohort Analytics ========================
  getCohortSummary: () => fetchAPI<any>('/cohort/summary'),
  getCohortSegment: (segment: string) => fetchAPI<any>(`/cohort/segments/${segment}`),
  getCohortAgentAnalysis: (agentId: number) => fetchAPI<any>(`/cohort/agent/${agentId}/analysis`),
  reclassifyCohort: (agentIds?: number[]) =>
    fetchAPI<any>('/cohort/reclassify', {
      method: 'POST',
      body: JSON.stringify(agentIds ? { agent_ids: agentIds } : {}),
    }),
  getCohortEngagementPlan: () => fetchAPI<any>('/cohort/engagement-plan'),
  getCohortTrends: () => fetchAPI<any>('/cohort/trends'),

  // ======================== Bulk Upload with Cohort ========================
  bulkUploadCohort: (file: File) => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('adm_token') : null;
    const formData = new FormData();
    formData.append('file', file);
    return fetch(`${API_BASE}/agents/bulk-upload-cohort`, {
      method: 'POST',
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: formData,
    }).then(async (res) => {
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Upload failed: ${res.status}`);
      }
      return res.json();
    });
  },

  // ======================== Agent-Submitted Feedback (admin view) ========================
  getAgentSubmittedByDept: (department: string) =>
    fetchAPI<any>(`/feedback-tickets/agent-submitted/queue/${department}`),
  respondToAgentTicket: (ticketId: string, body: string, respondedBy: string) =>
    fetchAPI<any>(`/feedback-tickets/agent-submitted/${ticketId}/respond`, {
      method: 'POST',
      body: JSON.stringify({ response_text: body, responded_by: respondedBy }),
    }),
  getADMAgentTickets: (admId: number) =>
    fetchAPI<any>(`/feedback-tickets/agent-submitted/${admId}`),
  getAgentTicketDetail: (ticketId: string) =>
    fetchAPI<any>(`/agent-portal/feedback/ticket/${ticketId}`),

  // ======================== Outreach ========================
  sendTelegramOutreach: (agentIds: number[], customMessages?: Record<number, string>) =>
    fetchAPI<any>('/outreach/send-telegram', {
      method: 'POST',
      body: JSON.stringify({
        agent_ids: agentIds,
        ...(customMessages ? { custom_messages: customMessages } : {}),
      }),
    }),
  getWorkflowDefaults: (strategy: string) =>
    fetchAPI<any>(`/outreach/workflow-defaults/${strategy}`),
  saveOutreachWorkflow: (agentIds: number[], steps: any[]) =>
    fetchAPI<any>('/outreach/save-workflow', {
      method: 'POST',
      body: JSON.stringify({ agent_ids: agentIds, steps }),
    }),
  sendOutreachStep: (agentId: number, step: any) =>
    fetchAPI<any>('/outreach/send-step', {
      method: 'POST',
      body: JSON.stringify({ agent_id: agentId, step }),
    }),

  // ======================== Dormancy Detection ========================
  detectDormancy: (text: string) =>
    fetchAPI<any>('/agents/detect-dormancy', {
      method: 'POST',
      body: JSON.stringify({ text }),
    }),
};
