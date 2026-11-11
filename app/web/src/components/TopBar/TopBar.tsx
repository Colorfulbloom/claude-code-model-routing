import { Badge } from "../Badge/Badge";
import { cx } from "../cx";
import "./TopBar.css";

export const states = ["default", "with-project", "project-open"] as const;

export interface TopBarProps {
  /** The page name. The page h1 stays in the main content. */
  title: string;
  /** A quiet mark after the title, such as "Demo data". Left out on real data. It may be a help term. */
  badge?: React.ReactNode;
  /** The project button. Its visible name is its accessible name, so a screen reader hears what is on screen. */
  project?: {
    name: string;
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
export function TopBar({ title, badge, project, projectRef, className }: TopBarProps) {
  return (
    <header className={cx("top-bar", className)}>
      <div className="top-bar-name">
        <p className="top-bar-title">{title}</p>
        {badge !== undefined && <Badge>{badge}</Badge>}
      </div>
      {project !== undefined && (
        <button
          type="button"
          className="top-bar-project"
          ref={projectRef}
          aria-haspopup="listbox"
          aria-expanded={project.open === true}
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
