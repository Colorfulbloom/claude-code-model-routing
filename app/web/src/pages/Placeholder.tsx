/* The page for every route that has no screen yet: its header and a page-level empty state. Dev-only wording. */
import { EmptyState } from "@/components/EmptyState/EmptyState";
import { PageHeader } from "@/components/PageHeader/PageHeader";
import { pageName } from "@/app/routes";
import type { PageId } from "@/app/routes";
import { t } from "@/strings/t";

export function Placeholder({ page }: { page: PageId }) {
  return (
    <>
      <PageHeader title={pageName(page)} />
      <EmptyState variant="page" mark="neutral">
        {t("ph_body")}
      </EmptyState>
    </>
  );
}
