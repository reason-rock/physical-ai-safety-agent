# Demo Walkthrough

## Start

For the fastest judge-facing walkthrough:

```powershell
start .\site\index.html
```

For the executable Python workflow:

```powershell
.\.venv\Scripts\python.exe run_demo.py --data-mode real_replay
```

For the executable web dashboard:

```powershell
.\.venv\Scripts\python.exe -m web.backend.run
cd web\frontend
npm install
npm run dev
```

## Screen Flow

1. The static demo or dashboard opens with a physical-AI safety decision already evaluated.
2. The summary cards show the current demo pair, `safer_but_slower`,
   `supported_test_only`, and `safety_manifest_only`.
3. Pair Plan shows the control/treatment split.
4. Parallel Training shows reward and fall-rate progress.
5. Research PC Evaluation shows matched metrics.
6. Safety Gate shows reasons, required actions, and Robot Action Diff.
7. Report exports a Markdown experiment note.

## Expected Decision

Unsupervised hardware testing is blocked. Supported low-speed testing is allowed
only with human approval and explicit conditions.
