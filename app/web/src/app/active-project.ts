import { useApi, useProjects } from "@/api/client";

/**
 * The project the shell works on. The route's project wins, then the one the launcher passed or
 * the person picked last, then the first project in the list. Null when there is none.
 *
 * On the picker route (#/ with no launch project) the first-project fallback is off, so the
 * sidebar Select shows its "Pick a project" placeholder until a pick. Other routes keep it.
 */
export function useActiveProject(
  routeProject: string | null,
  options: { fallback?: boolean } = {},
): string | null {
  const { fallback = true } = options;
  const { access } = useApi();
  const projects = useProjects();
  const first = fallback ? (projects.data?.projects[0]?.key ?? null) : null;
  return routeProject ?? access.getProject() ?? first;
}
