import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ToolUseBlock } from '../blocks/ToolUseBlock'

describe('ToolUseBlock', () => {
  it('shows Grep by its tool name', () => {
    render(
      <ToolUseBlock
        block={{
          id: 'tool_use:grep-1',
          type: 'tool_use',
          toolCallId: 'grep-1',
          toolName: 'Grep',
          arguments: { pattern: 'Edit', path: 'src' },
          result: null,
          status: 'running',
        }}
      />,
    )

    expect(screen.getByText(/Grep/)).toBeInTheDocument()
    expect(screen.queryByText(/Search/)).not.toBeInTheDocument()
  })
})
