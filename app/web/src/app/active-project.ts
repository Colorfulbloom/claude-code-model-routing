import { useApi, useProjects } from "@/api/client";

/**
 * The project the shell works on. The route's project wins, then the one the launcher passed or
 * the person picked last, then the first project in the list. Null when there is none.
 */
export function useActiveProject(routeProject: string | null): string | null {
  const { access } = useApi();
  const projects = useProjects();
  return routeProject ?? access.getProject() ?? projects.data?.projects[0]?.key ?? null;
}
