import { cx } from "../cx";
import "./TopBar.css";

export const states = ["default", "with-project", "project-open"] as const;

export interface TopBarProps {
  /** The page name. The page h1 stays in the main content. */
  title: string;
  /** The project button. Its accessible name starts with `projectLabel`, then the name. */
  project?: {
    name: string;
    /** The full accessible name, such as "Project, Tidewater reporting". */
    label: string;
    /** True while the project tray is open. It draws the 2px accent ring. */
    open?: boolean;
    /** The name is the "Pick a project" placeholder, so it shows muted. */
    placeholder?: boolean;
    onPress: () => void;
  };
  /** The project button's ref, so the page can return focus to it when the tray closes. */
  projectRef?: React.Ref<HTMLButtonElement>;
  className?: string;
}

/**
 * Sticky 52px bar with the page name and the project button at 720px and below (components.md
 * entry 2). The button opens the project tray, so it carries aria-haspopup and aria-expanded.
 */
export function TopBar({ title, project, projectRef, className }: TopBarProps) {
  return (
    <header className={cx("top-bar", className)}>
      <p className="top-bar-title">{title}</p>
      {project !== undefined && (
        <button
          type="button"
          className="top-bar-project"
          ref={projectRef}
          aria-haspopup="listbox"
          aria-expanded={project.open === true}
          aria-label={project.label}
          onClick={project.onPress}
        >
          <span
            className={cx("top-bar-project-name", project.placeholder === true && "is-placeholder")}
          >
            {project.name}
          </span>
          <span className="top-bar-project-caret" aria-hidden="true">
            {"\u25BE"}
          </span>
        </button>
      )}
    </header>
  );
}
