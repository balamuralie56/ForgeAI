import { useCallback, useEffect, useRef, useState } from "react";
import { StatusBar } from "./components/StatusBar";
import { HistorySidebar } from "./components/HistorySidebar";
import { AssistantView } from "./components/assistant/AssistantView";
import { ErrorBoundary } from "./components/ErrorBoundary";
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
import { RunContext } from "./runContext";
import { useEventStream } from "./useEventStream";
import type { RunDetail, StageStatus, WorkflowStatus } from "./types";
import "./App.css";

const ACTIVE_STATES = new Set(["PENDING", "RUNNING", "WAITING"]);
const VIEW_KEY = "forge.view";

type View = "build" | "assistant";

function initialView(): View {
  try {
    return window.localStorage.getItem(VIEW_KEY) === "assistant" ? "assistant" : "build";
  } catch {
    return "build";
  }
}

function findStage(workflow: WorkflowStatus | null, name: string): StageStatus | undefined {
  return workflow?.stages.find((s) => s.name === name);
}

function toWorkflowStatus(run: RunDetail): WorkflowStatus {
  return {
    id: run.workflow_id,
    name: run.name,
    type: run.workflow_type,
    state: run.state,
    progress: run.progress,
    stages: run.stages.map((s) => ({
      name: s.name ?? "",
      status: s.status ?? "PENDING",
      started_at: s.started_at ?? null,
      completed_at: s.completed_at ?? null,
      error: s.error ?? null,
      optional: s.optional ?? false,
      critical: s.critical ?? true,
    })),
    errors: run.errors,
    created_at: run.created_at,
    updated_at: run.updated_at,
  };
}

function App() {
  const { connectionState, log } = useEventStream();
  const [workflow, setWorkflow] = useState<WorkflowStatus | null>(null);
  const [openedFromHistory, setOpenedFromHistory] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState("overview");
  const [view, setView] = useState<View>(initialView);
  const pollRef = useRef<number | undefined>(undefined);
  const currentIdRef = useRef<string | null>(null);

  const pollStatus = useCallback(function poll(id: string) {
    api
      .getWorkflow(id)
      .then((status) => {
        // The user may have opened a different run while this request was in flight.
        if (currentIdRef.current !== id) return;
        setWorkflow(status);
        if (ACTIVE_STATES.has(status.state)) {
          pollRef.current = window.setTimeout(() => poll(id), 1500);
        }
      })
      .catch((e) => {
        if (currentIdRef.current === id) setError(e instanceof ApiError ? e.message : String(e));
      });
  }, []);

  useEffect(() => () => window.clearTimeout(pollRef.current), []);

  const startWorkflow = (goal: string) => {
    setError(null);
    api
      .createWorkflow(goal)
      .then((res) => {
        window.clearTimeout(pollRef.current);
        currentIdRef.current = res.workflow_id;
        setOpenedFromHistory(false);
        setActiveTab("overview");
        pollStatus(res.workflow_id);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  };

  const selectRun = (id: string) => {
    window.clearTimeout(pollRef.current);
    currentIdRef.current = id;
    setError(null);
    api
      .getRun(id)
      .then((run) => {
        if (currentIdRef.current !== id) return;
        const status = toWorkflowStatus(run);
        setWorkflow(status);
        setOpenedFromHistory(true);
        setActiveTab("overview");
        if (ACTIVE_STATES.has(status.state)) pollStatus(id);
      })
      .catch((e) => {
        if (currentIdRef.current === id) setError(e instanceof ApiError ? e.message : String(e));
      });
  };

  const newBuild = () => {
    window.clearTimeout(pollRef.current);
    currentIdRef.current = null;
    setWorkflow(null);
    setOpenedFromHistory(false);
    setError(null);
    setActiveTab("overview");
  };

  const handleDeleted = (id: string) => {
    if (id === currentIdRef.current) newBuild();
  };

  const changeView = (next: View) => {
    setView(next);
    try {
      window.localStorage.setItem(VIEW_KEY, next);
    } catch {
      // Storage can be unavailable (private mode); the view just isn't remembered.
    }
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
      <StatusBar connectionState={connectionState} view={view} onViewChange={changeView} />

      {view === "assistant" && (
        <div className="app__body">
          <ErrorBoundary>
            <AssistantView />
          </ErrorBoundary>
        </div>
      )}

      <div className="app__body" hidden={view !== "build"}>
        <HistorySidebar
          selectedId={workflow?.id ?? null}
          refreshKey={`${workflow?.id}|${workflow?.state}|${workflow?.progress}`}
          onSelect={selectRun}
          onNew={newBuild}
          onDeleted={handleDeleted}
        />

        <RunContext.Provider value={workflow?.id ?? null}>
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
                <ErrorBoundary key={`${activeTab}|${workflow?.id}`}>
                  {activeTab === "overview" && (
                    <OverviewTab workflow={workflow} isRunning={isRunning} onSubmit={startWorkflow} />
                  )}
                  {activeTab === "plan" && <PlanTab enabled={isDone("planner")} />}
                  {activeTab === "architecture" && <ArchitectureTab enabled={isDone("architect")} />}
                  {activeTab === "files" && workflow && (
                    <>
                      {openedFromHistory && (
                        <div className="app__note">
                          Generated files are shared by all runs, so this shows the current workspace,
                          which may include files from a later run.
                        </div>
                      )}
                      <FilesTab
                        workflowId={workflow.id}
                        isActive={isRunning}
                        reportReady={isDone("developer")}
                      />
                    </>
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
                </ErrorBoundary>
              </div>
            </section>
          </main>
        </RunContext.Provider>
      </div>
    </div>
  );
}

export default App;
