export type TranscriptBlock =
  | TranscriptUserBlock
  | TranscriptToolUseBlock
  | TranscriptAssistantTextBlock
  | TranscriptAgentTaskBlock
  | TranscriptCollapsedActivityBlock
  | TranscriptLiveActivityBlock
  | TranscriptSystemNoticeBlock

export interface TranscriptUserBlock {
  id: string
  type: 'user'
  content: string
  timestamp: string
}

export interface TranscriptToolUseBlock {
  id: string
  type: 'tool_use'
  toolCallId: string
  toolName: string
  arguments: unknown
  result: string | null
  status: 'preparing' | 'running' | 'success' | 'error'
}

export interface TranscriptAssistantTextBlock {
  id: string
  type: 'assistant_text'
  content: string
  timestamp: string
  streaming?: boolean
}

export interface TranscriptAgentTaskBlock {
  id: string
  type: 'agent_task'
  title?: string
  summary: string
  status: string
  detail: Record<string, unknown>
  children?: TranscriptBlock[]
}

export interface TranscriptCollapsedActivityBlock {
  id: string
  type: 'collapsed_activity'
  activityType: 'read' | 'search'
  count: number
  blocks: TranscriptToolUseBlock[]
}

/** 渲染期生成的临时聚合块：多个工具并发执行中，合并为一行实时活动。不持久化、不来自后端。 */
export interface TranscriptLiveActivityBlock {
  id: string
  type: 'live_activity'
  blocks: TranscriptToolUseBlock[]
}

export interface TranscriptSystemNoticeBlock {
  id: string
  type: 'system_notice'
  level?: 'info' | 'warning' | 'error'
  content: string
}

export interface TranscriptRun {
  runId?: string | null
  status: 'idle' | 'running' | 'completed' | 'aborted'
  done: boolean
  aborted: boolean
}

export interface ChatTranscriptHistoryResp {
  sessionKey: string
  run: TranscriptRun
  blocks: TranscriptBlock[]
}

export interface ChatTranscriptBlockEvent {
  type: 'transcript.block'
  sessionKey: string
  runId?: string | null
  seq: number
  op: 'append' | 'replace'
  block: TranscriptBlock
}

export interface ChatTranscriptDoneEvent {
  type: 'transcript.done'
  sessionKey: string
  runId?: string | null
  seq: number
}

export type ChatTranscriptEvent = ChatTranscriptBlockEvent | ChatTranscriptDoneEvent
