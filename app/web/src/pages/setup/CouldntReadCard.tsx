/*
 * The Couldn't read card, above a part's list when a file of the part could not be opened. The list
 * below it holds what Bar Tab could read (partial results), and the card says so. It reads in one
 * order (a-m4 p11 board). The title, the cause with the file in code, the fix line, then Copy path
 * with the full local path while the screen shows the short one. The error sits beside its cause
 * with the fix (usability lesson 16).
 */
import type { SetupPartAnswer } from "@/api/types";
import { postStatus } from "@/app/harness";
import { CopyPath } from "@/components/CopyPath/CopyPath";
import { RaisedFinding } from "@/components/RaisedFinding/RaisedFinding";
import { codeWord } from "@/lib/setup-words";
import { t, tn } from "@/strings/t";

type UnreadableFile = SetupPartAnswer["unreadable"][number];

/** Reasons that are real read failures. Files outside the roots are "not read here", not failures. */
const FAILURES: ReadonlySet<UnreadableFile["reason"]> = new Set<UnreadableFile["reason"]>([
  "permission",
  "not_utf8",
  "too_large",
  "vanished",
  "folder_unlistable",
]);

/** The files the card names, in the answer's order. */
export function readFailures(files: readonly UnreadableFile[]): UnreadableFile[] {
  return files.filter((f) => FAILURES.has(f.reason));
}

/** Stands in for the file while the cause is worded, so the file can be set in code after. */
const FILE_MARK = "\u0001";

/** The cause of one file, with the file's name in code. */
function Cause({ file }: { file: UnreadableFile }) {
  const parts = codeWord("cr_r_", file.reason, { file: FILE_MARK }).split(FILE_MARK);
  return (
    <>
      {parts.map((part, index) => (
        <span key={`${part}:${String(index)}`}>
          {index > 0 && <code className="setup-code setup-cr-path">{file.file}</code>}
          {part}
        </span>
      ))}
    </>
  );
}

export function CouldntReadCard({ files }: { files: readonly UnreadableFile[] }) {
  const [only] = files;
  if (only === undefined) return null;
  const copies = files.flatMap((file) =>
    file.full_path === null ? [] : [{ file, path: file.full_path }],
  );
  return (
    <RaisedFinding variant="error" title={tn("ft_unreadable", files.length)} className="setup-cr">
      {files.length === 1 ? (
        <p>
          <Cause file={only} /> {t("cr_b")}
        </p>
      ) : (
        <>
          <ul className="setup-cr-list">
            {files.map((file) => (
              <li key={`${file.reason}:${file.file}`}>
                <Cause file={file} />
              </li>
            ))}
          </ul>
          <p>{t("cr_b")}</p>
        </>
      )}
      <p className="muted setup-small">{t("cr_fix")}</p>
      {copies.length > 0 && (
        <div className="setup-cr-actions">
          {copies.map(({ file, path }) => (
            <CopyPath
              key={`${file.reason}:${file.file}`}
              value={path}
              label={t("in_copy")}
              copiedLabel={t("an_copied")}
              ariaLabel={t("fx_copy_path_aria", { file: file.file })}
              onStatus={postStatus}
            />
          ))}
        </div>
      )}
    </RaisedFinding>
  );
}
