// Shapes of dict payloads that the OpenAPI schema leaves untyped.
export type Strength = 'strong' | 'partial' | 'none'
export interface Evidence { id: string; type?: string; title?: string; snippet?: string; score?: number; source?: string }
export interface Claim { text: string; evidence_ids: string[] }
export interface Check { claim: string; verdict: string; evidence_ids?: string[]; fix?: string | null }
export interface Critique { approve?: boolean; personalisation?: number; grounding?: number; issues?: string[]; send_back?: boolean }
export interface Compliance { allowed: boolean; violations?: string[] }
export interface Risk { score?: number; client_quality?: number | string; is_scam?: boolean; flags?: string[]; injection_detected?: boolean; explanation?: string }
export interface Price { type?: string; amount?: number; connects_cost?: number; connects_worth_it?: boolean; rationale?: string }
export interface Match { requirement: string; evidence_ids: string[]; strength: Strength }
export interface Fit { score?: number; matches?: Match[]; missing?: string[]; reasons?: string | string[] }
export interface JobSpec { requirements?: string[]; deliverables?: string[]; screening_questions?: string[]; hidden_needs?: string[] }
export interface Draft { cover_letter: string; claims?: Claim[]; screening_answers?: unknown[] }
export interface DryRun { connects_cost?: number; balance_before?: number; balance_after?: number; payload?: unknown }
export interface TraceItem { node: string; ts?: string | number; [k: string]: unknown }

export interface ThreadValues {
  job?: { title?: string; description?: string; budget?: number | null; [k: string]: unknown }
  job_spec?: JobSpec
  risk?: Risk
  fit?: Fit
  evidence?: Record<string, Evidence>
  decision?: { action?: 'bid' | 'watch' | 'skip'; reasons?: string[] }
  price?: Price
  draft?: Draft
  verification?: { checks?: Check[] }
  critiques?: Critique[]
  compliance?: Compliance
  status?: string
  trace?: TraceItem[]
  usage?: Record<string, unknown>
}
export interface ProposalPending {
  kind: 'proposal_approval'; thread_id: string; draft: Draft; evidence: Record<string, Evidence>
  claims: Claim[]; verification: { checks?: Check[] }; risk: Risk; price: Price
  critiques: Critique[]; compliance: Compliance; dry_run_preview: DryRun
}
export interface MessagePending {
  kind: 'message_approval'; thread_id: string; intent?: string; reply: string
  slots: { start: string; end: string }[]; compliance: Compliance; last_client_message?: string
}
export interface ChatMessage { from: string; text: string; ts?: string }
export interface MsgThread { thread_id: string; client_id?: string; job_id?: string; messages: ChatMessage[]; run?: { thread_id: string; status: string } | null }
export interface Settings {
  persona?: string; autonomy?: 'manual' | 'auto_skip_low_fit'; weekly_connects_budget?: number
  hourly_floor?: number; fixed_floor?: number; saved_searches?: { query: string; every_hours?: number }[]; marketplace?: string
  [k: string]: unknown
}
export type MemoryDump = Record<string, ({ key: string } & Record<string, unknown>)[]>
