# All Painting Business Hub - Portable Install

This folder contains scripts to bootstrap a portable, unzip-and-run setup on **Windows** and **macOS**. The scripts:

1. Download a local Python runtime (or reuse an existing one).
2. Create per-service virtual environments.
3. Install each service's dependencies automatically.
4. Start the Business Hub and Business Subhub dashboards.

> The scripts are **best-effort** installers. They keep everything in the repo folder so you can move the whole directory to another machine.

## Windows

1. Right-click **install_windows.ps1** → *Run with PowerShell*.
2. When it finishes, run **run_hub_windows.bat** (and optionally **run_subhub_windows.bat**).

## macOS

```bash
./install_mac.sh
./run_hub_mac.sh
# Optional:
./run_subhub_mac.sh
```

## Notes
- Logs for the hub are stored in `master-dashboard/logs/`.
- Logs for the subhub are stored in `subhub-dashboard/logs/`.
- You can re-run the install scripts at any time to update dependencies.
