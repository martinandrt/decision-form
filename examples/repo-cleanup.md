# Repo cleanup before v2.0

Seven decisions, safest first. Tap a choice on each card, then send. My recommendation is marked.

## Wave 1 · safe, reversible

### Delete 23 merged branches?
All of them are merged into main and none has an open pull request.
- Delete all 23 *
- Keep release/* branches, delete the rest
- Keep all

### Move CI from Travis to GitHub Actions?
Travis builds take 14 minutes and fail at random about 1 run in 10.
> We would port four jobs: lint, tests, build and deploy. The deploy job needs one new repository secret. If anything breaks, the Travis config stays in git and can be switched back in one commit.
- Port all four jobs *
- Port tests only, keep deploy on Travis
- Not now

## Wave 2 · changes behaviour for users

### Drop Node 18 support?
Node 18 is end-of-life, but 6% of last month's installs still used it.
- Drop it in v2.0 *
- Keep it one more release with a warning
- Keep it

### Rename config keys to camelCase?
Matches the API, but every user has to touch their config file.
> Today the config uses snake_case and the API uses camelCase, so people mix them up. A small migration script can rewrite old configs automatically on first run, so nobody's setup breaks.
- Rename and ship an automatic migration *
- Rename and document it only
- Keep snake_case

### Default log level
- info *
- warn
- debug

## Wave 3 · hard to undo

### Remove 400 MB of test videos from git history?
Clone size would drop from 410 MB to 12 MB, but every fork and open pull request has to rebase.
> Rewriting history changes every commit hash after the first video was added. The alternative keeps history as it is and moves new videos to Git LFS, so the repo stops growing but does not shrink.
- Keep history, move new videos to Git LFS *
- Rewrite history after tagging the old one
- Leave it as it is

### When do we publish v2.0?
- Friday, after everything above is done *
- In two weeks
- On a specific date (write which) [write]
