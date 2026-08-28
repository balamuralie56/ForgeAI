import { useEffect, useRef, useState } from "react";
import { WS_URL } from "./api";
import type { ForgeEvent } from "./types";

export type ConnectionState = "connecting" | "open" | "closed";

/**
 * Subscribes to the ForgeAI event WebSocket and keeps a rolling log of every
 * event received, plus the most recent event of each type (useful for
 * reading the latest stage/finding state without re-scanning the whole log).
 */
export function useEventStream(maxLogSize = 500) {
  const [connectionState, setConnectionState] = useState<ConnectionState>("connecting");
  const [log, setLog] = useState<ForgeEvent[]>([]);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let cancelled = false;
    let retryTimer: number | undefined;

    function connect() {
      if (cancelled) return;
      setConnectionState("connecting");
      const socket = new WebSocket(WS_URL);
      socketRef.current = socket;

      socket.onopen = () => setConnectionState("open");

      socket.onmessage = (event: MessageEvent<string>) => {
        try {
          const parsed = JSON.parse(event.data) as ForgeEvent;
          setLog((prev) => {
            const next = [...prev, parsed];
            return next.length > maxLogSize ? next.slice(next.length - maxLogSize) : next;
          });
        } catch {
          // Ignore malformed frames rather than crashing the stream.
        }
      };

      socket.onclose = () => {
        setConnectionState("closed");
        if (!cancelled) {
          retryTimer = window.setTimeout(connect, 2000);
        }
      };

      socket.onerror = () => socket.close();
    }

    connect();

    return () => {
      cancelled = true;
      window.clearTimeout(retryTimer);
      socketRef.current?.close();
    };
  }, [maxLogSize]);

  return { connectionState, log, clearLog: () => setLog([]) };
}
