---
name: decision-form
description: Turn a pile of decisions into one tappable HTML page instead of a wall of text, then wait for the user's answers before acting. Use when you need the user to decide 3 or more things at once, before an irreversible or bulk action (deleting, migrating, rewriting history, mass edits, deploys), when the user must understand trade-offs before approving, or when they ask for a form or questionnaire. Not for a single yes/no question.
license: MIT
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/build_form.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/serve_form.py *)
---

# Decision form

You write the questions as Markdown, a script turns them into one self-contained page of decision cards, the
user taps through it on a laptop or phone, and the answers come back to you. **Nothing gets executed until the
answers are back.** That pause is the point: chat is bad at showing scope, tracking many decisions at once and
giving the user room to think.

Paths below use `${CLAUDE_SKILL_DIR}`, the folder that contains this file. If your agent does not substitute it,
use that folder's absolute path.

## When to use it

- 3 or more independent decisions at once, or
- an irreversible or bulk action (delete, archive, merge, migrate, rewrite history, deploy, mass edit), or
- the user has to understand trade-offs before saying yes, or
- the user asks for a form, questionnaire or "something I can click".

One or two quick questions: ask in chat or with your built-in question tool. A form for that is ceremony.

## 1. Write the questions

Save them as `decisions/YYYY-MM-DD-<slug>.md` in the working directory (create the folder), unless the user named
another place. The `.md`, the built `.html` and the `.answers.json` together are the decision record. If the
repository should not contain them, use a temporary directory.

```markdown
# Repo cleanup before v2.0
Seven decisions, safest first. Tap a choice on each card, then send. My recommendation is marked.

## Wave 1 · safe, reversible
### Delete 23 merged branches?
All of them are merged into main and none has an open pull request.
> Longer plain-language explanation, hidden behind "Explain".
- Delete all 23 *
- Keep release/* branches, delete the rest
- Keep all

## Wave 3 · hard to undo
### When do we publish v2.0?
- Friday, after everything above is done *
- On a specific date (write which) [write]
```

Syntax: `#` title, the line under it is the intro (links as `[text](https://...)`), `##` group, `###` question,
plain lines before the options are the "why", `>` lines are the explanation, `- option`, trailing `*` marks your
recommendation, `[write]` adds a text field, `- c) text` sets a key by hand. Run
`python3 ${CLAUDE_SKILL_DIR}/scripts/build_form.py --syntax` for the full reference and the JSON format.

**How to write the cards**, because the person reading them decides, and a card they can't follow is a wrong answer
waiting to happen:

1. **Write for the person, not for an AI.** Plain words, the practical effect. If a technical term must appear,
   say right after it what will actually happen. Test: if they would ask "what does that mean?", rewrite it.
2. **Title = the question.** "Delete 23 merged branches?", not "Branch hygiene".
3. **One "why" line with what is at stake, including the downside.** A card that lists only benefits is a
   sales pitch, not a decision.
4. **Always recommend exactly one option** with `*`. You did the analysis; say where you land.
5. **2 to 4 short options.** Do not add "Other": the page adds `x) Other` with a text field to every question
   that has no text field.
6. **Group into waves, safest and most reversible first**, irreversible last. Questions are numbered across
   the whole page.
7. **Only real decisions.** Things already done go in one line of the intro. Never a card that asks the user
   to run a command for you.
8. **Short intro:** the title plus one sentence. Context belongs in the cards and their explanations.

**Two modes.** By default the user reads the form alone and needs to understand it: use "why" lines and
explanations. If the user will go through it **live on a call with someone else**, make it punchy: no
explanations, one line per card, short options, under about 500 words in total, and leave out decisions the
other side does not care about (list those at the end of the intro as "I'll handle: ...").

## 2. Build the page

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/build_form.py decisions/2026-11-17-repo-cleanup.md      # add --lang cs for Czech UI
```

It writes `decisions/2026-11-17-repo-cleanup.html` next to the source and refuses to write when a question has no
options or the page script does not parse. Do not hand-edit the HTML; fix the `.md` and rebuild.

## 3. Collect the answers

**A. Watcher (preferred when you can run a background command).** Start the server in the background:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/serve_form.py decisions/2026-11-17-repo-cleanup.html          # add --lan for a phone
```

- It prints `Open: http://127.0.0.1:<port>/?t=<token>`. Give the user that full URL (the token is required).
  With `--lan` it also prints a phone URL for the same Wi-Fi; plain HTTP, so only on a network they trust.
- Do not poll. When the user taps "Send answers", the server writes `<name>.answers.json`, prints the answers and
  exits with code 0, which ends your background command. Exit code 2 means nobody answered within the timeout
  (default 60 minutes, `--timeout`): ask the user whether to restart it.
- If the server cannot bind a port (a sandbox, for example), use route B.

**B. Copy and paste (works anywhere).** Give the user the absolute path of the `.html` file to open in a browser.
Opened as a file, the page's button says "Copy answers"; they paste a line like this into the chat:

```
Repo cleanup before v2.0: 1a 2a 3b 4a 5a 6x: Ask the QA team first 7a
```

## 4. Read the answers

- `answers.json` is unambiguous: `answers` maps question number to option key, `notes` holds typed text, and
  `readable` repeats each question title with the chosen option's text. Prefer it.
- The pasted code is `<number><key>` per answered question; text after `:` is that question's note. Option keys
  follow the order in your `.md` (a, b, c...), `x` is Other. If a note makes the line ambiguous, ask.
- **An unanswered question is not a yes to your recommendation.** Ask about it; never fill it in yourself.
- Before acting, recap in one or two lines what you are about to do. Then execute wave by wave.
- Stop and ask if two answers contradict each other, or if something changed since you wrote the form.
- When done, report briefly what happened and what is left.

## Don't

- Don't start executing before the answers are back. That is the whole point.
- Don't build a form for a trivial yes/no.
- Don't make the page depend on a CDN or a server to render: it must open offline from a file (the template
  already does).
- Don't use this to collect answers from many people; a real survey tool fits that better.
