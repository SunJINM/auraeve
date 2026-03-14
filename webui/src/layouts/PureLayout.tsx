export function PureLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative flex flex-col h-screen" style={{ background: 'var(--bg-gradient)' }}>
      {/* 背景光球 */}
      <div className="orb w-[34rem] h-[34rem] -top-44 -left-40" style={{ background: '#f9a8c9', opacity: 0.5 }} />
      <div className="orb w-[26rem] h-[26rem] top-1/2 -translate-y-1/2 -right-24" style={{ background: '#c084fc', opacity: 0.3 }} />
      <div className="orb w-[26rem] h-[26rem] -bottom-24 left-1/2 -translate-x-1/2" style={{ background: '#fb7185', opacity: 0.38 }} />

      <main className="relative z-10 flex-grow w-full flex flex-col justify-center items-center">
        {children}
      </main>
    </div>
  )
}
