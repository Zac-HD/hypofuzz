import { Set } from "immutable"
import { useIsMobile } from "src/hooks/useIsMobile"

interface Option<T> {
  value: T
  content: React.ReactNode
  mobileContent?: React.ReactNode
}

interface Props<T> {
  value: T
  onChange: (value: T) => void
  options: Option<T>[]
  disabled?: boolean
}

export function Toggle<T>({ value, onChange, options, disabled = false }: Props<T>) {
  const isMobile = useIsMobile()
  // option values must be unique
  console.assert(Set(options.map(o => o.value)).size === options.length)

  return (
    <div className={`toggle ${disabled ? "toggle--disabled" : ""}`}>
      {options.map(option => (
        <button
          key={String(option.value)}
          className={`toggle__button${value === option.value ? " toggle__button--active" : ""} ${disabled ? "toggle__button--disabled" : ""}`}
          onClick={() => {
            if (disabled) {
              return
            }
            if (options.length == 2 && value === option.value) {
              const otherValue = options.find(o => o.value !== option.value)!.value
              onChange(otherValue)
            } else {
              onChange(option.value)
            }
          }}
        >
          {isMobile ? (option.mobileContent ?? option.content) : option.content}
        </button>
      ))}
    </div>
  )
}
