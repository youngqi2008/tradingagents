import { ApiClient } from './request'

export interface MpUser {
  id: string
  username: string
  nickname?: string
  openid?: string
  phone?: string
  is_active: boolean
  balance: number
  membership_level_id?: string
  /** 小程序角色：normal=普通, risk_officer=风控专员 */
  role?: string
  role_name?: string
  created_at: string
  last_login?: string
  total_analyses: number
}

export interface UserRole {
  id?: string
  code: string
  name: string
  description: string
  sort_order?: number
  is_default?: boolean
  is_active?: boolean
  user_count?: number
}

export interface MembershipLevel {
  id: string
  name: string
  code: string
  sort_order: number
  monthly_free_generations: number
  per_generation_price: number
  monthly_free_asks: number
  per_ask_price: number
  monthly_price: number
  description: string
  is_default: boolean
  is_active: boolean
}

export interface BillingRecord {
  id: string
  user_id: string
  action_type: string
  amount: number
  balance_before: number
  balance_after: number
  is_free: boolean
  stock_code?: string
  remark: string
  created_at: string
}

export interface PaymentOrder {
  id: string
  order_no: string
  user_id: string
  amount: number
  status: string
  description: string
  created_at: string
  paid_at?: string
}

export interface BenefitCampaign {
  id: string
  name: string
  code: string
  description: string
  status: 'draft' | 'active' | 'paused' | 'ended'
  grant_scope: 'manual' | 'membership' | 'all'
  /** default=系统默认授予(不可再手动发); addon=增加授予(运营手动) */
  grant_mode: 'default' | 'addon'
  membership_level_id?: string
  cycle_type: 'once' | 'daily' | 'monthly'
  start_at?: string
  end_at?: string
  report_quota: number
  ask_quota: number
  push_quota: number
  stackable: boolean
  priority: number
}

export interface UserBenefitGrant {
  id: string
  user_id: string
  campaign_id: string
  campaign_name: string
  campaign_code: string
  source: string
  cycle_key: string
  report_limit: number
  ask_limit: number
  push_limit: number
  report_used: number
  ask_used: number
  push_used: number
  report_remaining: number
  ask_remaining: number
  push_remaining: number
  valid_from?: string
  valid_to?: string
  status: string
  remark: string
}

export interface MpAnalysisTask {
  task_id: string
  user_id: string
  user_nickname: string
  user_openid: string
  stock_code: string
  stock_name: string
  status: string
  progress: number
  message: string
  source?: string
  created_at: string
  completed_at?: string
  summary?: string
  recommendation?: string
  risk_level?: string
  error_message?: string
  reports?: Record<string, unknown>
}

export interface MpChatMessage {
  id: string
  role: string
  content: string
  stock_code?: string
  status: string
  error_message?: string
  created_at: string
}

export interface MpChatSession {
  session_id: string
  user_id: string
  user_nickname: string
  user_openid: string
  title: string
  stock_code?: string
  strategy_id: string
  status: string
  message_count: number
  created_at: string
  updated_at: string
  last_message?: string
  messages?: MpChatMessage[]
}

export interface MpUserDetail {
  user: MpUser
  membership_level_name: string
  monthly_fee: number
  membership_fee_paid: boolean
  report_free_used: number
  report_free_limit: number
  report_free_remaining: number
  ask_free_used: number
  ask_free_limit: number
  ask_free_remaining: number
  report_benefit_remaining?: number
  ask_benefit_remaining?: number
  push_benefit_remaining?: number
  benefit_grants?: UserBenefitGrant[]
  free_quota_used: number
  free_quota_limit: number
  free_quota_remaining: number
  task_total: number
  recharge_count: number
  billing_count: number
  order_count: number
}

export interface MpNotification {
  id: string
  title: string
  content: string
  notice_type: string
  target_type: string
  target_membership_level_id?: string
  target_user_ids?: string[]
  status: string
  recipient_count: number
  read_count: number
  created_by: string
  created_at: string
}

