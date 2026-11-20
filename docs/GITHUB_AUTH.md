> Current desktop login: enter a PAT in the GUI. GitHub CLI reuses the OS-vault token in its child environment; a separate `gh auth login` is not required. Older independent CLI examples below are optional.

# GitHub authentication and identity

1. In GitHub Settings → Developer settings, create a fine-grained PAT scoped to the repositories you will allowlist. Contents read is sufficient for read operations; publication needs Contents write and Pull requests write. Organization policies may require approval. No Administration permission is requested by the application.
2. Run `github-ai-mcp login` or GUI GitHub login. A hidden prompt stores the PAT in the OS keyring. On Windows, use Windows Credential Manager. If the backend is unavailable or plaintext, the operation fails closed. Avoid third-party plaintext keyring backends.
3. Install GitHub CLI and run `gh auth login`, GitHub.com, HTTPS, under the same account. This supplies HTTPS Git credentials for private clone/fetch/push. The fixed Git helper is `gh auth git-credential`; no token appears in a remote URL.
4. `doctor` verifies API `/user` when a PAT exists. Push checks that `gh api user --jq .login` equals the REST actor. Author identity is separately configured per owned clone. Do not confuse actor, author, committer or AI assistance.
5. Author email is explicitly configured (there is no default), with explicit `identity_authorized` required. The program never changes global Git identity. Contributions diagnostics attempt `/user/emails`; a permitted verified email match is `verified`, inaccessible email scope is `unknown`, no match is `unverified`.
6. Logout removes only this application's PAT. Run `gh auth logout` separately for Git transport. Revoke PATs at GitHub Settings to invalidate them remotely.

Fine-grained token expiry, scopes and repository availability are enforced by GitHub; this GUI does not list every expiry/scope or implement interactive GitHub App installation. GitHub App credentials, refresh and bot attribution are not implemented. OAuth for MCP clients is independent of GitHub authentication and also not provided for public deployment.

The config example intentionally leaves identity authorization false, checks untrusted and the repository map empty. Editing an allowlist is a local administrative action, not consent inferred from a model request.

Primary reference: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens
