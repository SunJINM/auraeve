import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, beforeEach } from 'vitest'

import { LiveActivityBlock } from '../blocks/LiveActivityBlock'
import { ToolDetail } from '../blocks/ToolDetail'
import { DiffView } from '../DiffView'
import { groupTranscriptBlocks } from '../groupTranscriptBlocks'
import { getVerb, buildDrawerPayload } from '../toolPresentation'
import { lineDiff, diffStats } from '../../../../lib/lineDiff'
import { useFileDrawer } from '../../../../store/fileDrawer'
import type { TranscriptBlock, TranscriptToolUseBlock } from '../types'

const activeRead = (id: string, path: string): TranscriptToolUseBlock => ({
  id,
  type: 'tool_use',
  toolCallId: id,
  toolName: 'Read',
  arguments: { file_path: path },
  result: null,
  status: 'running',
})

describe('tool-call redesign', () => {
  beforeEach(() => {
    useFileDrawer.setState({ open: false, payload: null })
  })

  it('getVerb conjugates tense by status', () => {
    expect(getVerb('Edit', 'running')).toBe('Editing')
    expect(getVerb('Edit', 'success')).toBe('Edited')
    expect(getVerb('Bash', 'preparing')).toBe('Running')
    expect(getVerb('Bash', 'error')).toBe('Ran')
  })

  it('aggregates concurrent active tools into one live_activity block', () => {
    const blocks: TranscriptBlock[] = [
      activeRead('a', '/x/a.ts'),
      activeRead('b', '/x/b.ts'),
      activeRead('c', '/x/c.ts'),
    ]
    const grouped = groupTranscriptBlocks(blocks)
    expect(grouped).toHaveLength(1)
    expect(grouped[0].type).toBe('live_activity')
  })

  it('live row shows present-tense verb and concurrent count', () => {
    render(
      <LiveActivityBlock
        block={{ id: 'live:a', type: 'live_activity', blocks: [activeRead('a', '/x/a.ts'), activeRead('b', '/x/b.ts')] }}
      />,
    )
    expect(screen.getByText('Reading')).toBeInTheDocument()
    expect(screen.getByText(/· 2/)).toBeInTheDocument()
  })

  it('lineDiff produces correct add/remove counts', () => {
    const lines = lineDiff('a\nb\nc', 'a\nB\nc\nd')
    const { added, removed } = diffStats(lines)
    expect(removed).toBe(1) // b
    expect(added).toBe(2) // B, d
  })

  it('DiffView renders +/- summary', () => {
    render(<DiffView oldString={'a\nb'} newString={'a\nc'} />)
    expect(screen.getByText('+1')).toBeInTheDocument()
    expect(screen.getByText('-1')).toBeInTheDocument()
  })

  it('clicking the Edit path header opens the file drawer with a diff payload', () => {
    const block: TranscriptToolUseBlock = {
      id: 'e1',
      type: 'tool_use',
      toolCallId: 'e1',
      toolName: 'Edit',
      arguments: { file_path: '/repo/src/foo.ts', old_string: 'const a = 1', new_string: 'const a = 2' },
      result: null,
      status: 'success',
    }
    render(<ToolDetail block={block} />)
    fireEvent.click(screen.getByText('/repo/src/foo.ts'))

    const state = useFileDrawer.getState()
    expect(state.open).toBe(true)
    expect(state.payload?.mode).toBe('diff')
    expect(state.payload?.filePath).toBe('/repo/src/foo.ts')
  })

  it('buildDrawerPayload returns null for non-file tools', () => {
    expect(buildDrawerPayload('Bash', { command: 'ls' }, 'out')).toBeNull()
  })
})
