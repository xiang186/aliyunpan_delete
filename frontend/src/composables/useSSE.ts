import { ref, onUnmounted } from 'vue'

// How many consecutive onerror events before we give up and call onConnectionError.
// This prevents transient errors (Vite HMR, brief network blip) from being
// treated as permanent failures.
const MAX_RETRIES = 3
// Delay between retry attempts (ms)
const RETRY_DELAY = 1500

export function useSSE() {
  const isConnected = ref(false)
  const error = ref<string | null>(null)
  let eventSource: EventSource | null = null
  let terminalEventReceived = false
  let retryCount = 0
  let retryTimer: ReturnType<typeof setTimeout> | null = null
  let currentUrl = ''
  let currentHandlers: Record<string, (data: any) => void> = {}
  let currentOnError: (() => void) | undefined

  function connect(
    url: string,
    handlers: Record<string, (data: any) => void>,
    onConnectionError?: () => void,
  ) {
    // Store for potential retries
    currentUrl = url
    currentHandlers = handlers
    currentOnError = onConnectionError

    _connect()
  }

  function _connect() {
    _closeSource()
    terminalEventReceived = false
    eventSource = new EventSource(currentUrl)
    isConnected.value = true
    error.value = null

    eventSource.onerror = () => {
      isConnected.value = false
      error.value = 'SSE connection error'

      // If we already received a terminal event, the stream ended normally.
      // The browser fires onerror when it tries to reconnect after the server
      // closes the connection — just close and ignore.
      if (terminalEventReceived) {
        _closeSource()
        return
      }

      retryCount++
      console.log(`[useSSE] onerror (retry ${retryCount}/${MAX_RETRIES}) for ${currentUrl}`)

      if (retryCount < MAX_RETRIES) {
        // Transient error — close current source and retry after a delay.
        _closeSource()
        retryTimer = setTimeout(() => {
          console.log(`[useSSE] retrying connection to ${currentUrl}`)
          _connect()
        }, RETRY_DELAY)
      } else {
        // Exceeded retries — treat as a real connection failure.
        console.log(`[useSSE] max retries exceeded, calling onConnectionError`)
        _closeSource()
        retryCount = 0
        currentOnError?.()
      }
    }

    for (const [eventType, handler] of Object.entries(currentHandlers)) {
      eventSource.addEventListener(eventType, (e: Event) => {
        // Successful event received — reset retry counter.
        retryCount = 0
        const msgEvent = e as MessageEvent
        try {
          const data = JSON.parse(msgEvent.data)
          if (eventType === 'complete' || eventType === 'error' || eventType === 'stopped') {
            terminalEventReceived = true
          }
          handler(data)
        } catch {
          handler(msgEvent.data)
        }
      })
    }
  }

  function _closeSource() {
    if (retryTimer !== null) {
      clearTimeout(retryTimer)
      retryTimer = null
    }
    if (eventSource) {
      eventSource.close()
      eventSource = null
      isConnected.value = false
    }
  }

  function disconnect() {
    retryCount = 0
    terminalEventReceived = false
    _closeSource()
  }

  onUnmounted(disconnect)

  return { isConnected, error, connect, disconnect }
}
