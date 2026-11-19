> Current desktop upgrade coverage and outstanding Windows acceptance: [UPGRADE_REPORT](UPGRADE_REPORT.md) and [WINDOWS_SMOKE_TEST](WINDOWS_SMOKE_TEST.md). Historical core implementation matrix follows; old launcher limitations are superseded by those reports.

# Requirement coverage and remaining work

This is an explicit implementation status matrix, not a claim that every acceptance criterion has been met. The full supplied [specification](SPECIFICATION.md) is retained. Executed results are in [VERIFICATION_REPORT.md](VERIFICATION_REPORT.md).

| Specification area | Status | Implementation / evidence / limitation |
|---|---|---|
| Official MCP SDK + current transports | Implemented offline | SDK 2.3.0 pinned, stdio and loopback Streamable HTTP; wire/ASGI tests |
| Required compact tools/resources | Implemented, schema partial | All 26 listed tools plus 2 resources; typed input signatures and envelope; per-tool data output types not fully specialized |
| Repository allowlist and fixed startup mode | Implemented | Strict local config; no mutation/approval/config tools exposed |
| Clean workspace/user changes preservation | Implemented | Independent clones; dirty source and staged changes regression |
| One path per nonempty commit | Implemented | 1/5/17 path fixtures; 12 modified + 5 added = 17; repeated edits collapse |
| Deletions and strict renames | Implemented | Two distinct path commits for strict rename |
| Approved atomic rename exceptions | Not implemented | Cannot be enabled; always strict semantics |
| Case-only rename on Windows | Not implemented | Case-colliding trees fail closed; dedicated workflow needed |
| UTF-8, CRLF/LF and executable modes | Implemented offline | Unicode/emoji/CRLF/LF/mode fixtures; native Windows handling untested |
| Explicit binary writes | Implemented offline | Base64 policy opt-in; tested binary blob |
| Symlink/gitlink/submodule writes | Deliberately blocked | No dedicated opt-in workflow |
| Git LFS handling | Partial | Pointer writes blocked; no complete LFS workflow or object upload |
| Contextual patch and stale content checks | Implemented | Exact unique text replacement + SHA-256; no unified-diff parser |
| Snapshot preview and human approval | Implemented | Fingerprint binds base/tree/paths/messages/author; local GUI/CLI only |
| Narrow expiring automation grants | Implemented | Repo/ai-prefix/actions/file/byte/expiry policy; exact per-job grants |
| Secrets, paths and operational logs | Implemented, heuristic | Sensitive paths denied, credential indicators, bounded redacted previews; not an exhaustive secret detector |
| Host execution authorization | Implemented | Locally configured array commands + explicit trusted execution |
| Container/OS sandbox runners | Not implemented | Host execution is clearly warned and opt-in |
| SQLite, crash recovery, idempotency | Implemented offline | Version-1 schema guard, WAL/FULL, reconcile after commit 7 of 10, key conflict checks |
| Parallel jobs and stale locks | Partial | Service-wide kernel lock serializes every operation; OS releases on crash. Parallel throughput not implemented |
| Cancellation and retention | Partial | Cancel retains source/audit; manual audit pruning; no automatic workspace TTL cleanup |
| Full named state machine | Partial | Main durable states implemented; many errors use typed codes instead of separate persisted error states |
| Incomplete clone/create recovery | Not implemented | Retained RECOVERY_REQUIRED job for diagnostics; cancel/create fresh job |
| GitHub REST integration | Implemented, mocked tests | Metadata/rules/email/PR/CI; canonical host; bounded GET retries; no live credentials used |
| Secure normal Git push | Implemented offline | Local bare remotes tested; real HTTPS requires gh; actor equality/protection checks implemented but not live-tested |
| Lost push acknowledgment and divergence | Implemented offline | Reconciled remote SHA; no force; advanced target/base tests |
| PR idempotency | Implemented, bounded | GET reconciliation plus durable returned URL; REST fixture tested; first API page only |
| Rulesets, branch protection, signed commits | Partial | Read default metadata/target rules, enforce remote response; required signatures stop. No signing setup/key UI |
| Required final tests before real publish | Implemented | Real GitHub push blocked without configured required checks; failed/mutating checks tested |
| Global Git config/forged dates/activity | Forbidden | Global/system config and Git env ignored; no empty commits or artificial dates |
| Preferred author email | Implemented | explicit author email required, explicit local identity authorization, no global changes |
| Email verification | Implemented, mocked | /user/emails verified/unknown/unverified; no real account association verified here |
| Contribution diagnostics | Implemented, conservative | Separate local/push/PR outcomes, likely/not_eligible/unknown, observed count null |
| PAT in OS vault | Implemented, platform untested | Only recognized OS-backed keyring backends; plaintext rejection test; native vault round-trip untested |
| GitHub App/installation auth | Not implemented | No refresh/install/bot account management |
| Public remote OAuth/TLS hosting | Not implemented | Internet listener unavailable; local authenticated endpoint only |
| ChatGPT connection | Documented, untested | Official private Secure MCP Tunnel stdio route; permission/runtime prerequisites; no tunnel executed |
| Windows one-click scripts | Implemented, statically reviewed | Relative paths, UTF-8 BOM, checks/install/menu/human mode-3 confirmation; no Windows execution |
| GUI and CLI backend sharing | Implemented offline | Eight GUI pages, real operation buttons, background tasks, CLI commands; actual Qt render test/capture |
| Full GUI localization and polish | Partial | Russian/English navigation and themes; technical labels/dialogs remain mixed/English; no dedicated CI chart or expiry/scopes UI |
| Dependency lock/build | Implemented on Linux | Universal uv.lock + frozen install; source/wheel build; clean extract tested |
| Windows EXE packaging | Recipe only | PyInstaller script supplied; no EXE or native packaged test |
| Comprehensive bilingual docs | Implemented | English primary README, full Russian installation/use/recovery guide, linked technical docs and prompts |
| Read cache/freshness | Implemented, basic | Fetch allowlisted origin before cache reads, current SHA returned; no ETag/content-addressed cache optimization |
| Live user repository changes | Not performed | No credentials/account operations/user-repository pushes or PRs |

## Production readiness gate

Before relying on this release for production repositories: execute the native Windows installation/GUI/keyring/packaging suite; run authenticated GitHub tests in a separately authorized disposable repository; review host execution and token policies; resolve required LFS/signing/case-rename/public-hosting needs; independently review security. The source is runnable and tested but these unfinished requirements prevent a claim of full production acceptance.

## Русский итог

Основной Git/MCP workflow реализован и проверен офлайн, включая 17 отдельных коммитов и восстановление после сбоя. Нельзя честно заявить полное выполнение ТЗ production-ready: не проведены native Windows и live GitHub проверки, отсутствуют public OAuth, GitHub App, полный LFS/signing workflow и некоторые расширенные элементы GUI. Все эти границы указаны явно; реальные репозитории пользователя не менялись.
