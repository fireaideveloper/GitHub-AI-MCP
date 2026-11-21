# Development

Install the frozen lock with gui/dev extras; run pytest, ruff and mypy. Keep business logic outside GUI handlers and transport wrappers. Every mutation must preserve the policy boundary and final-tree invariant. Use offline bare remotes and MockTransport; real GitHub tests require a dedicated repository and separately authorized credentials.

Never add tokens, fake commits, fabricated evidence, broad shell-command tools or global Git config changes. If a change affects executable code, add meaningful regression coverage for its behavior. Record actual results and limitations in the verification report. Keep English README primary with a Russian guide link.
