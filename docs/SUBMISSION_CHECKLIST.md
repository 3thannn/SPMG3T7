# Submission checklist: one ZIP, numbered folders 1–7

Due Friday of Week 12 (6 Nov 2026), 23:59, on eLearn. Only the latest upload is
graded, and the late penalty starts in the first hour, so upload with time to
spare. Tick each line when the file is in the folder.

## Before building the ZIP

- [ ] PR #66 (CI fixes) merged, and CI green on the commit being submitted.
- [ ] Test workbook regenerated from that commit's CI run (see folder 3).
- [ ] Sprint 5 review and retrospective held; `Sprint 5.docx` completed and exported.
- [ ] Both instructors added to https://github.com/3thannn/SPMG3T7 (Settings → Collaborators).

## Folder 1: Product backlog

- [ ] `Product_Backlog.xlsx`, reconciled with Jira (statuses, US14.3/US14.6/US12.4
      ACs, the new US10.5; list in [`GAP_CLOSURE_CHANGE_LOG.md`](GAP_CLOSURE_CHANGE_LOG.md)).
- [ ] Jira export of project SPMG3T7 (all 22 epics and 66 stories, completed and pending).

## Folder 2: System design (C4)

- [ ] `ConnectSphere_C4_System_Design.pdf` (from [`docs/design/`](design/)).
- [ ] Optional: the three diagram PNGs beside it.

## Folder 3: Test cases and evidence

- [ ] `ConnectSphere_Test_Cases.xlsx`, regenerated from the final CI run.
- [ ] `REQUIREMENTS_BASELINE.md` (what the system must do, and each gap's decision).
- [ ] Optional: a screenshot or export of the final green CI run.

## Folder 4: Sprint evidence (all sprints)

- [ ] `Sprint 1.docx` … `Sprint 5.docx` and `Definition of Done.docx`, as PDF or Word.
- [ ] Jira sprint boards and burndown charts for Sprints 1–5.
- [ ] Final sprint recordings as **unlisted links** (not video files): planning,
      one daily standup, review, retrospective. Check each link plays when signed out.

## Folder 5: Slide deck

- [ ] The completed course template, exported as a **self-contained PDF**.

## Folder 6: Release

- [ ] The repository at the submitted commit (a `git archive` of it, so no
      `.env`, `.venv`, `node_modules`, `coverage`, `test-results` or `~$*` lock files).
- [ ] `README.md` (run instructions and the tested fresh-install order).
- [ ] The CI configuration, `.github/workflows/ci.yml`, is inside the archive.

```bash
git archive --format=zip -o 6-release.zip HEAD
```

## Folder 7: Repository access

- [ ] A short README: the GitHub URL, the submitted commit hash, and confirmation
      that both instructors have access.

## Last check

- [ ] Unzip the ZIP somewhere new; open every file; follow the README's fresh-install
      steps far enough to see the app sign in.
- [ ] Upload, then download it back from eLearn and check it is the right file.
