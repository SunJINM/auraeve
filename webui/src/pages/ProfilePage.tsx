import { useState } from 'react'
import { motion } from 'framer-motion'
import { HoverEffectCard } from '../components/HoverEffectCard'
import { profileApi, type ProfileImportResp } from '../api/client'
import './ManagePages.css'

type Notice = { type: 'ok' | 'error' | 'warn'; text: string } | null

export function ProfilePage() {
  const [busy, setBusy] = useState(false)
  const [archiveFile, setArchiveFile] = useState<File | null>(null)
  const [forceImport, setForceImport] = useState(false)
  const [notice, setNotice] = useState<Notice>(null)
  const [lastResult, setLastResult] = useState<ProfileImportResp | null>(null)

  const onExport = async () => {
    if (busy) return
    setBusy(true)
    setNotice(null)
    try {
      await profileApi.exportArchive()
      setNotice({ type: 'ok', text: '资料包已导出并开始下载。' })
    } catch (err: unknown) {
      setNotice({ type: 'error', text: err instanceof Error ? err.message : String(err) })
    } finally {
      setBusy(false)
    }
  }

  const onImport = async () => {
    if (busy) return
    if (!archiveFile) {
      setNotice({ type: 'warn', text: '请先选择 .auraeve 资料包。' })
      return
    }
    setBusy(true)
    setNotice(null)
    try {
      const payload = await profileApi.importArchive(archiveFile, forceImport)
      setLastResult(payload)
      setNotice({ type: 'ok', text: '资料包导入成功。建议重启运行时后继续使用。' })
    } catch (err: unknown) {
      setNotice({ type: 'error', text: err instanceof Error ? err.message : String(err) })
    } finally {
      setBusy(false)
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
              <h2 className="mgmt-title">资料迁移</h2>
              <p className="mgmt-subtitle">导出和导入个人资料包（配置、记忆、技能、插件和状态）。</p>
            </div>
            <span className="mgmt-pill">.auraeve</span>
          </div>

          <div className="mgmt-content">
            <section className="mgmt-panel">
              <div className="mgmt-block">
                <h3>导出资料包</h3>
                <div className="mgmt-muted">
                  导出当前状态目录为一个 .auraeve 文件，可用于迁移到其他机器。
                </div>
                <div className="mgmt-inline" style={{ marginTop: 12 }}>
                  <button className="mgmt-btn primary" disabled={busy} onClick={() => void onExport()}>
                    {busy ? '处理中...' : '导出并下载'}
                  </button>
                </div>
              </div>
            </section>

            <aside className="mgmt-side">
              <div className="mgmt-block">
                <h3>导入资料包</h3>
                <div className="mgmt-grid2">
                  <input
                    className="mgmt-input"
                    type="file"
                    accept=".auraeve,.zip,application/octet-stream"
                    onChange={(e) => setArchiveFile(e.target.files?.[0] || null)}
                  />
                  <div className="mgmt-muted">{archiveFile ? archiveFile.name : '未选择文件'}</div>
                </div>
                <div className="mgmt-inline" style={{ marginTop: 10 }}>
                  <label className="mgmt-muted">
                    <input
                      type="checkbox"
                      checked={forceImport}
                      onChange={(e) => setForceImport(e.target.checked)}
                    />{' '}
                    强制全量覆盖（会替换本地现有资料）
                  </label>
                </div>
                <div className="mgmt-inline" style={{ marginTop: 10 }}>
                  <button className="mgmt-btn danger" disabled={busy || !archiveFile} onClick={() => void onImport()}>
                    {busy ? '处理中...' : '导入资料包'}
                  </button>
                </div>
              </div>

              {lastResult && (
                <div className="mgmt-block">
                  <h3>最近导入结果</h3>
                  <div className="mgmt-info">
                    <InfoRow label="状态目录" value={lastResult.stateDir} />
                    <InfoRow label="配置文件" value={lastResult.configPath} />
                    <InfoRow label="状态备份" value={lastResult.stateBackup || '-'} />
                    <InfoRow label="配置备份" value={lastResult.configBackup || '-'} />
                  </div>
                </div>
              )}

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
