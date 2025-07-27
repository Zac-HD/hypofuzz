import { interpolate } from "d3-interpolate"
import { MouseEvent, useEffect, useRef, useState } from "react"

interface ZoomState {
  x: number
  y: number
  scaleX: number
}

interface UseZoomOptions {
  minScale?: number
  maxScale?: number
  wheelSensitivity?: number
  containerRef: React.RefObject<HTMLElement | null>
}

interface UseZoomReturn {
  transform: ZoomState
  onMouseDown: (event: MouseEvent<HTMLElement>) => void
  onDoubleClick: (event: MouseEvent<HTMLElement>) => void
  resetZoom: () => void
  setTransform: (transform: ZoomState) => void
}

const defaultZoomState: ZoomState = { x: 0, y: 0, scaleX: 1 }

export function useZoom({
  minScale = 1,
  maxScale = 50,
  wheelSensitivity = 0.0013,
  containerRef,
}: UseZoomOptions): UseZoomReturn {
  const [transform, setTransformState] = useState<ZoomState>(defaultZoomState)
  const isDragging = useRef(false)
  const lastPointer = useRef({ x: 0, y: 0 })
  const animationRef = useRef<number | null>(null)
  const isZooming = useRef(false)
  const wheelEventCount = useRef(0)
  const wheelTimeoutRef = useRef<number | null>(null)

  const cancelAnimation = () => {
    if (animationRef.current) {
      cancelAnimationFrame(animationRef.current)
      animationRef.current = null
    }
  }

  const setTransform = (newTransform: ZoomState) => {
    cancelAnimation()
    const constrainedTransform = newTransform
    setTransformState(constrainedTransform)
  }

  const resetZoom = () => {
    cancelAnimation()

    const startTransform = transform
    const endTransform = defaultZoomState
    const duration = 500 // milliseconds
    const startTime = performance.now()

    const interpolateX = interpolate(startTransform.x, endTransform.x)
    const interpolateY = interpolate(startTransform.y, endTransform.y)
    const interpolateScaleX = interpolate(startTransform.scaleX, endTransform.scaleX)

    const animate = (currentTime: number) => {
      const elapsed = currentTime - startTime
      const progress = Math.min(elapsed / duration, 1)

      // ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3)

      const newTransform: ZoomState = {
        x: interpolateX(eased),
        y: interpolateY(eased),
        scaleX: interpolateScaleX(eased),
      }

      setTransformState(newTransform)

      if (progress < 1) {
        animationRef.current = requestAnimationFrame(animate)
      } else {
        animationRef.current = null
      }
    }

    animationRef.current = requestAnimationFrame(animate)
  }

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const handleWheel = (event: WheelEvent) => {
      cancelAnimation()

      const rect = container.getBoundingClientRect()
      const mouseX = event.clientX - rect.left

      // ignore horizontal swipes
      if (Math.abs(event.deltaX) > Math.abs(event.deltaY)) {
        return
      }

      const scaleFactor = 1 - event.deltaY * wheelSensitivity
      const newScale = Math.max(
        minScale,
        Math.min(maxScale, transform.scaleX * scaleFactor),
      )
      const wouldZoom = newScale !== transform.scaleX

      // Prevent page scrolling if we would zoom OR if we're in an active zoom session
      if (wouldZoom || isZooming.current) {
        event.preventDefault()
        event.stopPropagation()
      } else {
        // increment counter to indicate wheel activity
        wheelEventCount.current++
      }
      if (wouldZoom) {
        // Mark that we're in an active zoom session
        isZooming.current = true

        const scaleRatio = newScale / transform.scaleX
        const newX = mouseX - (mouseX - transform.x) * scaleRatio
        // horizontal-only zoom; keep y unchanged
        const newTransform = {
          x: newX,
          y: transform.y,
          scaleX: newScale,
        }
        const constrainedTransform = newTransform
        setTransformState(constrainedTransform)
      }

      // Reset wheel event counter and set timeout to detect when wheel events stop
      wheelEventCount.current = 0

      // Clear any existing timeout
      if (wheelTimeoutRef.current) {
        clearTimeout(wheelTimeoutRef.current)
      }

      // Set a timeout to check if wheel events have stopped
      wheelTimeoutRef.current = window.setTimeout(() => {
        // If wheel event counter is still 0, no new wheel events came in
        if (wheelEventCount.current === 0) {
          isZooming.current = false
        }
        wheelTimeoutRef.current = null
      }, 150)
    }

    container.addEventListener("wheel", handleWheel, { passive: false })

    return () => {
      container.removeEventListener("wheel", handleWheel)
    }
  }, [transform, minScale, maxScale, wheelSensitivity, cancelAnimation])

  const onMouseDown = (event: MouseEvent<HTMLElement>) => {
    if (event.button !== 0) return // Only accept left mouse button
    cancelAnimation()

    isDragging.current = true
    lastPointer.current = { x: event.clientX, y: event.clientY }

    const handleMouseMove = (e: globalThis.MouseEvent) => {
      if (!isDragging.current) return

      const deltaX = e.clientX - lastPointer.current.x
      const deltaY = e.clientY - lastPointer.current.y

      setTransformState(prev => {
        const newTransform = {
          x: prev.x + deltaX,
          y: prev.y + deltaY,
          scaleX: prev.scaleX,
        }
        return newTransform
      })

      lastPointer.current = { x: e.clientX, y: e.clientY }
    }

    const handleMouseUp = () => {
      isDragging.current = false
      document.removeEventListener("mousemove", handleMouseMove)
      document.removeEventListener("mouseup", handleMouseUp)
    }

    document.addEventListener("mousemove", handleMouseMove)
    document.addEventListener("mouseup", handleMouseUp)
  }

  const onDoubleClick = (event: MouseEvent<HTMLElement>) => {
    event.preventDefault()
    resetZoom()
  }

  useEffect(() => {
    return () => {
      cancelAnimation()
      if (wheelTimeoutRef.current) {
        clearTimeout(wheelTimeoutRef.current)
      }
    }
  }, [cancelAnimation])

  return {
    transform,
    onMouseDown,
    onDoubleClick,
    resetZoom,
    setTransform,
  }
}
