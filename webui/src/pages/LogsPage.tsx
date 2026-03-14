import { useEffect, useMemo, useRef, useState } from 'react'
import {
  logsApi,
  type LogEvent,
  type LogStreamEvent,
  type LogsStatsResp,
} from '../api/client'
import './LogsPage.css'

const LEVELS = ['trace', 'debug', 'info', 'warn', 'error', 'fatal']

function formatTime(ts?: string) {
  if (!ts) return '--'
  const d = new Date(ts)
  return Number.isNaN(d.getTime()) ? ts : d.toLocaleString()
}

function fromDatetimeLocal(value: string): string | undefined {
  if (!value.trim()) return undefined
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return undefined
  return d.toISOString()
}

export function LogsPage() {
  const [loading, setLoading] = useState(false)
  const [streaming, setStreaming] = useState(true)
  const [events, setEvents] = useState<LogEvent[]>([])
  const [history, setHistory] = useState<LogEvent[]>([])
  const [context, setContext] = useState<LogEvent[]>([])
  const [selected, setSelected] = useState<LogEvent | null>(null)
  const [stats, setStats] = useState<LogsStatsResp | null>(null)
  const [text, setText] = useState('')
  const [subsystems, setSubsystems] = useState('')
  const [kinds, setKinds] = useState('')
  const [sessionKey, setSessionKey] = useState('')
  const [runId, setRunId] = useState('')
  const [channel, setChannel] = useState('')
  const [fromTsInput, setFromTsInput] = useState('')
  const [toTsInput, setToTsInput] = useState('')
  const [cursor, setCursor] = useState<number | undefined>(undefined)
  const [levels, setLevels] = useState<string[]>(['info', 'warn', 'error', 'fatal'])
  const [message, setMessage] = useState('')
  const unsubRef = useRef<(() => void) | null>(null)

  const parseList = (raw: string) => raw.split(',').map((x) => x.trim()).filter(Boolean)
  const visibleEvents = events.slice().reverse().slice(0, 400)
  const visibleHistory = history.slice(0, 500)

  const refreshStats = async () => {
    try {
      const res = await logsApi.stats(fromDatetimeLocal(fromTsInput), fromDatetimeLocal(toTsInput))
      setStats(res)
    } catch (err: unknown) {
      setMessage(err instanceof Error ? err.message : String(err))
    }
  }

  const refreshTail = async (reset = false) => {
    setLoading(true)
    try {
      const res = await logsApi.tail(reset ? undefined : cursor, 500, 250000)
      setCursor(res.cursor)
      setEvents((prev) => (reset || res.reset ? res.events : [...prev, ...res.events]).slice(-1200))
    } catch (err: unknown) {
      setMessage(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  const search = async () => {
    setLoading(true)
    try {
      const res = await logsApi.search({
        levels,
        subsystems: parseList(subsystems),
        kinds: parseList(kinds),
        text: text || undefined,
        sessionKey: sessionKey || undefined,
        runId: runId || undefined,
        channel: channel || undefined,
        fromTs: fromDatetimeLocal(fromTsInput),
        toTs: fromDatetimeLocal(toTsInput),
        limit: 300,
        offset: 0,
      })
      setHistory(res.events)
      setContext([])
      setSelected(res.events[0] || null)
      setMessage(`查询完成：${res.total} 条，展示 ${res.events.length} 条`)
      await refreshStats()
    } catch (err: unknown) {
      setMessage(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  const loadContext = async (eventId?: string) => {
    if (!eventId) return
    try {
      const res = await logsApi.context(eventId, 20, 20)
      setContext(res.events)
    } catch (err: unknown) {
      setMessage(err instanceof Error ? err.message : String(err))
    }
  }

  const exportLogs = async (format: 'jsonl' | 'csv') => {
    setLoading(true)
    try {
      await logsApi.export({
        format,
        levels,
        subsystems: parseList(subsystems),
        kinds: parseList(kinds),
        text: text || undefined,
        sessionKey: sessionKey || undefined,
        runId: runId || undefined,
        channel: channel || undefined,
        fromTs: fromDatetimeLocal(fromTsInput),
        toTs: fromDatetimeLocal(toTsInput),
        limit: 10000,
      })
      setMessage(`导出成功（${format}）`)
    } catch (err: unknown) {
      setMessage(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refreshTail(true)
    void refreshStats()
  }, [])

  useEffect(() => {
    if (!streaming) {
      unsubRef.current?.()
      unsubRef.current = null
      return
    }
    unsubRef.current?.()
    unsubRef.current = logsApi.stream(
      (evt: LogStreamEvent) => {
        if (evt.type !== 'event' || !evt.event) return
        setEvents((prev) => [...prev, evt.event!].slice(-1200))
      },
      { levels, subsystems: parseList(subsystems), text: text || undefined },
    )
    return () => {
      unsubRef.current?.()
      unsubRef.current = null
    }
  }, [streaming, levels.join(','), text, subsystems])

  const mergedStats = useMemo(() => {
    const levelStats = stats?.byLevel || {}
    return LEVELS.map((level) => ({ level, count: levelStats[level] || 0 }))
  }, [stats])

  const errorTotal = (stats?.byLevel.error || 0) + (stats?.byLevel.fatal || 0)
  const infoTotal = (stats?.byLevel.info || 0) + (stats?.byLevel.debug || 0) + (stats?.byLevel.trace || 0)

  const pick = (event: LogEvent) => {
    setSelected(event)
    void loadContext(event.eventId)
  }

  const summarizeStatus = (item: LogEvent) => {
    const attrs = item.attrs || {}
    const status = typeof attrs.status === 'string' ? attrs.status : ''
    if (status) return status
    if (item.level === 'error' || item.level === 'fatal') return 'failed'
    if (item.level === 'warn') return 'warn'
    return 'ok'
  }

  const summarizeDuration = (item: LogEvent) => {
    const raw = item.attrs && typeof item.attrs.durationMs === 'number' ? item.attrs.durationMs : undefined
    if (typeof raw !== 'number') return '--'
    return `${raw}ms`
  }

  const fullContent = (item: LogEvent) => {
    const attrs = item.attrs || {}
    const fullFromAttrs = typeof attrs.fullContent === 'string' ? attrs.fullContent : ''
    if (fullFromAttrs) return `${item.message || ''}\n${fullFromAttrs}`.trim()
    const textFromAttrs = typeof attrs.resultText === 'string' ? attrs.resultText : ''
    if (textFromAttrs) return `${item.message || ''}\n${textFromAttrs}`.trim()
    return item.message || '-'
  }

  return (
    <div className="logs-shell">
      <div className="logs-orb logs-orb-a" />
      <div className="logs-orb logs-orb-b" />
      <div className="logs-orb logs-orb-c" />
      <div className="logs-stage">
        <div className="logs-hero">
          <div>
            <h2 className="logs-title">日志中心</h2>
            <p className="logs-subtitle">实时追踪、历史检索、事件窗口定位、结构化属性分析</p>
          </div>
          <div className="logs-actions">
            <button className="logs-btn" onClick={() => void refreshTail(true)} disabled={loading}>刷新 Tail</button>
            <button className="logs-btn primary" onClick={() => void search()} disabled={loading}>执行查询</button>
            <button className="logs-btn" onClick={() => void exportLogs('jsonl')} disabled={loading}>导出 JSONL</button>
            <button className="logs-btn" onClick={() => void exportLogs('csv')} disabled={loading}>导出 CSV</button>
            <button className={`logs-btn ${streaming ? 'live' : ''}`} onClick={() => setStreaming((v) => !v)}>
              {streaming ? '实时中' : '已暂停'}
            </button>
          </div>
        </div>

        <div className="logs-kpis">
          <div className="logs-kpi"><span>总事件</span><b>{stats?.total || 0}</b></div>
          <div className="logs-kpi"><span>错误/Fatal</span><b>{errorTotal}</b></div>
          <div className="logs-kpi"><span>Info/Debug</span><b>{infoTotal}</b></div>
          <div className="logs-kpi"><span>实时缓存</span><b>{events.length}</b></div>
        </div>

        {message && <div className="logs-toast">{message}</div>}

        <div className="logs-layout">
          <aside className="logs-filter">
            <h3>筛选器</h3>
            <input className="logs-input" placeholder="关键词" value={text} onChange={(e) => setText(e.target.value)} />
            <input className="logs-input" placeholder="subsystem，逗号分隔" value={subsystems} onChange={(e) => setSubsystems(e.target.value)} />
            <input className="logs-input" placeholder="kind，逗号分隔（log,audit,event,trace）" value={kinds} onChange={(e) => setKinds(e.target.value)} />
            <input className="logs-input" placeholder="sessionKey" value={sessionKey} onChange={(e) => setSessionKey(e.target.value)} />
            <input className="logs-input" placeholder="runId" value={runId} onChange={(e) => setRunId(e.target.value)} />
            <input className="logs-input" placeholder="channel" value={channel} onChange={(e) => setChannel(e.target.value)} />
            <input className="logs-input" type="datetime-local" value={fromTsInput} onChange={(e) => setFromTsInput(e.target.value)} />
            <input className="logs-input" type="datetime-local" value={toTsInput} onChange={(e) => setToTsInput(e.target.value)} />
            <div className="logs-levels">
              {LEVELS.map((level) => (
                <label key={level} className="logs-pill">
                  <input
                    type="checkbox"
                    checked={levels.includes(level)}
                    onChange={(e) => {
                      setLevels((prev) => {
                        if (e.target.checked) return Array.from(new Set([...prev, level]))
                        return prev.filter((v) => v !== level)
                      })
                    }}
                  />
                  {level}
                </label>
              ))}
            </div>
            <h4>Top Subsystem</h4>
            <div className="logs-tags">
              {(stats?.topSubsystems || []).slice(0, 8).map((item) => (
                <button key={item.subsystem} className="logs-tag" onClick={() => setSubsystems(item.subsystem)}>
                  {item.subsystem} ({item.count})
                </button>
              ))}
            </div>
          </aside>

          <section className="logs-main">
            <div className="logs-panel logs-focus logs-stream-panel">
              <h3>实时日志内容（上下文）流</h3>
              <div className="logs-stream-list">
                {visibleEvents.map((item, idx) => (
                  <button
                    key={`${item.eventId || idx}-live`}
                    className={`logs-stream-row ${selected?.eventId === item.eventId ? 'active' : ''}`}
                    onClick={() => pick(item)}
                  >
                    <span className="time">{formatTime(item.ts)}</span>
                    <span className="content">{fullContent(item)}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="logs-panel">
              <h3>事件详情（完整输出）</h3>
              <div className="logs-meta">
                <div><span>时间</span><b>{formatTime(selected?.ts)}</b></div>
                <div><span>subsystem</span><b>{selected?.subsystem || '-'}</b></div>
                <div><span>kind</span><b>{selected?.kind || '-'}</b></div>
                <div><span>level</span><b>{selected?.level || '-'}</b></div>
                <div><span>session</span><b>{selected?.sessionKey || '-'}</b></div>
                <div><span>runId</span><b>{selected?.runId || '-'}</b></div>
                <div><span>channel</span><b>{selected?.channel || '-'}</b></div>
                <div><span>status</span><b>{selected ? summarizeStatus(selected) : '-'}</b></div>
                <div><span>duration</span><b>{selected ? summarizeDuration(selected) : '-'}</b></div>
              </div>
              <pre className="logs-attrs logs-content-full">{selected ? fullContent(selected) : '请选择一条事件'}</pre>
              <h4 className="logs-subhead">事件窗口（前后事件）</h4>
              <div className="logs-list compact">
                {context.map((item, idx) => (
                  <button key={`${item.eventId || idx}-ctx-main`} className="logs-row simple" onClick={() => setSelected(item)}>
                    <span className="time">{formatTime(item.ts)}</span>
                    <span className="msg">
                      [{item.level || '-'}] {item.subsystem || '-'} {fullContent(item)}
                    </span>
                  </button>
                ))}
                {!context.length && <div className="logs-muted">点击上方实时日志查看事件窗口</div>}
              </div>
            </div>

            <div className="logs-panel">
              <h3>历史查询结果</h3>
              <div className="logs-list">
                {visibleHistory.map((item, idx) => (
                  <button key={`${item.eventId || idx}-history`} className={`logs-row ${selected?.eventId === item.eventId ? 'active' : ''}`} onClick={() => pick(item)}>
                    <span className={`badge status-${summarizeStatus(item)}`}>{summarizeStatus(item)}</span>
                    <span className="badge">{item.level || '-'}</span>
                    <span className="badge">{item.kind || '-'}</span>
                    <span className="time">{formatTime(item.ts)}</span>
                    <span className="subsystem">{item.subsystem || '-'}</span>
                    <span className="duration">{summarizeDuration(item)}</span>
                    <span className="msg">{fullContent(item)}</span>
                  </button>
                ))}
                {!visibleHistory.length && <div className="logs-muted">暂无查询结果</div>}
              </div>
            </div>
          </section>

          <aside className="logs-detail">
            <div className="logs-panel">
              <h3>等级分布</h3>
              <div className="logs-stat-grid">
                {mergedStats.map((entry) => (
                  <div key={entry.level} className="logs-stat-item">
                    <span>{entry.level}</span>
                    <b>{entry.count}</b>
                  </div>
                ))}
              </div>
            </div>
            <div className="logs-panel">
              <h3>类型分布</h3>
              <div className="logs-list compact">
                {(stats?.topKinds || []).map((item, idx) => (
                  <button key={`${item.kind || idx}-kind`} className="logs-row simple" onClick={() => setKinds(item.kind || '')}>
                    <span className="time">{item.kind || '-'}</span>
                    <span className="msg">{item.count}</span>
                  </button>
                ))}
              </div>
            </div>
            <div className="logs-panel">
              <h3>渠道分布</h3>
              <div className="logs-list compact">
                {(stats?.topChannels || []).map((item, idx) => (
                  <button key={`${item.channel || idx}-channel`} className="logs-row simple" onClick={() => setChannel(item.channel || '')}>
                    <span className="time">{item.channel || '-'}</span>
                    <span className="msg">{item.count}</span>
                  </button>
                ))}
              </div>
            </div>
            <div className="logs-panel">
              <h3>最近错误</h3>
              <div className="logs-list compact">
                {(stats?.recentErrors || []).map((item, idx) => (
                  <button key={`${item.eventId || idx}-error`} className="logs-row simple" onClick={() => pick(item)}>
                    <span className="time">{formatTime(item.ts)}</span>
                    <span className="msg">{item.message || '-'}</span>
                  </button>
                ))}
              </div>
            </div>
          </aside>
        </div>
      </div>
    </div>
  )
}
