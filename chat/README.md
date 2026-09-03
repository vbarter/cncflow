# cncflow-chat

Read-only Pi agent behind `POST /api/v1/chat`. Jail cwd is `CHAT_JAIL` (`docs/knowledge-base`, `backend/cncflow_core`, `frontend/src`). Tools: `read`, `bash`, `ls`, `grep`. `write` / `edit` are not registered. Model: `TUZI_MODEL` default `gpt-4.1-mini` at `https://api.tu-zi.com/v1`.
