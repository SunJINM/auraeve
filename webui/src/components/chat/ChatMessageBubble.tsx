import { motion } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import clsx from 'clsx'
import type { ChatMessage } from '../../api/client'

export function ChatMessageBubble({ message, index }: { message: ChatMessage; index: number }) {
  const isUser = message.role === 'user'
  const isAssistant = message.role === 'assistant'

  return (
    <motion.div
      className={clsx('flex', isUser ? 'justify-end' : 'justify-start')}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, delay: Math.min(index * 0.015, 0.12) }}
    >
      <div
        className={clsx(
          'max-w-[88%] xl:max-w-[78%] rounded-[22px] border px-4 py-3 text-sm leading-7 shadow-sm',
          isUser ? 'rounded-br-md' : 'rounded-bl-md',
        )}
        style={{
          background: isUser ? 'var(--msg-user)' : 'var(--msg-agent)',
          color: 'var(--text-primary)',
          borderColor: 'var(--glass-border)',
        }}
      >
        <div className="mb-2 flex items-center gap-2 text-[11px]" style={{ color: 'var(--text-secondary)' }}>
          <span>{isUser ? '你' : isAssistant ? 'AuraEve' : '系统'}</span>
          {message.timestamp && <span>{formatTimestamp(message.timestamp)}</span>}
        </div>

        {isAssistant ? (
          <div className="chat-markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
          </div>
        ) : (
          <div className="whitespace-pre-wrap break-words">{message.content}</div>
        )}
      </div>
    </motion.div>
  )
}

function formatTimestamp(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}
