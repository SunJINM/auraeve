import { Card } from '@heroui/card'
import type { CardProps } from '@heroui/card'
import clsx from 'clsx'
import React from 'react'

export interface HoverEffectCardProps extends CardProps {
  children: React.ReactNode
  maxXRotation?: number
  maxYRotation?: number
  hoverLight?: boolean
}

export function HoverEffectCard({
  children,
  maxXRotation = 5,
  maxYRotation = 5,
  hoverLight = true,
  className,
  style,
  ...props
}: HoverEffectCardProps) {
  const cardRef = React.useRef<HTMLDivElement | null>(null)
  const [isShowLight, setIsShowLight] = React.useState(false)
  const [pos, setPos] = React.useState({ left: 0, top: 0 })
  const resetTransform = React.useCallback(() => {
    if (!cardRef.current) return
    cardRef.current.style.transform =
      'perspective(1200px) rotateX(0deg) rotateY(0deg) translateZ(0)'
  }, [])

  return (
    <Card
      {...props}
      ref={cardRef}
      className={clsx('relative overflow-hidden bg-opacity-50 backdrop-blur-lg', className)}
      style={{
        willChange: 'transform',
        transform: 'perspective(1200px) rotateX(0deg) rotateY(0deg) translateZ(0)',
        ...style,
      }}
      onMouseEnter={() => {
        if (cardRef.current) cardRef.current.style.transition = 'transform 0.16s ease-out'
      }}
      onMouseLeave={() => {
        setIsShowLight(false)
        if (cardRef.current) {
          cardRef.current.style.transition = 'transform 0.28s ease-out'
          resetTransform()
        }
      }}
      onMouseMove={(e: React.MouseEvent<HTMLDivElement>) => {
        if (!cardRef.current) return
        const target = e.target as HTMLElement
        if (target.closest('button, input, textarea, select, a, [role="button"]')) {
          cardRef.current.style.transition = 'transform 0.2s ease-out'
          resetTransform()
          setIsShowLight(false)
          return
        }
        setIsShowLight(hoverLight)
        const { x, y, width, height } = cardRef.current.getBoundingClientRect()
        const offsetX = e.clientX - x
        const offsetY = e.clientY - y
        setPos({ left: offsetX - 75, top: offsetY - 75 })
        cardRef.current.style.transition = 'transform 0.08s linear'
        const halfW = Math.max(width / 2, 1)
        const halfH = Math.max(height / 2, 1)
        const normalizedX = (offsetX - halfW) / halfW
        const normalizedY = (offsetY - halfH) / halfH
        const rotateX = -normalizedY * maxXRotation
        const rotateY = normalizedX * maxYRotation
        cardRef.current.style.transform =
          `perspective(1200px) rotateX(${rotateX.toFixed(3)}deg) rotateY(${rotateY.toFixed(3)}deg) translateZ(0)`
      }}
    >
      {hoverLight && (
        <div
          className={clsx(
            isShowLight ? 'opacity-100' : 'opacity-0',
            'absolute rounded-full blur-[100px] filter transition-opacity duration-300 pointer-events-none',
            'bg-gradient-to-r from-primary-400 to-secondary-400 w-[150px] h-[150px]',
          )}
          style={{ left: pos.left, top: pos.top }}
        />
      )}
      {children}
    </Card>
  )
}
