import React, { createContext, useContext, useEffect, useRef, useState } from "react"
import { createPortal } from "react-dom"
import { useLocation } from "react-router-dom"

interface TooltipState {
  visible: boolean
  content: React.ReactNode
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
  showTooltip: (content: React.ReactNode, x: number, y: number, owner: string) => void
  hideTooltip: (owner: string) => void
  moveTooltip: (x: number, y: number, owner: string) => void
  visible: boolean
}

const TooltipContext = createContext<TooltipContextType | null>(null)
const TOOLTIP_OFFSET = 10
const TOOLTIP_TOP_OFFSET = 25
const SCREEN_MARGIN = 10

function TooltipPortal({ state }: { state: TooltipState }) {
  const tooltipRef = useRef<HTMLDivElement>(null)
  // place offscreen initially until we compute its position
  const [position, setPosition] = useState({ left: -9999, top: -9999 })

  useEffect(() => {
    if (!state.visible || !tooltipRef.current) {
      return
    }
    // prevent tooltip from going out of bounds. flip to the left side if we're going to go
    // off the screen on the right. etc.
    const tooltipRect = tooltipRef.current.getBoundingClientRect()
    const tooltipWidth = tooltipRect.width
    const tooltipHeight = tooltipRect.height

    let left = state.x + TOOLTIP_OFFSET
    let top = state.y - TOOLTIP_TOP_OFFSET

    const rightEdge = left + tooltipWidth
    if (rightEdge > window.innerWidth - SCREEN_MARGIN) {
      left = state.x - tooltipWidth - TOOLTIP_OFFSET

      if (left < SCREEN_MARGIN) {
        left = SCREEN_MARGIN
      }
    }

    if (left < SCREEN_MARGIN) {
      left = SCREEN_MARGIN
    }

    if (top < SCREEN_MARGIN) {
      top = SCREEN_MARGIN
    }

    const bottomEdge = top + tooltipHeight
    if (bottomEdge > window.innerHeight - SCREEN_MARGIN) {
      top = state.y - tooltipHeight - TOOLTIP_OFFSET

      if (top < SCREEN_MARGIN) {
        top = SCREEN_MARGIN
      }
    }

    setPosition({ left, top })
  }, [state.x, state.y, state.visible])

  if (!state.visible) {
    return null
  }

  return createPortal(
    <div
      ref={tooltipRef}
      className="cursor-tooltip"
      style={{
        position: "fixed",
        left: `${position.left}px`,
        top: `${position.top}px`,
        display: "block",
        pointerEvents: "none", // prevent tooltip from interfering with mouse events
        zIndex: 9999,
      }}
    >
      {typeof state.content === "string" ? (
        <div dangerouslySetInnerHTML={{ __html: state.content }} />
      ) : (
        state.content
      )}
    </div>,
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

  const showTooltip = (
    content: React.ReactNode,
    x: number,
    y: number,
    owner: string,
  ) => {
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
