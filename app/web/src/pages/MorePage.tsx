/*
 * The More page (phone only). Reference links and the version lines. At 721px and up the Shell
 * redirects #/more to the current project's Live, so this page never shows on a desktop.
 */
import { useAppInfo } from "@/api/client";
import { useActiveProject } from "@/app/active-project";
import { MoreCard } from "@/components/MoreCard/MoreCard";
import { PageHeader } from "@/components/PageHeader/PageHeader";
import { VERSION } from "@/lib/version";
import { t } from "@/strings/t";
import "./MorePage.css";

export function MorePage() {
  const project = useActiveProject(null);
  const app = useAppInfo(project);
  return (
    <>
      <PageHeader title={t("more_h1")} />
      <div className="grid">
        <MoreCard
          title={t("nav_ref_h")}
          rows={[
            {
              id: "decides",
              href: "#/reference/decides",
              label: t("nav_decides"),
              icon: "decides",
            },
            {
              id: "glossary",
              href: "#/reference/glossary",
              label: t("nav_glossary"),
              icon: "glossary",
            },
          ]}
        />
        <section className="more-version" aria-labelledby="more-version-title">
          <h2 className="more-version-title" id="more-version-title">
            {t("more_ver_h")}
          </h2>
          {app.data !== undefined && (
            <p>{t("more_ver_cc", { version: app.data.claude_version })}</p>
          )}
          <p>{t("more_ver_app", { version: VERSION })}</p>
        </section>
      </div>
    </>
  );
}
