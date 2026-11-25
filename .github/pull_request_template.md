## What this changes
<!-- One or two sentences. Which module? Why? -->

## How it was checked
- [ ] Backend tests pass locally (`cd backend; .\.venv\Scripts\python.exe -m pytest -q`)
- [ ] Frontend type check passes (`cd frontend; npx tsc --noEmit`)
- [ ] Tried it in the running app
- [ ] **UI change:** screenshot before / after attached below

## Checklist
- [ ] A line added under **Unreleased** in `CHANGELOG.md`
- [ ] New database change? One Alembic migration, created after pulling the latest `main` (see CONTRIBUTING.md)
- [ ] No secrets, `.env`, customer documents or database dumps in the diff
- [ ] Touches shared code (`app/core`, `app/ai`, `ui.tsx`, models)? Explained below

## Screenshots / notes
