import { beforeEach, describe, expect, it } from 'vitest'

import { useAppStore } from '../app'

describe('app store sessions', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('removes legacy local session list when login succeeds', () => {
    localStorage.setItem('webui_sessions', JSON.stringify([{ key: 'old', title: '旧会话' }]))

    useAppStore.getState().setToken('')

    expect(localStorage.getItem('webui_sessions')).toBeNull()
  })
})
