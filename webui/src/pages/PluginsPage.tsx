import { useCallback, useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { HoverEffectCard } from '../components/HoverEffectCard'
import { pluginApi, type PluginActionResp, type PluginDoctorResp, type PluginRecord } from '../api/client'
import './ManagePages.css'

type Notice = { type: 'ok' | 'error' | 'warn'; text: string } | null

export function PluginsPage() {
  const [plugins, setPlugins] = useState<PluginRecord[]>([])
  const [doctor, setDoctor] = useState<PluginDoctorResp | null>(null)
  const [selectedId, setSelectedId] = useState('')
  const [selected, setSelected] = useState<PluginRecord | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [installPath, setInstallPath] = useState('')
  const [installLink, setInstallLink] = useState(false)
  const [notice, setNotice] = useState<Notice>(null)

  const loadAll = useCallback(async (keepNotice = false) => {
    setLoading(true)
    if (!keepNotice) setNotice(null)
    try {
      const [listResp, doctorResp] = await Promise.all([pluginApi.list(), pluginApi.doctor()])
      setPlugins(listResp.plugins || [])
      setDoctor(doctorResp)
      const nextSelected = selectedId || listResp.plugins?.[0]?.id || ''
      setSelectedId(nextSelected)
    } catch (err: unknown) {
      setNotice({ type: 'error', text: `加载插件失败: ${err instanceof Error ? err.message : String(err)}` })
    } finally {
      setLoading(false)
    }
  }, [selectedId])

  const loadInfo = useCallback(async (pluginId: string) => {
    if (!pluginId) return setSelected(null)
    try {
      const infoResp = await pluginApi.info(pluginId)
      setSelected(infoResp.plugin || null)
    } catch {
      setSelected(null)
    }
  }, [])

  useEffect(() => {
    void loadAll()
  }, [loadAll])

  useEffect(() => {
    void loadInfo(selectedId)
  }, [selectedId, loadInfo])

  const pluginCountText = useMemo(() => `${plugins.length} 个插件`, [plugins.length])

  const runAction = async (fn: () => Promise<PluginActionResp>, successText: string) => {
    if (busy) return
    setBusy(true)
    setNotice(null)
    try {
      const result = await fn()
      if (result.ok === false) throw new Error(result.message || '操作失败')
      await loadAll(true)
      if (selectedId) await loadInfo(selectedId)
      setNotice({ type: 'ok', text: result.message || successText })
    } catch (err: unknown) {
      setNotice({ type: 'error', text: err instanceof Error ? err.message : String(err) })
    } finally {
      setBusy(false)
    }
  }

  const onInstall = async () => {
    const path = installPath.trim()
    if (!path) return setNotice({ type: 'warn', text: '请输入插件路径（目录或压缩包）' })
    await runAction(() => pluginApi.install(path, installLink), '插件安装成功')
    setInstallPath('')
    setInstallLink(false)
  }

  const onEnable = async () => {
    if (!selectedId) return
    await runAction(() => pluginApi.enable(selectedId), `已启用插件: ${selectedId}`)
  }

  const onDisable = async () => {
    if (!selectedId) return
    await runAction(() => pluginApi.disable(selectedId), `已禁用插件: ${selectedId}`)
  }

  const onUninstall = async () => {
    if (!selectedId) return
    await runAction(() => pluginApi.uninstall(selectedId, false), `已卸载插件: ${selectedId}`)
    if (selectedId === selected?.id) {
      setSelected(null)
      setSelectedId('')
    }
  }

  return (
    <div className="mgmt-shell">
      <div className="mgmt-orb mgmt-orb-a" />
      <div className="mgmt-orb mgmt-orb-b" />
      <div className="mgmt-orb mgmt-orb-c" />

      <motion.div
        className="mgmt-stage"
        initial={{ opacity: 0, y: 18, scale: 0.96 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.5, type: 'spring', stiffness: 120, damping: 20 }}
      >
        <HoverEffectCard className="mgmt-card" maxXRotation={0.35} maxYRotation={0.35} hoverLight={false}>
          <div className="mgmt-hero">
            <div>
              <h2 className="mgmt-title">插件管理</h2>
              <p className="mgmt-subtitle">插件安装、启停、卸载、诊断一体化控制台</p>
            </div>
            <span className="mgmt-pill">{pluginCountText}</span>
          </div>

          <div className="mgmt-toolbar">
            <div className="mgmt-muted">保持与 MCP 页面一致的视觉与交互风格。</div>
            <div className="mgmt-actions">
              <button className="mgmt-btn" onClick={() => void loadAll()} disabled={busy}>刷新</button>
            </div>
          </div>

          <div className="mgmt-content">
            <section className="mgmt-panel">
              <div className="mgmt-block">
                <h3>插件列表</h3>
                {loading ? (
                  <div className="mgmt-muted">加载中...</div>
                ) : plugins.length === 0 ? (
                  <div className="mgmt-muted">尚未发现插件</div>
                ) : (
                  <div className="mgmt-list">
                    {plugins.map((plugin) => (
                      <button
                        key={plugin.id}
                        className={`mgmt-item ${selectedId === plugin.id ? 'active' : ''}`}
                        onClick={() => setSelectedId(plugin.id)}
                      >
                        <div className="mgmt-item-top">
                          <span>{plugin.id}</span>
                          <span className={`mgmt-pill ${plugin.enabled ? 'ok' : 'bad'}`}>{plugin.enabled ? '启用' : '禁用'}</span>
                          {plugin.reason && <span className="mgmt-pill bad">{plugin.reason}</span>}
                        </div>
                        <div className="mgmt-item-sub">
                          {plugin.version || 'no-version'} · {plugin.origin || 'unknown-origin'}
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </section>

            <aside className="mgmt-side">
              <div className="mgmt-block">
                <h3>插件详情</h3>
                {!selected ? (
                  <div className="mgmt-muted">请选择一个插件查看详情</div>
                ) : (
                  <div className="mgmt-info">
                    <InfoRow label="ID" value={selected.id} />
                    <InfoRow label="版本" value={selected.version || '-'} />
                    <InfoRow label="状态" value={selected.enabled ? '启用' : '禁用'} />
                    <InfoRow label="来源" value={selected.origin || '-'} />
                    <InfoRow label="入口" value={selected.entry || '-'} />
                    <InfoRow label="目录" value={selected.root || '-'} />
                    <InfoRow label="Manifest" value={selected.manifestPath || '-'} />
                    <InfoRow label="描述" value={selected.description || '-'} />
                  </div>
                )}

                <div className="mgmt-inline" style={{ marginTop: 10 }}>
                  <button className="mgmt-btn primary" disabled={!selectedId || busy} onClick={() => void onEnable()}>启用</button>
                  <button className="mgmt-btn" disabled={!selectedId || busy} onClick={() => void onDisable()}>禁用</button>
                  <button className="mgmt-btn" disabled={!selectedId || busy} onClick={() => void loadInfo(selectedId)}>刷新详情</button>
                  <button className="mgmt-btn danger" disabled={!selectedId || busy} onClick={() => void onUninstall()}>卸载</button>
                </div>
              </div>

              <div className="mgmt-block">
                <h3>安装插件</h3>
                <div className="mgmt-grid2">
                  <input
                    className="mgmt-input"
                    placeholder="插件路径（目录或压缩包）"
                    value={installPath}
                    onChange={(e) => setInstallPath(e.target.value)}
                  />
                  <label className="mgmt-muted" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <input type="checkbox" checked={installLink} onChange={(e) => setInstallLink(e.target.checked)} />
                    仅链接路径（不复制）
                  </label>
                </div>
                <div className="mgmt-inline" style={{ marginTop: 8 }}>
                  <button className="mgmt-btn primary" disabled={busy} onClick={() => void onInstall()}>
                    {busy ? '安装中...' : '安装'}
                  </button>
                </div>
              </div>

              <div className="mgmt-block">
                <h3>诊断</h3>
                {!doctor ? (
                  <div className="mgmt-muted">暂无诊断结果</div>
                ) : (
                  <div className="mgmt-info">
                    <InfoRow label="状态" value={doctor.ok ? '正常' : '异常'} />
                    <InfoRow label="插件目录" value={String(doctor.plugins?.length || 0)} />
                    <InfoRow label="问题数" value={String(doctor.issues?.length || 0)} />
                    {(doctor.issues || []).map((issue, i) => (
                      <div key={`${issue}-${i}`} className="mgmt-muted">- {issue}</div>
                    ))}
                  </div>
                )}
              </div>

              {notice && <div className={`mgmt-toast ${notice.type}`}>{notice.text}</div>}
            </aside>
          </div>
        </HoverEffectCard>
      </motion.div>
    </div>
  )
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="mgmt-info-row">
      <span>{label}</span>
      <span>{value}</span>
    </div>
  )
}

