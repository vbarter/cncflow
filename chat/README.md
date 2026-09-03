# cncflow-chat

Read-only Pi agent behind `POST /api/v1/chat`. Jail cwd is `CHAT_JAIL` (`docs/knowledge-base`, `backend/cncflow_core`, `frontend/src`). The only registered tools are `read` and read-only `bash`; `write`, `edit`, and all other tools are disabled. Model: `TUZI_MODEL` default `gpt-4.1-mini` at `https://api.tu-zi.com/v1`.
