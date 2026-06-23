import { describe, expect, it } from 'vitest'

import { sanitizeDocumentHtml } from '../documentHtml'

describe('sanitizeDocumentHtml', () => {
  it('removes scripts and inline event handlers from converted document HTML', () => {
    const dirty = '<table><tr><td onclick="alert(1)">单元格</td></tr></table><script>alert(2)</script>'

    const clean = sanitizeDocumentHtml(dirty)

    expect(clean).toContain('单元格')
    expect(clean).not.toContain('<script')
    expect(clean).not.toContain('onclick')
  })
})
