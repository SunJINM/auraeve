import { describe, expect, it } from 'vitest'

import { detectDocType, extname, formatSize, hljsLanguage } from '../documentKinds'

describe('documentKinds', () => {
  it('detects type by extension', () => {
    expect(detectDocType('a.md').kind).toBe('markdown')
    expect(detectDocType('a.pdf').kind).toBe('pdf')
    expect(detectDocType('a.docx').kind).toBe('word')
    expect(detectDocType('a.xlsx').kind).toBe('excel')
    expect(detectDocType('a.pptx').kind).toBe('ppt')
    expect(detectDocType('main.py').kind).toBe('code')
    expect(detectDocType('notes.txt').kind).toBe('text')
  })

  it('marks ppt and legacy doc as non-previewable, docx as previewable', () => {
    expect(detectDocType('a.pptx').previewable).toBe(false)
    expect(detectDocType('a.doc').previewable).toBe(false)
    expect(detectDocType('a.docx').previewable).toBe(true)
    expect(detectDocType('a.md').previewable).toBe(true)
  })

  it('falls back to mime when extension is unknown', () => {
    expect(detectDocType('blob', 'application/pdf').kind).toBe('pdf')
    expect(detectDocType('blob', 'image/png').kind).toBe('image')
    expect(detectDocType('blob', 'application/octet-stream').kind).toBe('other')
  })

  it('extname handles special files and casing', () => {
    expect(extname('path/to/Dockerfile')).toBe('dockerfile')
    expect(extname('a.TS')).toBe('ts')
    expect(extname('noext')).toBe('')
  })

  it('hljsLanguage maps known extensions', () => {
    expect(hljsLanguage('a.ts')).toBe('typescript')
    expect(hljsLanguage('a.unknownext')).toBeUndefined()
  })

  it('formatSize formats byte counts', () => {
    expect(formatSize(500)).toBe('500 B')
    expect(formatSize(2048)).toBe('2 KB')
    expect(formatSize(0)).toBe('')
  })
})
