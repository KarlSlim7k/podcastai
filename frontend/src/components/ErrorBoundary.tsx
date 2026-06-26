import { Component, ReactNode } from 'react'

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: any) {
    console.error('ErrorBoundary caught error:', error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback
      }
      return (
        <div className="fixed inset-0 z-[9999] bg-red-900/90 flex items-center justify-center p-8">
          <div className="bg-red-950 border-2 border-red-500 rounded-lg p-6 max-w-2xl">
            <h2 className="text-2xl font-bold text-red-200 mb-4">
              ⚠️ Error en el Editor Vertical
            </h2>
            <div className="bg-black/50 p-4 rounded mb-4 overflow-auto max-h-96">
              <pre className="text-red-300 text-sm whitespace-pre-wrap">
                {this.state.error?.message}
                {'\n\n'}
                {this.state.error?.stack}
              </pre>
            </div>
            <button
              onClick={() => {
                this.setState({ hasError: false, error: null })
                window.location.reload()
              }}
              className="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded"
            >
              Recargar página
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
