import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ToolUseBlock } from '../blocks/ToolUseBlock'

describe('ToolUseBlock', () => {
  it('renders a Chinese activity line with the tool target', () => {
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

    expect(screen.getByText('搜索')).toBeInTheDocument()
    expect(screen.getByText(/Edit/)).toBeInTheDocument()
  })

  it('keeps long command targets truncated and result summary constrained', () => {
    render(
      <ToolUseBlock
        block={{
          id: 'tool_use:bash-1',
          type: 'tool_use',
          toolCallId: 'bash-1',
          toolName: 'Bash',
          arguments: {
            command:
              'powershell -NoProfile -Command "Get-ChildItem -Force C:\\Users\\Administrator\\Desktop\\Very\\Long\\Path\\That\\Should\\Not\\Break\\The\\Toolbar"',
          },
          result: 'STDERR: access denied',
          status: 'error',
        }}
      />,
    )

    const button = screen.getByRole('button')
    // 整行使用 truncate 容器，长命令不会撑破布局
    expect(button.querySelector('.truncate')).toBeTruthy()
    // 结果摘要靠右、有宽度约束
    expect(screen.getByText(/STDERR/).className).toMatch(/max-w-/)
  })
})
