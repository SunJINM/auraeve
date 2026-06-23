import DOMPurify from 'dompurify'

/** 清洗由 docx/xlsx 等文档解析库生成的 HTML，再交给 React 注入。 */
export function sanitizeDocumentHtml(html: string): string {
  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
  })
}