export const opsApi = {
  getStatistics: () =>
    ApiClient.get<{ data: OpsStatistics }>('/api/admin/ops/statistics'),

  listMpUsers: (params?: { skip?: number; limit?: number; keyword?: string; role?: string }) =>
    ApiClient.get<{ users: MpUser[]; total: number }>('/api/admin/ops/users', { params }),

  getMpUserDetail: (userId: string) =>
    ApiClient.get<MpUserDetail>(`/api/admin/ops/users/${userId}`),

  updateUserMembership: (userId: string, membership_level_id: string) =>
    ApiClient.put(`/api/admin/ops/users/${userId}/membership`, { membership_level_id }),

  listUserRoles: (params?: { active_only?: boolean }) =>
    ApiClient.get<{ roles: UserRole[] }>('/api/admin/ops/roles', { params }),

  createUserRole: (data: Partial<UserRole>) =>
    ApiClient.post('/api/admin/ops/roles', data),

  updateUserRoleDef: (id: string, data: Partial<UserRole>) =>
    ApiClient.put(`/api/admin/ops/roles/${id}`, data),

  deactivateUserRole: (id: string) =>
    ApiClient.delete(`/api/admin/ops/roles/${id}`),

  updateUserRole: (userId: string, role: string) =>
    ApiClient.put(`/api/admin/ops/users/${userId}/role`, { role }),

  grantUserRoles: (userIds: string[], role: string) =>
    ApiClient.post('/api/admin/ops/roles/grant', { user_ids: userIds, role }),

  setUserActive: (userId: string, is_active: boolean) =>
    ApiClient.put(`/api/admin/ops/users/${userId}/active`, null, { params: { is_active } }),

  adjustBalance: (userId: string, amount: number, remark?: string) =>
    ApiClient.post(`/api/admin/ops/users/${userId}/adjust-balance`, { amount, remark }),

  listMembershipLevels: () =>
    ApiClient.get<{ data: { levels: MembershipLevel[] } }>('/api/admin/ops/membership-levels'),

  createMembershipLevel: (data: Partial<MembershipLevel>) =>
    ApiClient.post('/api/admin/ops/membership-levels', data),

  updateMembershipLevel: (id: string, data: Partial<MembershipLevel>) =>
    ApiClient.put(`/api/admin/ops/membership-levels/${id}`, data),

  deleteMembershipLevel: (id: string) =>
    ApiClient.delete(`/api/admin/ops/membership-levels/${id}`),

  listBillingRecords: (params?: { user_id?: string; action_type?: string; skip?: number; limit?: number }) =>
    ApiClient.get<{ records: BillingRecord[]; total: number }>('/api/admin/ops/billing-records', { params }),

  listPaymentOrders: (params?: { user_id?: string; skip?: number; limit?: number }) =>
    ApiClient.get<{ orders: PaymentOrder[]; total: number }>('/api/admin/ops/payment-orders', { params }),

  listAnalysisTasks: (params?: {
    status?: string
    user_id?: string
    stock_code?: string
    keyword?: string
    skip?: number
    limit?: number
  }) =>
    ApiClient.get<{ data: { tasks: MpAnalysisTask[]; total: number } }>(
      '/api/admin/ops/analysis-tasks',
      { params }
    ),

  getAnalysisTask: (taskId: string) =>
    ApiClient.get<{ data: MpAnalysisTask }>(`/api/admin/ops/analysis-tasks/${taskId}`),

  markTaskFailed: (taskId: string) =>
    ApiClient.post(`/api/admin/ops/analysis-tasks/${taskId}/mark-failed`),

  deleteTask: (taskId: string) =>
    ApiClient.delete(`/api/admin/ops/analysis-tasks/${taskId}`),

  listChatSessions: (params?: {
    status?: string
    user_id?: string
    keyword?: string
    skip?: number
    limit?: number
  }) =>
    ApiClient.get<{ data: { sessions: MpChatSession[]; total: number } }>(
      '/api/admin/ops/chat-sessions',
      { params }
    ),

  getChatSession: (sessionId: string) =>
    ApiClient.get<{ data: MpChatSession }>(`/api/admin/ops/chat-sessions/${sessionId}`),

  updateChatSessionStatus: (sessionId: string, status: string) =>
    ApiClient.put(`/api/admin/ops/chat-sessions/${sessionId}/status`, { status }),

  deleteChatSession: (sessionId: string) =>
    ApiClient.delete(`/api/admin/ops/chat-sessions/${sessionId}`),

  listMpNotifications: (params?: { skip?: number; limit?: number }) =>
    ApiClient.get<{ data: { notifications: MpNotification[]; total: number } }>(
      '/api/admin/ops/notifications',
      { params }
    ),

  createMpNotification: (data: {
    title: string
    content: string
    target_type: string
    target_membership_level_id?: string
    target_user_ids?: string[]
  }) => ApiClient.post('/api/admin/ops/notifications', data),

  revokeMpNotification: (id: string) =>
    ApiClient.post(`/api/admin/ops/notifications/${id}/revoke`),

  listBenefitCampaigns: (params?: { status?: string; skip?: number; limit?: number }) =>
    ApiClient.get<{ data: { campaigns: BenefitCampaign[] } }>(
      '/api/admin/ops/benefit-campaigns',
      { params }
    ),

  createBenefitCampaign: (data: Partial<BenefitCampaign>) =>
    ApiClient.post('/api/admin/ops/benefit-campaigns', data),

  updateBenefitCampaign: (id: string, data: Partial<BenefitCampaign>) =>
    ApiClient.put(`/api/admin/ops/benefit-campaigns/${id}`, data),

  listUserBenefits: (userId: string, includeInactive = false) =>
    ApiClient.get<{ data: { grants: UserBenefitGrant[]; summary: any } }>(
      `/api/admin/ops/users/${userId}/benefits`,
      { params: { include_inactive: includeInactive } }
    ),

  assignUserBenefit: (
    userId: string,
    data: {
      campaign_id: string
      remark?: string
      report_quota?: number
      ask_quota?: number
      push_quota?: number
      valid_from?: string
      valid_to?: string
    }
  ) => ApiClient.post(`/api/admin/ops/users/${userId}/benefits`, data),

  revokeUserBenefit: (grantId: string) =>
    ApiClient.post(`/api/admin/ops/benefit-grants/${grantId}/revoke`),

  listOpsFavorites: (params?: {
    user_id?: string
    stock_code?: string
    mp_only?: boolean
    skip?: number
    limit?: number
  }) =>
    ApiClient.get<{ data: { items: OpsFavoriteItem[]; total: number } }>(
      '/api/admin/ops/favorites',
      params
    ),

  listUserFavorites: (userId: string) =>
    ApiClient.get<{ data: { favorites: any[]; total: number } }>(
      `/api/admin/ops/users/${userId}/favorites`
    ),

  addUserFavorite: (
    userId: string,
    data: { stock_code: string; stock_name?: string; market?: string; notes?: string }
  ) => ApiClient.post(`/api/admin/ops/users/${userId}/favorites`, data),

  removeUserFavorite: (userId: string, stockCode: string) =>
    ApiClient.delete(`/api/admin/ops/users/${userId}/favorites/${stockCode}`),

  runFavoritesDigest: (userId?: string) =>
    ApiClient.post('/api/admin/ops/favorites/digest/run', {}, {
      params: userId ? { user_id: userId } : undefined,
    }),

  runMarketReview: () => ApiClient.post('/api/admin/ops/market-review/run', {}),
}

export interface OpsFavoriteItem {
  user_id: string
  storage_user_id: string
  is_mp_user: boolean
  nickname?: string
  stock_code: string
  stock_name: string
  market: string
  notes: string
  tags: string[]
  added_at?: string
}
