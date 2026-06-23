import { useState } from 'react'
import { HiChevronRight } from 'react-icons/hi2'

import type { TranscriptToolUseBlock } from '../types'
import { useFileDrawer } from '../../../../store/fileDrawer'
import { GameEntryCard } from '../../../game/GameEntryCard'
import { buildDrawerPayload, getToolTarget, getVerb, isActiveStatus, isFileTool } from '../toolPresentation'
import { ToolDetail } from './ToolDetail'

const DOUDIZHU_RE = /\[\[doudizhu:([a-z0-9]+)\]\]/i

export function ToolUseBlock({ block, nested = false }: { block: TranscriptToolUseBlock; nested?: boolean }) {
  const [open, setOpen] = useState(false)
  const openDrawer = useFileDrawer((s) => s.openDrawer)

  // 斗地主开局：渲染「进入牌桌」入口卡片，替代默认工具行
  if (block.toolName === 'start_doudizhu') {
    const gameId = block.result?.match(DOUDIZHU_RE)?.[1]
    if (gameId) return <div className={nested ? '' : 'ml-8'}><GameEntryCard gameId={gameId} /></div>
  }

  const verb = getVerb(block.toolName, block.status)
  const target = getToolTarget(block.toolName, block.arguments)
  const isError = block.status === 'error'
  const isActive = isActiveStatus(block.status)

  // 文件类工具：目标即文件名，点击从右侧滑出完整文件 / 变更
  const drawerPayload = isFileTool(block.toolName)
    ? buildDrawerPayload(block.toolName, block.arguments, block.result)
    : null

  return (
    <div className={`${nested ? '' : 'ml-8'} max-w-[760px]`}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="row-btn group flex w-full items-center gap-2 rounded-[10px] px-2 py-1.5 text-left"
      >
        <span className={`min-w-0 flex-1 truncate text-[13px] ${isActive ? 'tool-shimmer' : ''}`}>
          {/* 失败：仅动词变红，目标保持常态色 */}
          <span
            className="font-medium"
            style={isActive ? undefined : { color: isError ? 'var(--danger)' : 'var(--text-secondary)' }}
          >
            {verb}
          </span>
          {target ? (
            drawerPayload ? (
              <span
                role="button"
                tabIndex={0}
                onClick={(e) => {
                  e.stopPropagation()
                  openDrawer(drawerPayload)
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.stopPropagation()
                    openDrawer(drawerPayload)
                  }
                }}
                className="tool-target-link"
                style={isActive ? undefined : { color: 'var(--text-tertiary)' }}
              >
                {' '}
                {target}
              </span>
            ) : (
              <span style={isActive ? undefined : { color: 'var(--text-tertiary)' }}>
                {' '}
                {target}
              </span>
            )
          ) : null}
        </span>

        <HiChevronRight
          size={14}
          className="shrink-0 opacity-0 transition group-hover:opacity-60"
          style={{ color: 'var(--text-tertiary)', transform: open ? 'rotate(90deg)' : 'none' }}
        />
      </button>

      {open && (
        <div className="reveal mt-1.5 pl-2">
          <ToolDetail block={block} />
        </div>
      )}
    </div>
  )
}
