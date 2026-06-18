import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { FileChangesResp } from '../../../../api/client'
import { FileChangesView } from '../FileChangesView'

const gitData: FileChangesResp = {
  git: true,
  repoRoot: '/repo',
  anchor: 'src/b.ts',
  files: [
    {
      path: 'src/a.ts',
      status: 'modified',
      mode: 'diff',
      added: 1,
      removed: 1,
      hunks: [
        {
          header: '@@ -1,2 +1,2 @@',
          lines: [
            { type: 'ctx', oldNo: 1, newNo: 1, text: 'keep' },
            { type: 'del', oldNo: 2, text: 'old' },
            { type: 'add', newNo: 2, text: 'new' },
          ],
        },
      ],
    },
    {
      path: 'src/b.ts',
      status: 'added',
      mode: 'diff',
      added: 1,
      removed: 0,
      hunks: [{ header: '@@ -0,0 +1 @@', lines: [{ type: 'add', newNo: 1, text: 'brand new' }] }],
    },
  ],
}

describe('FileChangesView', () => {
  it('renders every changed file with status badge and hunk header', () => {
    render(<FileChangesView data={gitData} />)
    expect(screen.getByText(/src\/a\.ts/)).toBeInTheDocument()
    expect(screen.getByText(/src\/b\.ts/)).toBeInTheDocument()
    expect(screen.getByText('已修改')).toBeInTheDocument()
    expect(screen.getByText('新增')).toBeInTheDocument()
    expect(screen.getByText('@@ -1,2 +1,2 @@')).toBeInTheDocument()
    expect(screen.getByText('old')).toBeInTheDocument()
    expect(screen.getByText('new')).toBeInTheDocument()
  })

  it('renders empty-state when no files', () => {
    render(<FileChangesView data={{ git: true, repoRoot: '/repo', anchor: null, files: [] }} />)
    expect(screen.getByText('（无变更）')).toBeInTheDocument()
  })

  it('renders binary file notice without lines', () => {
    render(
      <FileChangesView
        data={{
          git: true,
          repoRoot: '/repo',
          anchor: 'img.png',
          files: [
            { path: 'img.png', status: 'modified', mode: 'diff', added: 0, removed: 0, binary: true, hunks: [] },
          ],
        }}
      />,
    )
    expect(screen.getByText(/二进制文件/)).toBeInTheDocument()
  })
})
