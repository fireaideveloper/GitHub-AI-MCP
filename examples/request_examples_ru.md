# Practical AI prompts / Практические запросы

Use an allowlisted repository and the configured access mode. Replace owner/repo and IDs with real tool results. These prompts are examples, not authorization to a real repository.

| English | Русский |
|---|---|
| Show the project tree and explain its architecture; do not modify anything. | Покажи дерево и архитектуру проекта. Ничего не изменяй. |
| Locate a bug and propose declared paths/messages; do not publish. | Найди ошибку и предложи пути/сообщения. Не публикуй. |
| Fix four files in one job, preview them, and create one commit per genuinely changed path after local approval. | Исправь четыре файла одним заданием, покажи diff, после локального одобрения создай отдельные коммиты. |
| Add localization tests; run the configured checks and publish a PR only under the approved policy. | Добавь тесты локализации, выполни разрешённые проверки и публикуй PR только в рамках одобрения. |
| Compare the recorded base and remote heads; stop if either branch diverged. | Сравни базу и remote; при расхождении остановись. |
| Show the job report with real SHAs, confirmed URLs and CI outcomes. | Покажи отчёт с настоящими SHA, проверенными URL и результатами CI. |
| Diagnose contribution eligibility without promising a contribution count. | Объясни eligibility вкладов без обещания их количества. |
| Resume the interrupted job without duplicate commits or repeat pushes. | Продолжи прерванное задание без дублирования коммитов и push. |
| Cancel this job and keep its local audit report; don't undo published history. | Отмени задание, сохрани аудит, не переписывай опубликованную историю. |
| Run authorized security checks before publication; stop on secret indicators. | Перед публикацией выполни разрешённые проверки безопасности и остановись при секрете. |

Example for SherlockPC: “In the allowlisted fireaideveloper/SherlockPC repository, investigate Spanish punctuation rendering in READ_ONLY first. Create a declared localization/test plan, then an isolated LOCAL_REVIEW job. Read current checksums before edits. Show exact diffs for local approval, create one nonempty commit per changed path and report final-tree checks. Do not publish until I approve the exact snapshot in the local control UI and enable publishing policy.”
