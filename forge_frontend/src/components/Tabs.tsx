export interface TabDef {
  id: string;
  label: string;
  disabled?: boolean;
  badge?: number;
}

export function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: TabDef[];
  active: string;
  onChange: (id: string) => void;
}) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          role="tab"
          type="button"
          aria-selected={active === tab.id}
          className={`tabs__item ${active === tab.id ? "tabs__item--active" : ""}`}
          disabled={tab.disabled}
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
          {typeof tab.badge === "number" && tab.badge > 0 && (
            <span className="tabs__badge">{tab.badge}</span>
          )}
        </button>
      ))}
    </div>
  );
}
