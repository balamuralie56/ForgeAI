import { useCallback, useEffect, useRef, useState } from "react";
import { StatusBar } from "./components/StatusBar";
import { RequestForm } from "./components/RequestForm";
import { PipelineView } from "./components/PipelineView";
import { EventLog } from "./components/EventLog";
import { FileBrowser } from "./components/FileBrowser";
import { api, ApiError } from "./api";
import { useEventStream } from "./useEventStream";
import type { WorkflowStatus } from "./types";
import "./App.css";

const ACTIVE_STATES = new Set(["PENDING", "RUNNING", "WAITING"]);

function App() {
  const { connectionState, log } = useEventStream();
  const [workflow, setWorkflow] = useState<WorkflowStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<number | undefined>(undefined);

  const pollStatus = useCallback(function poll(id: string) {
    api
      .getWorkflow(id)
      .then((status) => {
        setWorkflow(status);
        if (ACTIVE_STATES.has(status.state)) {
          pollRef.current = window.setTimeout(() => poll(id), 1500);
        }
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, []);

  useEffect(() => () => window.clearTimeout(pollRef.current), []);

  const startWorkflow = (goal: string) => {
    setError(null);
    api
      .createWorkflow(goal)
      .then((res) => {
        pollStatus(res.workflow_id);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  };

  const isRunning = workflow ? ACTIVE_STATES.has(workflow.state) : false;

  return (
    <div className="app">
      <StatusBar connectionState={connectionState} />

      <main className="app__main">
        <section className="app__intake">
          <RequestForm onSubmit={startWorkflow} disabled={isRunning} />
          {error && <div className="app__error">{error}</div>}
        </section>

        {workflow && (
          <section className="app__pipeline">
            <PipelineView workflow={workflow} />
          </section>
        )}

        <section className="app__split">
          <EventLog events={log} />
          {workflow && workflow.state === "COMPLETED" && (
            <div className="app__files">
              <div className="app__files-header">Generated files</div>
              <FileBrowser workflowId={workflow.id} />
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

export default App;
