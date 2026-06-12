import { fireEvent, render, screen } from '@testing-library/react'
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

  it('truncates long command targets and hides raw result until expanded', () => {
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
    // 折叠态不再展示结果摘要/退出码
    expect(screen.queryByText(/access denied/)).toBeNull()

    // 展开后命令与错误输出以结构化面板呈现
    fireEvent.click(button)
    expect(screen.getByText('命令')).toBeInTheDocument()
    expect(screen.getByText('错误输出')).toBeInTheDocument()
    expect(screen.getByText(/access denied/)).toBeInTheDocument()
  })
})
