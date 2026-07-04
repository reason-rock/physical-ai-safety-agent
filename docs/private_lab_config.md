# Private Lab Configuration

Private values live in `.env`, which is ignored by git. Commit
`.env.example`, but do not commit `.env`.

## Current Safety Defaults

The private `.env` may contain real GPU0/GPU1 training endpoints and hardware
hosts, but the public code still keeps these safety defaults:

- `GAITLAB_USE_MOCK_NODES=true`
- `GAITLAB_ENABLE_SSH=false`
- `GAITLAB_ALLOW_REAL_ROBOT=false`

This means the app can display the real lab topology without opening SSH
connections or sending hardware commands.

## Check Loaded Values

```powershell
.\.venv\Scripts\python.exe scripts\check_env.py
```

The output masks secret-like values. Do not paste `.env` into public docs,
issues, or pull requests.
