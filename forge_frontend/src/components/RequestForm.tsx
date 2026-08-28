import { useState } from "react";
import type { FormEvent } from "react";

interface RequestFormProps {
  onSubmit: (goal: string) => void;
  disabled: boolean;
  busyLabel?: string;
}

export function RequestForm({ onSubmit, disabled, busyLabel }: RequestFormProps) {
  const [goal, setGoal] = useState("");

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = goal.trim();
    if (!trimmed || disabled) return;
    onSubmit(trimmed);
  };

  return (
    <form className="request-form" onSubmit={handleSubmit}>
      <textarea
        className="request-form__input"
        placeholder="Describe what you want ForgeAI to build — e.g. “A CLI todo app with SQLite storage and a --list flag.”"
        value={goal}
        onChange={(e) => setGoal(e.target.value)}
        disabled={disabled}
        rows={3}
      />
      <button type="submit" className="request-form__submit" disabled={disabled || !goal.trim()}>
        {disabled ? (busyLabel ?? "Running…") : "Build it"}
      </button>
    </form>
  );
}
