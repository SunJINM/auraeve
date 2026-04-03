export type TranscriptBlock =
  | TranscriptUserBlock
  | TranscriptToolCallBlock
  | TranscriptToolResultBlock
  | TranscriptAssistantTextBlock
  | TranscriptRunStatusBlock
  | TranscriptCollapsedActivityBlock

export interface TranscriptUserBlock {
  id: string
  type: 'user'
  content: string
  timestamp: string
}

export interface TranscriptToolCallBlock {
  id: string
  type: 'tool_call'
  toolCallId: string
  toolName: string
  arguments: unknown
}

export interface TranscriptToolResultBlock {
  id: string
  type: 'tool_result'
  toolCallId: string
  toolName: string
  content: string
}

export interface TranscriptAssistantTextBlock {
  id: string
  type: 'assistant_text'
  content: string
  timestamp: string
}

export interface TranscriptRunStatusBlock {
  id: string
  type: 'run_status'
  status: 'started' | 'running' | 'completed' | 'aborted'
  content: string
  timestamp: string
}

export interface TranscriptCollapsedActivityBlock {
  id: string
  type: 'collapsed_activity'
  activityType: 'read'
  count: number
  blocks: Array<TranscriptToolCallBlock | TranscriptToolResultBlock>
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
