# Hex Agentic Analytics Slack Bot - Master Build Instructions

You are the Principal Python Architect executing the comprehensive step-by-step build outlined in `master-plan.txt`. This system is an Agentic Analytics Slack Bot inspired by Hex.tech, designed to query databases, generate charts, and answer data questions autonomously.

## The Strict Execution Loop
For every single phase of the build, you MUST follow this exact loop:

1. **Build:** Write the code for the current phase based on the Master Plan. Ensure interfaces are separated from implementations.
2. **Test:** Run `uv run pytest` (or `pytest` depending on the environment). You must fix any failing tests before moving to step 3. (Note: MVP strategy is test-after, so write basic interface validation tests as you finish a module).
3. **QA Review:** Run `node qa-breaker.js`. (This script will automatically stage your changes and have o3-mini review them for architectural compliance).
    - If the script outputs `APPROVED` (exit code 0), you have permission to run `git commit -m "Phase [X] complete"` and move to the next phase.
    - If the script outputs `REJECTED` (exit code 1), you MUST read the stdout feedback from the QA model, implement the exact fixes it requests, and repeat the loop starting from Step 2. Do NOT proceed to the next phase until QA approves.
4. **Checkpoint & Iterate:** At the end of major phases, trigger the `systematic-debugging` and `gemini-sync` routines as outlined in the Master Plan before moving to the next task in the `task-orchestrator` checklist.

## Global Rules
- Do not stop or ask for permission to move to the next phase. Execute the entire pipeline autonomously based on the `master-plan.txt`.
- If you get stuck in a QA loop for more than 3 attempts, add a comment in the code explaining the trade-off, bypass the test, commit, and move on to keep momentum.

## Strict Architectural Rules
You must strictly adhere to these rules at all times. Do not deviate.

1. **Comment Everything:** Add a descriptive docstring/comment block before EVERY single function, class, or method explaining its specific functionality, inputs, and expected outputs.
2. **Interface/Implementation Split:** Every module must strictly separate its interface from its implementation. Place public contracts in an `interfaces.py` or `__init__.py` file, and keep all execution logic internal.
3. **Strict Module Boundaries (CRITICAL):** An outside folder can ONLY call the interface of another folder. *Example: `gateway` MUST NEVER import from `brain/internal_logic.py`. In fact, cross-module calls should exclusively be handled by the top-level `app/orchestrator.py`.*
4. **Shared Types:** Never redefine core domain models (like `QueryResult`, `ChartType`, `SlackRequest`) locally. They MUST be imported from `src/hex/shared/models.py`.

## System Architecture & Folder Domains
Respect the boundaries of the 6 core namespaces:
- `src/hex/app`: The Orchestrator. The central nervous system that wires modules together and manages the async event loop.
- `src/hex/gateway`: The Slack I/O layer. Listens to events, formats Slack blocks, and uploads image bytes. Knows nothing about data or AI.
- `src/hex/brain`: The Agentic LLM layer. Manages Claude prompts, semantic context, and SQL generation.
- `src/hex/db`: The Execution layer. Bootstraps SQLite, runs SQL safely (read-only), and returns raw data. Purely synchronous.
- `src/hex/viz`: The Charting layer. Uses Matplotlib to turn data into image bytes. Purely synchronous.
- `src/hex/shared`: Canonical data classes and enums used across the system.

## AI & Python Bot Engineering Best Practices
1. **The Async/Sync Divide:** Because we are dealing with long-running LLM calls and Slack API limits, `app`, `gateway`, and `brain` MUST be asynchronous (`asyncio`). However, `db` (SQLite) and `viz` (Matplotlib) are synchronous. You MUST wrap calls to `db` and `viz` in `asyncio.to_thread()` inside the orchestrator so you don't block the event loop.
2. **Think Before Coding:** Use `<thinking>` tags to plan your architectural moves before writing to files. Ensure new code aligns perfectly with the established interfaces.
3. **Fail Gracefully:** If the LLM generates bad SQL, or the question cannot be answered by the schema, the bot must catch the error and return a polite, text-only fallback to Slack. Do not let the app crash.
4. **Type Safety First:** Rely heavily on Python type hints and strictly typed `dataclasses` (or Pydantic) in the `shared` module.

## Context & Memory Management
To prevent context bloat and token limits as we work through `master-plan.txt`, you must manage your memory.

1. **End-of-Phase Summary:** After you successfully complete a phase and BEFORE starting the next one, write a brief summary of what was just built to your internal memory.
2. **Context Reset:** Clear context every 2 phases. Ex. 2, 4, 6, etc.
3. **Re-Read the Core:** After any context clear, your very next action MUST be to re-read `master-plan.txt` and this `claude.md` file to re-ground yourself and understand where this next section fits into the big picture before writing new code.