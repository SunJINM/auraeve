import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import { DocumentCard } from '../blocks/DocumentCard'
import { useFileDrawer } from '../../../../store/fileDrawer'

describe('DocumentCard', () => {
  beforeEach(() => {
    useFileDrawer.getState().closeDrawer()
  })

  it('renders filename and type label', () => {
    render(
      <DocumentCard data={{ filename: '报告.docx', url: '/api/webui/resources/x/content', size: 2048 }} />,
    )
    expect(screen.getByText('报告.docx')).toBeInTheDocument()
    expect(screen.getByText(/Word 文档/)).toBeInTheDocument()
  })

  it('opens the document preview drawer on click', () => {
    render(<DocumentCard data={{ filename: 'a.md', filePath: '/ws/a.md', content: '# Hi' }} />)
    fireEvent.click(screen.getByRole('button', { name: /预览 a\.md/ }))
    const state = useFileDrawer.getState()
    expect(state.open).toBe(true)
    expect(state.payload?.mode).toBe('document')
    expect(state.payload?.filename).toBe('a.md')
    expect(state.payload?.content).toBe('# Hi')
  })

  it('exposes a download action without opening the drawer', () => {
    render(<DocumentCard data={{ filename: 'a.md', filePath: '/ws/a.md' }} />)
    expect(screen.getByRole('button', { name: '下载' })).toBeInTheDocument()
  })
})
