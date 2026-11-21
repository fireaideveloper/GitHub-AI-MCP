# Native Windows acceptance — NOT RUN in this delivery

Current environment is Linux. Source tests/offscreen captures are separate evidence and cannot satisfy native acceptance. Native CI has not been launched. Use a disposable Windows account with no existing application credentials or repositories. Record each result as PASS/FAIL/NOT RUN, command/procedure, exact OS/build, observation, evidence path, limitations and reviewer. Leave it NOT RUN until executed; checkbox completion alone is insufficient.

Automated command after bundle build:

```powershell
& .venv/Scripts/python.exe scripts/windows_smoke.py --bundle dist --output "$env:TEMP/GitHub-AI-MCP-smoke.json"
```

It copies the real runtime into a Cyrillic/spaces directory, uses independent config/data, refuses existing GitHub/MCP credentials, creates only a disposable MCP vault secret and removes its own credential after testing. It uses same real packaged EXE in each mode, not Python replacements. HTTP lifecycle uses the production controller/Windows Job Objects. GUI termination is limited to its acceptance-owned process with autostart disabled. No live GitHub or tunnel authorization is attempted.

| Case / procedure | Required observation / evidence | Delivery result / limitation |
|---|---|---|
| Packaged raw stdio initialize, tools/list, health call | All stdout JSON-RPC only; 26 tools; structured READ_ONLY response; clean exit, WINDOWS_EVIDENCE.json | NOT RUN; same wire driver tested against Linux source |
| Packaged doctor from unrelated Unicode directory | Valid JSON; READ_ONLY; no prompts | NOT RUN |
| Packaged HTTP unauthenticated health/shutdown; authenticated identity | 401 without token; correct owned PID/fingerprint; bearer without private nonce cannot stop | NOT RUN; source HTTP tests pass |
| HTTP restart, killed owned child, manual stop | Different PID, bounded recovery, port release, manual stop remains stopped | NOT RUN; source fixture lifecycle passes |
| Occupied unrelated port | Start refused; listener alive, never adopted/killed | NOT RUN natively; source socket test passes |
| Packaged GUI offscreen | Alive after startup, own config, native smoke JSON | NOT RUN; not proof of native tray/DPI |
| Clean Windows 10/11 x64, non-admin, Python/pip/uv absent | GUI and internal server modes work from Downloads and fresh directory; no persistent GUI console/UAC | NOT RUN; requires clean VM, not CI developer runner |
| Native GUI Start/Stop/Restart/Stop all, controller crash/exit | Owned MCP/tunnel trees closed by Job Object, graceful shutdown, bounded retries only | NOT RUN; provider tool is bundled; its account/profile must be authorized |
| Tunnel expiry/disconnect/authentication | Verify through actual supported provider capability; activity alone Unverified | NOT RUN; no live vendor session/API evidence |
| Setup missing Git/gh, unusable executables, vault failure | Clear localized statuses, official help, read-only explore; no plaintext fallback | NOT RUN natively; unit/offscreen checks exist |
| Optional PAT login/logout, actor match and token copy | Validated OS-vault credential, no logs/JSON/SQLite/argv leak, clipboard expiry | NOT RUN live; mocks only, needs authorization |
| Installer silent/non-admin install, selectable path and shortcuts | Per-user Apps & Features entry, Start Menu, optional desktop/startup default off | NOT RUN; disposable non-admin VM/manual procedure below |
| Active GUI and active stdio sidecar during update/uninstall | Refusal, manual graceful closure; no force kills or unsafe replacement | NOT RUN; runtime mutex/installer paths reviewed statically |
| Reinstall and uninstall with test state/credentials | Program files/shortcuts removed; byte-identical config/job fixtures, vault survives, repositories untouched | NOT RUN; preservation encoded, not native proof |
| Sign-in startup/reboot and tray | Normal GUI after login; no privileged daemon; Exit owns cleanup | NOT RUN |
| Keyboard only, resizing, 100/150/200% DPI, both locales/themes | Visible focus, no clipping, icon and dialogs consistent | NOT RUN; previous Linux offscreen theme captures only |
| About / Legal offline | MIT attribution, exact runtime notices/texts and unresolved checklist readable | Source discovery verified; native NOT RUN |
| One changed path per nonempty commit, approvals, identity, CHECK_FAILED | Existing isolated Git suite passes, no duplicate commits/source mutations/unapproved push | PASS on Linux source; native regressions NOT RUN |
| Hashes/signatures | Recomputed actual SHA-256; Valid with real certificate or NotSigned explicitly | Source archive hash PASS; Windows artifacts/signing NOT RUN |
| Exact DLL/module license/source/replacement audit | Corresponding sources/offer, required notices, actual replacement test, reviewer approval | REVIEW_REQUIRED; native inventory NOT RUN |

Disposable VM installer procedure: create test user-state files and record hashes; ensure no running app; run Setup `/CURRENTUSER /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /DIR="C:\Users\test\Downloads\Проверка приложения"`; inspect user uninstall registry/shortcuts; launch, exit, reinstall; repeat with GUI and sidecar active and verify refusal; run installed `unins000.exe` with the same silent switches; compare retained state and vault credential; inspect that unrelated repository fixtures are untouched. Do not run this against a personal installation. CI does not claim this non-admin VM procedure: hosted runners often have admin rights.

Evidence record template: `case, OS/build, command, observed, PASS|FAIL|NOT RUN, evidence file, limitation, date/reviewer`. Automated JSON records only completed checks; manual slots remain explicit. Live GitHub writes, tunnel authentication, signing and publishing require appropriate infrastructure and express authorization; none occurred here.
