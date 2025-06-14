import React, {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useRef,
  useState,
} from "react"

import { Notification } from "../components/Notification"

interface NotificationData {
  id: number
  message: ReactNode
  duration: number | null
}

interface NotificationContextType {
  addNotification: (message: ReactNode, duration: number | null) => number
  updateNotification: (id: number, message: ReactNode, duration: number | null) => void
  dismissNotification: (id: number) => void
}

const NotificationContext = createContext<NotificationContextType | null>(null)

interface NotificationProviderProps {
  children: React.ReactNode
}

export function NotificationProvider({ children }: NotificationProviderProps) {
  const [notifications, setNotifications] = useState<NotificationData[]>([])
  const timers = useRef<Map<number, number>>(new Map())
  const idCounter = useRef(0)

  const dismissNotification = useCallback((id: number) => {
    clearTimeout(timers.current.get(id)!)
    timers.current.delete(id)

    setNotifications(prev => prev.filter(n => n.id !== id))
  }, [])

  const addNotification = useCallback(
    (message: ReactNode, duration: number | null) => {
      const id = ++idCounter.current
      const notification: NotificationData = { id, message, duration }

      setNotifications(prev => [...prev, notification])

      if (duration !== null) {
        const timer = setTimeout(() => {
          dismissNotification(id)
        }, duration)
        timers.current.set(id, timer)
      }

      return id
    },
    [dismissNotification],
  )

  const updateNotification = useCallback(
    (id: number, message: ReactNode, duration: number | null) => {
      setNotifications(prev =>
        prev.map(notification =>
          notification.id === id
            ? { ...notification, message, duration }
            : notification,
        ),
      )

      if (duration !== null) {
        clearTimeout(timers.current.get(id)!)
        const timer = setTimeout(() => {
          dismissNotification(id)
        }, duration)
        timers.current.set(id, timer)
      }
    },
    [dismissNotification],
  )

  return (
    <NotificationContext.Provider
      value={{ addNotification, updateNotification, dismissNotification }}
    >
      {children}
      <div className="notifications">
        {notifications.map((notification, index) => (
          <div
            key={notification.id}
            className="notification-wrapper"
            style={{ top: `${20 + index * 80}px` }}
          >
            <Notification
              message={notification.message}
              isVisible={true}
              onDismiss={() => dismissNotification(notification.id)}
            />
          </div>
        ))}
      </div>
    </NotificationContext.Provider>
  )
}

export function useNotification() {
  const context = useContext(NotificationContext)
  if (!context) {
    throw new Error("useNotification must be used within a NotificationProvider")
  }
  return context
}
