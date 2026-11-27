# GitHub-AI-MCP 1.0.1 — startup and tunnel guide

Start with the [Windows quickstart](QUICKSTART_EN.md) for developer tools, vendor downloads,
locked dependencies, the one-file build and first-run configuration.
The single EXE needs no Python installation. Native Windows packaging has not been run in this Linux session.

Open Setup. Select the official tunnel executable and an existing YAML using Browse.
Save its runtime control-plane key in the password field, separately from GitHub PAT,
OpenAI model credentials and the local HTTP MCP token. Enable Windows logon startup,
service startup, and the services you need; tray, recovery and notifications are optional.
Save, reopen Setup, repair the main stdio command with backup, then validate with doctor.
The installed client determines schema acceptance. Initial cloud tunnel creation remains
with the provider. Local application features do not require a tunnel.

Only an OS-approved keyring backend is accepted. Runtime keys are scoped to the child's
environment, never startup argv or application JSON/YAML. Existing shell credentials
are not imported. Replace a key by entering a new one and saving; remove it with the
dedicated button. Keys are not redisplayed. Expired/rejected credentials require repair.

The two MCP transports are independent: authenticated loopback HTTP is owned by the GUI;
the tunnel launches a separate stdio worker process. Source mode uses the current Python
module. Frozen mode uses the same `GitHub-AI-MCP.exe` with `--internal-server`,
`--config` and `serve --transport stdio`; no sibling console EXE is required.

A live tunnel process does not prove remote availability. Owned-process health is read
only from a loopback listener attributed to that PID. Recent local component observations
are shown separately. Older/unknown health schemas remain unverified. External clients
using the selected executable are reported as unmanaged and never terminated or adopted.
Readiness alone is insufficient. Remote availability remains unverified until an actual
remote read-only invocation is performed through your account.

Use Run Diagnostics / Copy Safe Diagnostics for structured states without raw stderr,
profile contents or credentials. The YAML editor masks literal secrets, validates before
replacement, backs up and writes atomically. Invalid edits leave the original untouched.
Masked malformed-profile backups may not exactly reproduce the original. Valid command
repair retains unrelated settings and an exact original backup.

Startup uses one per-user HKCU Run value without elevation. Validate shows actual command
registration; Enable/Repair requires explicit selection. Open Windows startup settings to
inspect it. Disable by clearing the checkbox and saving. Remove an older application's
Startup-folder shortcut first if Setup reports a conflict. Windows may independently
disable Startup apps; verify in its settings and by a real logon test.

Transient timeouts/crashes get at most three retries with exponential delay and jitter.
Exit 2, invalid profiles and detected authentication rejection stop repeated attempts.
Manual Start resets attempts after repairs. Known authentication rejection from a live
owned process stops it. Network recovery inside a running vendor client remains vendor-managed.

After moving or updating the application, repair startup registration and the YAML MCP
command. Source environments need dependency reinstall after relocation. Keep the single EXE at its configured path. Exit using the application's menu to stop owned services.
To remove the portable application, disable startup, optionally remove the runtime key,
exit and delete the EXE. User data and remaining vault credentials are retained. Repository
permissions and policy mode are unchanged. Duplicate GUI launches are rejected by the
existing kernel-owned lock; they do not focus an existing window.

Run native acceptance under an isolated Windows account: EXEs without Python, secure vault,
real reboot/logon, tray, offline logon recovery, relocation, uninstall and remote read-only
MCP calls. No such native or remote checks ran here. See WINDOWS_SMOKE_TEST.md.
