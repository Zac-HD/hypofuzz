import { useIsMobile } from "../hooks/useIsMobile"

interface Option<T> {
  value: T
  content: React.ReactNode
  mobileContent?: React.ReactNode
}

interface Props<T> {
  value: T
  onChange: (value: T) => void
  options: Option<T>[]
}

export function Toggle<T>({ value, onChange, options }: Props<T>) {
  const isMobile = useIsMobile()

  return (
    <div className="scale-toggle">
      {options.map(option => (
        <button
          key={String(option.value)}
          className={`scale-toggle__button${value === option.value ? " scale-toggle__button--active" : ""}`}
          onClick={() => {
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
