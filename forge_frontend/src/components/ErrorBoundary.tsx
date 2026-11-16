import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Keeps one tab's rendering failure (usually an unexpected report shape) from
 * blanking the whole app. Give it a `key` that changes with the tab or run so
 * it resets once the user moves on.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Tab failed to render:", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="tab-panel report-gate__error">
          This tab couldn't be displayed because its data had an unexpected shape.
          <br />
          {this.state.error.message}
        </div>
      );
    }
    return this.props.children;
  }
}
