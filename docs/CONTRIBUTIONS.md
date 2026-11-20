# Honest GitHub Contributions diagnostics

Author email must be explicitly configured; `author@example.invalid` is only a documentation example; actual account association must be checked, never assumed. The application distinguishes locally created commits, confirmed pushed commits, PR URL and observed profile contribution count. The last is always null here because profile counts are not queried or measured.

Diagnostic results: `likely`, `not_eligible`, `unknown`, with `guaranteed: false`. Local repositories return unknown. A fork or a feature branch returns not_eligible for current commit eligibility. A standalone default/gh-pages branch with verified email and push participation may be likely; this remains subject to GitHub's full criteria and processing.

Official criteria include an account-linked commit email, standalone rather than fork repository, default or gh-pages branch, and a qualifying relationship with the repository. Private contribution visibility and processing delays matter. Feature branch publication itself does not guarantee profile activity. Squash merges create a different final SHA/history; a history-preserving merge can retain commits only when repository rules permit it. Do not bypass reviews or rules for statistics.

## FAQ / Частые вопросы

- **Private repository / приватный репозиторий:** profile visibility settings can hide details; the application never makes it public.
- **Feature branch / feature-ветка:** commits generally need to reach a qualifying branch; opening a PR is distinct activity.
- **Fork:** standalone repository requirement applies to commit contributions.
- **Email:** if verified association cannot be read, confirm it in your GitHub email settings. Never impersonate another author.
- **Signed commits:** repository signature requirements are separate from contribution attribution; this release blocks required-signature publication.
- **Delay:** allow GitHub time to process activity; the app does not guarantee a deadline or count.

No empty commits, timestamp manipulation, artificial repetition or fabricated activity are supported.

Official sources checked during implementation (2026-10-09):
- https://docs.github.com/en/account-and-profile/reference/profile-contributions-reference
- https://docs.github.com/en/account-and-profile/how-tos/contribution-settings/troubleshooting-missing-contributions
- https://docs.github.com/en/account-and-profile/how-tos/email-preferences/setting-your-commit-email-address
