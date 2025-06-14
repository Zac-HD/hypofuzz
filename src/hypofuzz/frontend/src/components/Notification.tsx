import { faXmark } from "@fortawesome/free-solid-svg-icons"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { ReactNode, useEffect, useState } from "react"

interface NotificationProps {
  message: string | ReactNode
  onDismiss: () => void
  isVisible: boolean
}

export function Notification({ message, onDismiss, isVisible }: NotificationProps) {
  const [shouldRender, setShouldRender] = useState(isVisible)

  useEffect(() => {
    if (isVisible) {
      setShouldRender(true)
      return
    } else {
      // Delay unmounting to allow exit animation
      const timer = setTimeout(() => {
        setShouldRender(false)
      }, 300)

      return () => clearTimeout(timer)
    }
  }, [isVisible])

  if (!shouldRender) {
    return null
  }

  return (
    <div
      className={`notification ${isVisible ? "notification--visible" : "notification--hidden"}`}
      onClick={onDismiss}
    >
      <div className="notification__content">{message}</div>
      <button
        className="notification__close"
        onClick={e => {
          e.stopPropagation()
          onDismiss()
        }}
        aria-label="Close notification"
      >
        <FontAwesomeIcon icon={faXmark} />
      </button>
    </div>
  )
}
