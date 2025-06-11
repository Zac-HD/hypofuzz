import React, { createContext, useContext, useEffect, useRef, useState } from "react"
import { createPortal } from "react-dom"

interface TooltipState {
  visible: boolean
  content: string
  x: number
  y: number
}

interface TooltipContextType {
  showTooltip: (content: string, x: number, y: number) => void
  hideTooltip: () => void
  moveTooltip: (x: number, y: number) => void
  visible: boolean
}

const TooltipContext = createContext<TooltipContextType | null>(null)

function TooltipPortal({ state }: { state: TooltipState }) {
  if (!state.visible) return null

  return createPortal(
    <div
      className="cursor-tooltip"
      style={{
        position: "fixed",
        left: `${state.x + 10}px`,
        top: `${state.y - 28}px`,
        display: "block",
        pointerEvents: "none", // prevent tooltip from interfering with mouse events
        zIndex: 9999,
      }}
      dangerouslySetInnerHTML={{ __html: state.content }}
    />,
    document.body,
  )
}

export function TooltipProvider({ children }: { children: React.ReactNode }) {
  const [tooltipState, setTooltipState] = useState<TooltipState>({
    visible: false,
    content: "",
    x: 0,
    y: 0,
  })

  const showTooltip = (content: string, x: number, y: number) => {
    setTooltipState({
      visible: true,
      content,
      x,
      y,
    })
  }

  const hideTooltip = () => {
    setTooltipState(prev => ({
      ...prev,
      visible: false,
    }))
  }

  const moveTooltip = (x: number, y: number) => {
    if (tooltipState.visible) {
      setTooltipState(prev => ({
        ...prev,
        x,
        y,
      }))
    }
  }

  const contextValue: TooltipContextType = {
    showTooltip,
    hideTooltip,
    moveTooltip,
    visible: tooltipState.visible,
  }

  return (
    <TooltipContext.Provider value={contextValue}>
      {children}
      <TooltipPortal state={tooltipState} />
    </TooltipContext.Provider>
  )
}

export function useTooltip() {
  const context = useContext(TooltipContext)
  if (!context) {
    throw new Error("useTooltip must be used within a TooltipProvider")
  }
  return context
}
