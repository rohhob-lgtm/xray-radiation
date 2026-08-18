import { Component, type ErrorInfo, type ReactNode } from 'react';

/**
 * Generic React error boundary — catches a render-time exception thrown by
 * anything inside it (e.g. a chat-result card given a payload shape it
 * doesn't expect) and shows a small inline fallback instead of letting the
 * error propagate to the page root, which otherwise crashes the whole view
 * (or, in dev, opens Vite's full-screen error overlay).
 *
 * React error boundaries must be class components — there is no hook
 * equivalent in stable React.
 */
export class ErrorBoundary extends Component<
  { children: ReactNode; fallback?: ReactNode },
  { hasError: boolean }
> {
  constructor(props: { children: ReactNode; fallback?: ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): { hasError: boolean } {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // eslint-disable-next-line no-console
    console.error('ErrorBoundary caught a render error:', error, info.componentStack);
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        this.props.fallback ?? (
          <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
            Something went wrong displaying this message.
          </div>
        )
      );
    }
    return this.props.children;
  }
}
