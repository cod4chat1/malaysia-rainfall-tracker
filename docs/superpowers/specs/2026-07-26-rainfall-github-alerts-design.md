# Rainfall GitHub Alert Design

## Goal

Replace the Gmail SMTP notification implementation with the same GitHub issue
alert pattern used by the ship-traffic tracker. The rainfall update must notify
the repository owner after each scheduled or manually triggered `recent` run
without requiring another mail account, App Password, or email secrets.

## Design

The daily workflow will grant `issues: write` permission and use
`actions/github-script` in an `always()` step after the rainfall update.

The alert step will:

1. Read the last JSON run summary from `rainfall-run.log`, when available.
2. Determine whether the update succeeded or failed.
3. Create a `daily-update-alerts` label if it does not exist.
4. Find the existing open issue carrying that label.
5. Add a new comment to that issue, or create the issue on the first run.
6. Mention the repository owner so GitHub can deliver the alert through the
   owner's normal GitHub notification email.

Each alert will include the completion status, Malaysia-time timestamp,
processed dates, rows written, unavailable/skipped dates, Google Sheet link,
and GitHub Actions run link. Successful runs with no new CHIRPS data will still
produce an alert so the user knows the automation completed.

## Scope Changes

- Remove the Gmail SMTP notification module and its tests.
- Remove documentation for `RAINFALL_EMAIL_FROM`,
  `RAINFALL_EMAIL_APP_PASSWORD`, and `RAINFALL_EMAIL_TO`.
- Do not add new repository secrets.
- Preserve the existing rainfall download, aggregation, Google Sheets, backfill,
  and scheduling behavior.
- Keep one open alert issue instead of creating a new issue every day.

## Failure Handling

The alert step runs with `always()` and is non-blocking, so an issue-notification
failure cannot change the rainfall job's result. If the main update fails before
creating a summary, the alert will still report failure and link to the workflow
run for diagnosis.

## Validation

- Run the existing Python test suite and lint checks.
- Validate the workflow diff and confirm that no Gmail secret references remain.
- Confirm the workflow has `contents: read` and `issues: write`.
- After merge, manually run `recent` and verify that the alert issue/comment is
  created with a mention, Sheet link, and workflow link.
