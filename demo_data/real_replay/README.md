# Sanitized Real Replay Data

This folder contains aggregate replay evidence derived from private DARwIn-OP robot CSV logs. Raw robot logs, hostnames, private paths, credentials, and checkpoints are intentionally excluded. The public app can use these files without connecting to a robot or training server.

Regenerate locally with:

```powershell
.\.venv\Scripts\python.exe scripts\build_real_replay.py --control-csv <private-control.csv> --treatment-csv <private-treatment.csv>
```
