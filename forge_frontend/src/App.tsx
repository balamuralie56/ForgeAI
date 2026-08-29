import { useCallback, useEffect, useRef, useState } from "react";
import { StatusBar } from "./components/StatusBar";
import { PipelineView } from "./components/PipelineView";
import { EventLog } from "./components/EventLog";
import { Tabs } from "./components/Tabs";
import type { TabDef } from "./components/Tabs";
import { OverviewTab } from "./components/tabs/OverviewTab";
import { PlanTab } from "./components/tabs/PlanTab";
import { ArchitectureTab } from "./components/tabs/ArchitectureTab";
import { FilesTab } from "./components/tabs/FilesTab";
import { TestsTab } from "./components/tabs/TestsTab";
import { DocumentationTab } from "./components/tabs/DocumentationTab";
import { SecurityTab } from "./components/tabs/SecurityTab";
import { ReviewTab } from "./components/tabs/ReviewTab";
import { GitTab } from "./components/tabs/GitTab";
import { api, ApiError } from "./api";
import { useEventStream } from "./useEventStream";
import type { StageStatus, WorkflowStatus } from "./types";
import "./App.css";

const ACTIVE_STATES = new Set(["PENDING", "RUNNING", "WAITING"]);

function findStage(workflow: WorkflowStatus | null, name: string): StageStatus | undefined {
  return workflow?.stages.find((s) => s.name === name);
}

function App() {
  const { connectionState, log } = useEventStream();
  const [workflow, setWorkflow] = useState<WorkflowStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState("overview");
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
        setActiveTab("overview");
        pollStatus(res.workflow_id);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  };

  const isRunning = workflow ? ACTIVE_STATES.has(workflow.state) : false;
  const isDone = (stageName: string) => findStage(workflow, stageName)?.status === "COMPLETED";
  const stageDot = (stageName: string): string => {
    const status = findStage(workflow, stageName)?.status;
    if (status === "COMPLETED") return "●";
    if (status === "RUNNING" || status === "WAITING") return "◐";
    if (status === "FAILED") return "✕";
    return "";
  };

  const tabs: TabDef[] = [
    { id: "overview", label: "Overview" },
    { id: "plan", label: `Plan ${stageDot("planner")}`.trim() },
    { id: "architecture", label: `Architecture ${stageDot("architect")}`.trim() },
    { id: "files", label: `Files ${stageDot("developer")}`.trim() },
    { id: "tests", label: `Tests ${stageDot("tester")}`.trim() },
    { id: "docs", label: `Docs ${stageDot("documentation")}`.trim() },
    { id: "security", label: `Security ${stageDot("security")}`.trim() },
    { id: "review", label: `Review ${stageDot("reviewer")}`.trim() },
    { id: "git", label: `Git ${stageDot("git")}`.trim() },
    { id: "activity", label: "Activity", badge: isRunning ? undefined : 0 },
  ];

  return (
    <div className="app">
      <StatusBar connectionState={connectionState} />

      <main className="app__main">
        {error && <div className="app__error">{error}</div>}

        {workflow && (
          <section className="app__pipeline">
            <PipelineView workflow={workflow} />
          </section>
        )}

        <section className="app__workbench">
          <Tabs tabs={tabs} active={activeTab} onChange={setActiveTab} />

          <div className="app__tab-body">
            {activeTab === "overview" && (
              <OverviewTab workflow={workflow} isRunning={isRunning} onSubmit={startWorkflow} />
            )}
            {activeTab === "plan" && <PlanTab enabled={isDone("planner")} />}
            {activeTab === "architecture" && <ArchitectureTab enabled={isDone("architect")} />}
            {activeTab === "files" && workflow && (
              <FilesTab workflowId={workflow.id} isActive={isRunning} />
            )}
            {activeTab === "files" && !workflow && (
              <div className="tab-panel report-gate__empty">
                Files appear here once a build starts.
              </div>
            )}
            {activeTab === "tests" && <TestsTab enabled={isDone("tester")} />}
            {activeTab === "docs" && <DocumentationTab enabled={isDone("documentation")} />}
            {activeTab === "security" && <SecurityTab enabled={isDone("security")} />}
            {activeTab === "review" && <ReviewTab enabled={isDone("reviewer")} />}
            {activeTab === "git" && <GitTab enabled={isDone("git")} />}
            {activeTab === "activity" && (
              <div className="tab-panel tab-panel--activity">
                <EventLog events={log} />
              </div>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}

export default App;
