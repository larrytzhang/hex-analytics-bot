# Engineering Guidelines


## 1. Core Principles
- **Simplicity first**: Make every change as simple as possible. Touch minimal code. Senior-developer standards — no laziness, no temporary fixes, find root causes.
- **Engineered enough**: Not under-engineered (fragile, hacky) and not over-engineered (premature abstraction, unnecessary complexity).
- **Explicit over clever**: Bias toward clarity. Handle more edge cases, not fewer — thoughtfulness beats speed.
- **DRY aggressively**: Flag repetition. Duplication is a design smell, not a shortcut.
- **Comment everything**: Every function, class, and non-trivial block gets a comment explaining *why*. Code shows *what*; comments explain intent, constraints, and tradeoffs.
- **Separate interface from implementation**: Public contracts live apart from private mechanics. Callers depend on interfaces, never on internal details. Changing implementation must not force callers to change.


## 2. Planning & Task Management
- Enter plan mode for any non-trivial task (3+ steps or architectural decisions). Skip it for simple, obvious fixes.
- Write the plan to `tasks/todo.md` as a checkable list and confirm it with the user before touching code.
- Write detailed specs upfront — reduce ambiguity before starting.
- If anything goes sideways mid-task, STOP and re-plan. Don't keep pushing.
- As you work: mark items complete, give a high-level summary at each step, and add a review section to `tasks/todo.md` when done.


## 3. Review Protocol
Before implementing non-trivial changes, review through the four lenses below. For every issue found: describe the problem concretely with file/line references, present 2–3 options (including "do nothing" when reasonable), state effort/risk/impact/maintenance for each, give an opinionated recommendation tied to the Core Principles, and wait for user agreement before proceeding. Pause after each section for feedback. Don't assume priorities on timeline or scale.


1. **Architecture**: system design, component boundaries, coupling, data flow, scaling, single points of failure, security boundaries (auth, data access, API surface).
2. **Code quality**: organization, DRY violations, error handling, missing edge cases, technical debt, over/under-engineering.
3. **Tests**: coverage gaps across unit/integration/e2e, assertion strength, edge cases, untested failure modes and error paths.
4. **Performance**: N+1 queries and DB access patterns, memory usage, caching opportunities, hot/high-complexity paths.


For big changes, surface up to 4 issues per section. For small changes, surface one question per section.


## 4. Testing
- Well-tested code is non-negotiable — too many tests beats too few.
- Cover unit, integration, and e2e paths where each applies.
- Test failure modes and error paths, not just happy paths.
- Never mark work complete without tests that prove correctness.


## 5. Subagents
- Use subagents liberally to keep the main context window clean.
- Offload research, exploration, and parallel analysis.
- One focused task per subagent.
- For complex problems, throw more compute at it via parallel subagents.


## 6. Verification & Elegance
- Never mark a task complete without proving it works: run tests, check logs, demonstrate correctness. Diff behavior against main when relevant.
- Ask: "Would a staff engineer approve this?"
- For non-trivial changes, pause and ask "is there a more elegant way?" If a fix feels hacky, redo it knowing everything you now know.
- Autonomous bug fixing: given a bug report, failing test, or broken CI — just fix it. Point at the logs/errors, resolve them, no hand-holding required.


## 7. Self-Improvement
- After any correction from the user, append the pattern and a preventive rule to `tasks/lessons.md`.
- Review `tasks/lessons.md` at session start for the current project.
- Iterate ruthlessly on these lessons until the mistake rate drops.



