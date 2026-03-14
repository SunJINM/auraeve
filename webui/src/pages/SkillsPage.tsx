import { useCallback, useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { HoverEffectCard } from '../components/HoverEffectCard'
import { skillApi, type SkillActionResp, type SkillDoctorResp, type SkillRecord } from '../api/client'
import './ManagePages.css'

type Notice = { type: 'ok' | 'error' | 'warn'; text: string } | null

interface UploadSummary {
  installed: Array<Record<string, unknown>>
  skipped: Array<Record<string, unknown>>
  failed: Array<Record<string, unknown>>
}

export function SkillsPage() {
  const [skills, setSkills] = useState<SkillRecord[]>([])
  const [doctor, setDoctor] = useState<SkillDoctorResp | null>(null)
  const [selectedKey, setSelectedKey] = useState('')
  const [selected, setSelected] = useState<SkillRecord | null>(null)
  const [targetSkill, setTargetSkill] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [installId, setInstallId] = useState('')
  const [notice, setNotice] = useState<Notice>(null)
  const [syncAll, setSyncAll] = useState(true)
  const [syncDryRun, setSyncDryRun] = useState(false)
  const [hubSlug, setHubSlug] = useState('')
  const [hubVersion, setHubVersion] = useState('')
  const [hubForce, setHubForce] = useState(false)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploadForce, setUploadForce] = useState(false)
  const [uploadSummary, setUploadSummary] = useState<UploadSummary | null>(null)

  const loadAll = useCallback(async (keepNotice = false) => {
    setLoading(true)
    if (!keepNotice) setNotice(null)
    try {
      const [listResp, doctorResp] = await Promise.all([skillApi.list(), skillApi.doctor()])
      const items = listResp.skills || []
      setSkills(items)
      setDoctor(doctorResp)
      const nextSelected = selectedKey || items?.[0]?.skillKey || items?.[0]?.name || ''
      setSelectedKey(nextSelected)
      if (!targetSkill && nextSelected) setTargetSkill(nextSelected)
    } catch (err: unknown) {
      setNotice({ type: 'error', text: `加载技能失败: ${err instanceof Error ? err.message : String(err)}` })
    } finally {
      setLoading(false)
    }
  }, [selectedKey, targetSkill])

  const loadInfo = useCallback(async (id: string) => {
    if (!id) return setSelected(null)
    try {
      const info = await skillApi.info(id)
      setSelected(info.skill || null)
    } catch {
      setSelected(null)
    }
  }, [])

  useEffect(() => {
    void loadAll()
  }, [loadAll])

  useEffect(() => {
    void loadInfo(selectedKey)
  }, [selectedKey, loadInfo])

  const countText = useMemo(() => `${skills.length} 个技能`, [skills.length])

  const runAction = async (fn: () => Promise<SkillActionResp>, successText: string) => {
    if (busy) return
    setBusy(true)
    setNotice(null)
    try {
      const result = await fn()
      if (result.ok === false) throw new Error(result.stderr || result.message || result.stdout || '操作失败')
      await loadAll(true)
      if (selectedKey) await loadInfo(selectedKey)
      setNotice({ type: 'ok', text: result.message || successText })
      return result
    } catch (err: unknown) {
      setNotice({ type: 'error', text: err instanceof Error ? err.message : String(err) })
      return null
    } finally {
      setBusy(false)
    }
  }

  const onInstall = async () => {
    const skillId = targetSkill.trim() || selectedKey.trim()
    if (!skillId) return setNotice({ type: 'warn', text: '请输入目标技能 ID/Key。' })
    await runAction(() => skillApi.install(skillId, installId.trim() || undefined), `已安装技能依赖: ${skillId}`)
  }

  const onEnable = async () => {
    if (!selected) return
    await runAction(() => skillApi.enable(selected.skillKey || selected.name), `已启用技能: ${selected.name}`)
  }

  const onDisable = async () => {
    if (!selected) return
    await runAction(() => skillApi.disable(selected.skillKey || selected.name), `已禁用技能: ${selected.name}`)
  }

  const onSync = async () => {
    await runAction(() => skillApi.sync(syncAll, syncDryRun), '技能同步完成')
  }

  const onInstallFromHub = async () => {
    const slug = hubSlug.trim()
    if (!slug) return setNotice({ type: 'warn', text: '请输入技能 slug、Hub URL 或安装命令。' })
    await runAction(() => skillApi.installFromHub(slug, hubVersion.trim() || undefined, hubForce), `已从 Hub 安装技能: ${slug}`)
  }

  const onUploadAndInstall = async () => {
    if (!uploadFile) {
      setNotice({ type: 'warn', text: '请先选择压缩包文件。' })
      return
    }
    if (busy) return
    setBusy(true)
    setNotice(null)
    try {
      const upload = await skillApi.uploadArchive(uploadFile)
      if (!upload.ok || !upload.uploadId) throw new Error(upload.message || '上传失败')
      const installed = await skillApi.installFromUpload(upload.uploadId, uploadForce)
      if (installed.ok === false) throw new Error(installed.message || installed.stderr || '安装失败')
      await loadAll(true)
      if (selectedKey) await loadInfo(selectedKey)
      setUploadSummary({
        installed: installed.installed || [],
        skipped: installed.skipped || [],
        failed: installed.failed || [],
      })
      setNotice({ type: 'ok', text: installed.message || `已安装上传压缩包: ${uploadFile.name}` })
    } catch (err: unknown) {
      setNotice({ type: 'error', text: err instanceof Error ? err.message : String(err) })
    } finally {
      setBusy(false)
    }
  }

  const currentInstallOptions = selected?.install || []

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
              <h2 className="mgmt-title">技能管理</h2>
              <p className="mgmt-subtitle">技能启停、依赖安装、同步、Hub 安装（ClawHub/SkillHub）与本地压缩包安装。</p>
            </div>
            <span className="mgmt-pill">{countText}</span>
          </div>

          <div className="mgmt-toolbar">
            <div className="mgmt-muted">统一技能管理面板。</div>
            <div className="mgmt-actions">
              <button className="mgmt-btn" onClick={() => void loadAll()} disabled={busy}>刷新</button>
            </div>
          </div>

          <div className="mgmt-content">
            <section className="mgmt-panel">
              <div className="mgmt-block">
                <h3>技能列表</h3>
                {loading ? (
                  <div className="mgmt-muted">加载中...</div>
                ) : skills.length === 0 ? (
                  <div className="mgmt-muted">未发现技能。</div>
                ) : (
                  <div className="mgmt-list">
                    {skills.map((skill) => {
                      const id = skill.skillKey || skill.name
                      return (
                        <button
                          key={id}
                          className={`mgmt-item ${selectedKey === id ? 'active' : ''}`}
                          onClick={() => {
                            setSelectedKey(id)
                            setTargetSkill(id)
                          }}
                        >
                          <div className="mgmt-item-top">
                            <span>{skill.name}</span>
                            <span className={`mgmt-pill ${skill.eligible ? 'ok' : 'bad'}`}>{skill.eligible ? '可用' : '不可用'}</span>
                            {skill.enabled === false && <span className="mgmt-pill bad">已禁用</span>}
                          </div>
                          <div className="mgmt-item-sub">{skill.source || 'unknown-source'} | {skill.skillKey}</div>
                        </button>
                      )
                    })}
                  </div>
                )}
              </div>
            </section>

            <aside className="mgmt-side">
              <div className="mgmt-block">
                <h3>技能详情</h3>
                {!selected ? (
                  <div className="mgmt-muted">请选择技能查看详情。</div>
                ) : (
                  <div className="mgmt-info">
                    <InfoRow label="名称" value={selected.name} />
                    <InfoRow label="Key" value={selected.skillKey} />
                    <InfoRow label="状态" value={selected.eligible ? '可用' : '不可用'} />
                    <InfoRow label="来源" value={selected.source || '-'} />
                    <InfoRow label="路径" value={selected.skillFile || '-'} />
                    <InfoRow label="描述" value={selected.description || '-'} />
                    <InfoRow label="缺失 bins" value={(selected.missing?.bins || []).join(', ') || '-'} />
                    <InfoRow label="缺失 env" value={(selected.missing?.env || []).join(', ') || '-'} />
                  </div>
                )}

                <div className="mgmt-inline" style={{ marginTop: 10 }}>
                  <button className="mgmt-btn primary" disabled={!selected || busy} onClick={() => void onEnable()}>启用</button>
                  <button className="mgmt-btn" disabled={!selected || busy} onClick={() => void onDisable()}>禁用</button>
                  <button className="mgmt-btn" disabled={!selectedKey || busy} onClick={() => void loadInfo(selectedKey)}>刷新详情</button>
                  <button className="mgmt-btn primary" disabled={busy} onClick={() => void onSync()}>同步</button>
                </div>
              </div>

              <div className="mgmt-block">
                <h3>安装依赖</h3>
                <div className="mgmt-grid2">
                  <input
                    className="mgmt-input"
                    placeholder="目标技能 ID/Key"
                    value={targetSkill}
                    onChange={(e) => setTargetSkill(e.target.value)}
                  />
                  <select className="mgmt-select" value={installId} onChange={(e) => setInstallId(e.target.value)}>
                    <option value="">自动选择安装器</option>
                    {currentInstallOptions.map((opt) => (
                      <option key={opt.id} value={opt.id}>{opt.label} ({opt.kind})</option>
                    ))}
                  </select>
                </div>
                <div className="mgmt-inline" style={{ marginTop: 8 }}>
                  <label className="mgmt-muted"><input type="checkbox" checked={syncAll} onChange={(e) => setSyncAll(e.target.checked)} /> sync --all</label>
                  <label className="mgmt-muted"><input type="checkbox" checked={syncDryRun} onChange={(e) => setSyncDryRun(e.target.checked)} /> sync --dry-run</label>
                  <button className="mgmt-btn primary" disabled={busy} onClick={() => void onInstall()}>{busy ? '执行中...' : '安装依赖'}</button>
                </div>
              </div>

              <div className="mgmt-block">
                <h3>从 Hub 安装</h3>
                <div className="mgmt-grid2">
                  <input
                    className="mgmt-input"
                    placeholder="slug / Hub URL / 命令（例：skillhub install xxx）"
                    value={hubSlug}
                    onChange={(e) => setHubSlug(e.target.value)}
                  />
                  <input
                    className="mgmt-input"
                    placeholder="版本（可选）"
                    value={hubVersion}
                    onChange={(e) => setHubVersion(e.target.value)}
                  />
                </div>
                <div className="mgmt-inline" style={{ marginTop: 8 }}>
                  <label className="mgmt-muted"><input type="checkbox" checked={hubForce} onChange={(e) => setHubForce(e.target.checked)} /> 强制覆盖</label>
                  <button className="mgmt-btn primary" disabled={busy} onClick={() => void onInstallFromHub()}>{busy ? '执行中...' : '安装 Hub 技能'}</button>
                </div>
              </div>

              <div className="mgmt-block">
                <h3>本地压缩包安装</h3>
                <div className="mgmt-grid2">
                  <input
                    className="mgmt-input"
                    type="file"
                    accept=".zip,.tar.gz,.tgz"
                    onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                  />
                  <div className="mgmt-muted">{uploadFile ? uploadFile.name : '未选择文件'}</div>
                </div>
                <div className="mgmt-inline" style={{ marginTop: 8 }}>
                  <label className="mgmt-muted"><input type="checkbox" checked={uploadForce} onChange={(e) => setUploadForce(e.target.checked)} /> 强制覆盖</label>
                  <button className="mgmt-btn primary" disabled={busy || !uploadFile} onClick={() => void onUploadAndInstall()}>
                    {busy ? '执行中...' : '上传并安装'}
                  </button>
                </div>
                {uploadSummary && (
                  <div className="mgmt-info" style={{ marginTop: 8 }}>
                    <InfoRow label="安装成功" value={String(uploadSummary.installed.length)} />
                    <InfoRow label="已跳过" value={String(uploadSummary.skipped.length)} />
                    <InfoRow label="安装失败" value={String(uploadSummary.failed.length)} />
                  </div>
                )}
              </div>

              <div className="mgmt-block">
                <h3>诊断</h3>
                {!doctor ? (
                  <div className="mgmt-muted">暂无诊断结果。</div>
                ) : (
                  <div className="mgmt-info">
                    <InfoRow label="状态" value={doctor.ok ? '正常' : '异常'} />
                    <InfoRow label="发现技能" value={String(doctor.skills?.length || 0)} />
                    <InfoRow label="问题数" value={String(doctor.issues?.length || 0)} />
                    {(doctor.issues || []).map((issue, i) => (
                      <div key={`${issue.code || 'issue'}-${i}`} className="mgmt-muted">- {issue.code || 'issue'}: {issue.message || 'unknown'}</div>
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
