import { useState } from "react";
import { manifest, type ManifestEntry } from "./manifest";
import { W } from "./words";

type Theme = "light" | "dark" | "system";

const themes: { id: Theme; label: string }[] = [
  { id: "light", label: W.sheet_theme_light },
  { id: "dark", label: W.sheet_theme_dark },
  { id: "system", label: W.sheet_theme_system },
];

const stateWords: Record<string, string> = {
  default: W.cs_s_default,
  hover: W.cs_s_hover,
  focus: W.cs_s_focus,
  pressed: W.cs_s_pressed,
  disabled: W.cs_s_disabled,
  selected: W.cs_s_selected,
  empty: W.cs_s_empty,
  error: W.cs_s_error,
};

function applyTheme(theme: Theme) {
  if (theme === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = theme;
}

function groupByComponent(entries: ManifestEntry[]): Map<string, ManifestEntry[]> {
  const groups = new Map<string, ManifestEntry[]>();
  for (const entry of entries) {
    const list = groups.get(entry.component) ?? [];
    list.push(entry);
    groups.set(entry.component, list);
  }
  return groups;
}

/** The component sheet: every component in every state, with a theme switch for review. */
export function Sheet() {
  const [theme, setTheme] = useState<Theme>("system");
  const groups = groupByComponent(manifest);
  return (
    <main className="sheet">
      <header className="sheet-head">
        <div>
          <h1 className="sheet-title">{W.cs_h1}</h1>
          <p className="muted">{W.cs_sub}</p>
        </div>
        <fieldset className="sheet-theme">
          <legend>{W.sheet_theme}</legend>
          {themes.map((option) => (
            <label
              key={option.id}
              className={option.id === theme ? "sheet-theme-on chosen" : undefined}
            >
              <input
                type="radio"
                name="theme"
                value={option.id}
                checked={option.id === theme}
                onChange={() => {
                  setTheme(option.id);
                  applyTheme(option.id);
                }}
              />
              {option.label}
            </label>
          ))}
        </fieldset>
      </header>
      {[...groups].map(([component, entries]) => (
        <section key={component} className="sheet-section" aria-labelledby={`sheet-${component}`}>
          <h2 id={`sheet-${component}`} className="sheet-section-title">
            {component}
          </h2>
          <div className="sheet-cells">
            {entries.map((entry) => (
              <div
                key={entry.state}
                className="sheet-cell"
                data-component={entry.component}
                data-state={entry.state}
              >
                <div className="sheet-demo">{entry.render()}</div>
                <p className="sheet-caption">{stateWords[entry.state] ?? entry.state}</p>
              </div>
            ))}
          </div>
        </section>
      ))}
    </main>
  );
}
