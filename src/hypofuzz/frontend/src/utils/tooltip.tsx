import React, { createContext, useContext, useEffect, useState } from "react"
import { createPortal } from "react-dom"
import { useLocation } from "react-router-dom"

interface TooltipState {
  visible: boolean
  content: string
  x: number
  y: number
  // the concept of a "tooltip owner" simplifies investigation if anything goes wrong. For instance,
  // I got into an infinite render loop when multiple components used tooltips. This ended up being
  // because of an over-aggressive useEffect for cleanup, but I at first thought it was due to conflicting
  // components.
  //
  // And also the concept of an owner probably genuinely removes a class of bugs - but that's not why I
  // added it initially.
  owner: string | null
}

interface TooltipContextType {
  showTooltip: (content: string, x: number, y: number, owner: string) => void
  hideTooltip: (owner: string) => void
  moveTooltip: (x: number, y: number, owner: string) => void
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
  const location = useLocation()
  const [tooltipState, setTooltipState] = useState<TooltipState>({
    visible: false,
    content: "",
    x: 0,
    y: 0,
    owner: null,
  })

  // Navigation avoids firing onmouseleave events, leaving dangling tooltips.
  // Hide any tooltips when navigating to a new page.
  useEffect(() => {
    setTooltipState(prev => ({
      ...prev,
      visible: false,
      owner: null,
    }))
  }, [location.pathname])

  const showTooltip = (content: string, x: number, y: number, owner: string) => {
    setTooltipState({
      visible: true,
      content,
      x,
      y,
      owner,
    })
  }

  const hideTooltip = (owner: string) => {
    setTooltipState(prev => {
      if (prev.owner === owner) {
        return {
          ...prev,
          visible: false,
          owner: null,
        }
      }
      return prev
    })
  }

  const moveTooltip = (x: number, y: number, owner: string) => {
    setTooltipState(prev => {
      if (prev.visible && prev.owner === owner && (prev.x !== x || prev.y !== y)) {
        return {
          ...prev,
          x,
          y,
        }
      }
      return prev
    })
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
