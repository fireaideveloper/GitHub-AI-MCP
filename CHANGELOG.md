# Проверка и исправления запуска — 2026-10-13

Локальное исправление YAML без ключа/сети, редактируемая команда stdio, сохранение пользовательской команды, проверка введённого ключа, безопасные коды диагностики, обновление настроек служб, очистка неудачно запущенных процессов и регрессии. Подробности и ограничения: [AUDIT_RU.md](AUDIT_RU.md). Windows EXE в этой поставке не собран.

# Single-executable refactor

- Replace dual onedir GUI/server packaging and automatic release archives with
  one native Windows onefile/windowed build, isolated temporary work and atomic output.
- Dispatch internal HTTP/stdio workers through the same EXE before importing Qt;
  restore inherited Windows pipes without creating a console.
- Embed explicitly supplied PortableGit, gh and provider tunnel client; fail the
  build if required vendor inputs are absent. Vendor binaries were not supplied
  and are not included in this source delivery.
- Resolve read-only resources inside the extraction root; preserve per-user
  state, vault credentials, process ownership, bounded restart and opt-in startup.
- Avoid persisting temporary tunnel executable paths between launches.
- Remove old launchers, dual-server entrypoint, installer, duplicate Windows setup
  guide, generated inventories/reports, old evidence and unreferenced screenshots.
- Retain source, API/security docs, examples, tests, lock, licenses, optional signing
  and explicitly invoked source/archive/hash utilities.

Validation in this Linux delivery: **165 tests passed**, Ruff passed, 35 source
files passed mypy, compileall and the offline local Git demo passed. Mypy's optional
psutil affinity discovery crashes in this container (PID lookup); the check was
run with that optional discovery disabled, without changing application sources.
Windows EXE compilation and native inherited-pipe/tray/Job Object/logon behavior,
vendor execution, live GitHub/tunnel and clean-machine portability were not tested.
See docs/RELEASE_BUILD.md for exact build inputs and commands.

# Changelog

## 1.0.1 — 2026-10-12

- Opt-in per-user Windows logon startup, validation/repair/removal, unified installer registration.
- OS-vault tunnel runtime credentials and scoped environment injection.
- Safe YAML editor, backed-up stdio path repair, installed-client doctor validation.
- Unmanaged external process detection, conservative health evidence and bounded recovery.
- Safe diagnostics, service/tray preferences, notifications and RU/EN setup guides.
- Source tests verified on Linux; native Windows and real remote acceptance pending.

## 1.0.0

Original source release; retained historical audits/evidence describe that release.
