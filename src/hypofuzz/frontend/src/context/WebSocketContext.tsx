import React, { createContext, useContext, useEffect, useState, useCallback } from 'react'
import { Report, Metadata } from '../types/dashboard'

export interface WebSocketRequest {
  page: 'overview' | 'test';
  node_id?: string;
}

interface WebSocketContextType {
  reports: Record<string, Report[]>;
  metadata: Record<string, Metadata>;
  socket: WebSocket | null;
}

interface WebSocketEvent {
  type: 'save' | 'initial' | 'metadata';
  data: unknown;
  reports?: unknown
  metadata?: unknown
}

const WebSocketContext = createContext<WebSocketContextType | null>(null)

interface WebSocketProviderProps {
  children: React.ReactNode;
  nodeId?: string;
}

export function WebSocketProvider({ children, nodeId }: WebSocketProviderProps) {
  const [socket, setSocket] = useState<WebSocket | null>(null)
  const [reports, setReports] = useState<Record<string, Report[]> | null>(null)
  const [metadata, setMetadata] = useState<Record<string, Metadata> | null>(null)

  useEffect(() => {
    const url = new URL(`ws${window.location.protocol === 'https:' ? 's' : ''}://${window.location.host}/ws`);
    if (nodeId) {
      url.searchParams.set('node_id', nodeId);
    }

    const ws = new WebSocket(url);

    ws.onmessage = (event) => {
      const message = JSON.parse(event.data) as WebSocketEvent;

      switch (message.type) {
        case 'initial':
          setReports(message.reports as Record<string, Report[]>);
          setMetadata(message.metadata as Record<string, Metadata>);
          break;
        case 'save':
          setReports(currentReports => {
            const newReports = { ...(currentReports ?? {}) };
            const report = message.data as Report;
            const nodeid = report.nodeid;
            if (!newReports[nodeid]) {
              newReports[nodeid] = [];
            }
            newReports[nodeid] = [...newReports[nodeid], report];
            newReports[nodeid].sort((a, b) => a.elapsed_time - b.elapsed_time);
            return newReports;
          });
          break;
        case 'metadata':
          setMetadata(currentMetadata => {
            const newMetadata = { ...(currentMetadata ?? {}) };
            const metadata = message.data as Metadata;
            newMetadata[metadata.nodeid] = metadata;
            return newMetadata;
          });
          break;
      }
    }

    setSocket(ws)

    return () => {
      ws.close()
    }
  }, [nodeId])

  if (reports === null || metadata === null) {
    return null // Don't render anything until we have initial data
  }

  return (
    <WebSocketContext.Provider value={{ reports, metadata, socket }}>
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
