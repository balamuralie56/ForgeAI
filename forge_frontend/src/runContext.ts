import { createContext } from "react";

/**
 * The workflow run the workbench is currently showing. Report tabs read their
 * data from that run's own stored reports; `null` means no run is selected.
 */
export const RunContext = createContext<string | null>(null);
