import React, { createContext, useContext, useEffect, useState, useCallback } from 'react'
import { TestRecord } from '../types/dashboard'

interface WebSocketContextType {
  data: Record<string, TestRecord[]>;
  requestNodeState: (nodeId: string) => void;
}

const WebSocketContext = createContext<WebSocketContextType | null>(null)

export function WebSocketProvider({ children }: { children: React.ReactNode }) {
  const [socket, setSocket] = useState<WebSocket | null>(null)
  const [data, setData] = useState<Record<string, TestRecord[]> | null>(null)

  useEffect(() => {
    fetch('/api/tests/')
      .then(response => response.json())
      .then(initialData => {
        setData(initialData)
      })
      .catch(error => {
        console.error('Failed to fetch initial state:', error)
      })

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const websocketURL = `${protocol}//${host}/ws`;

    const ws = new WebSocket(websocketURL)

    ws.onmessage = (event) => {
      setData(JSON.parse(event.data))
    }

    setSocket(ws)

    return () => {
      ws.close()
    }
  }, [])

  const requestNodeState = useCallback((nodeId: string) => {
    fetch(`/api/tests/${nodeId}`)
      .then(response => response.json())
      .then(nodeData => {
        setData(current => current ? {
          ...current,
          [nodeId]: nodeData
        } : null)
      })
      .catch(error => {
        console.error('Failed to fetch node state:', error)
      })
  }, [])

  if (data === null) {
    return null // Don't render anything until we have initial data
  }

  return (
    <WebSocketContext.Provider value={{ data, requestNodeState }}>
      {children}
    </WebSocketContext.Provider>
  )
}

export function useWebSocket() {
  const context = useContext(WebSocketContext)
  if (!context) {
    throw new Error('useWebSocket must be used within a WebSocketProvider')
  }
  return context
}
