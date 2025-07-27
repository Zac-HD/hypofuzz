import { useEffect, useRef, useState } from "react"

interface RangeSliderProps {
  min: number
  max: number
  value: [number, number]
  onChange: (value: [number, number]) => void
  step?: number
}

export function RangeSlider({ min, max, value, onChange, step = 1 }: RangeSliderProps) {
  const [dragging, setDragging] = useState<"min" | "max" | null>(null)
  const sliderRef = useRef<HTMLDivElement>(null)
  console.assert(min <= max, `min: ${min} max: ${max}`)

  const [minValue, maxValue] = value
  const range = max - min

  const minPercent = range === 0 ? 0 : ((minValue - min) / range) * 100
  const maxPercent = range === 0 ? 100 : ((maxValue - min) / range) * 100

  // ensure that if both are overlapped on the very left (right) edge, the thumb
  // with room to move right (left) is on top
  const zIndexMin = minPercent < 50 ? 1 : 2
  const zIndexMax = maxPercent < 50 ? 2 : 1

  const getValueFromPosition = (clientX: number): number => {
    if (!sliderRef.current) return min

    const rect = sliderRef.current.getBoundingClientRect()
    const percent = Math.max(
      0,
      Math.min(100, ((clientX - rect.left) / rect.width) * 100),
    )
    const rawValue = min + (percent / 100) * range

    // Snap to step
    const steppedValue = Math.round(rawValue / step) * step
    return Math.max(min, Math.min(max, steppedValue))
  }

  const handleMouseDown = (thumb: "min" | "max") => (event: React.MouseEvent) => {
    event.preventDefault()
    setDragging(thumb)
  }

  const handleMouseMove = (event: MouseEvent) => {
    if (!dragging) return

    const newValue = getValueFromPosition(event.clientX)

    if (dragging === "min") {
      onChange([Math.min(newValue, maxValue), maxValue])
    } else {
      onChange([minValue, Math.max(newValue, minValue)])
    }
  }

  const handleMouseUp = () => {
    setDragging(null)
  }

  const handleTrackClick = (event: React.MouseEvent) => {
    if (dragging) return

    const newValue = getValueFromPosition(event.clientX)
    const minDistance = Math.abs(newValue - minValue)
    const maxDistance = Math.abs(newValue - maxValue)

    if (minDistance < maxDistance) {
      onChange([Math.min(newValue, maxValue), maxValue])
    } else {
      onChange([minValue, Math.max(newValue, minValue)])
    }
  }

  useEffect(() => {
    if (dragging) {
      document.addEventListener("mousemove", handleMouseMove)
      document.addEventListener("mouseup", handleMouseUp)
      return () => {
        document.removeEventListener("mousemove", handleMouseMove)
        document.removeEventListener("mouseup", handleMouseUp)
      }
    }
    return () => {}
  }, [dragging, handleMouseMove, handleMouseUp])

  return (
    <div className="range-slider">
      <div className="range-slider__container">
        <div ref={sliderRef} className="range-slider__track" onClick={handleTrackClick}>
          <div
            className="range-slider__range"
            style={{
              left: `${minPercent}%`,
              width: `${maxPercent - minPercent}%`,
            }}
          />
          <div
            className={`range-slider__thumb range-slider__thumb--min`}
            style={{
              left: `${minPercent}%`,
              zIndex: zIndexMin,
            }}
            onMouseDown={handleMouseDown("min")}
          />
          <div
            className={`range-slider__thumb range-slider__thumb--max`}
            style={{
              left: `${maxPercent}%`,
              zIndex: zIndexMax,
            }}
            onMouseDown={handleMouseDown("max")}
          />
        </div>
      </div>
    </div>
  )
}
