# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

Monitor for TP-Link Tapo P110/P115 smart plugs, priced with UTE's *Plan Inteligente Hogares*
(Uruguay's three-band tariff). Stack: FastAPI + SQLite backend, React + Vite + Tailwind
frontend, Docker Compose. The project is being rebuilt step by step as a portfolio piece; see
`docs/decisions/` for the reasoning behind each design choice.

## How we work

- Explain a file's contents and purpose before creating it, then wait for the author's OK.
- Never commit, push, or change the GitHub repository without explicit confirmation in the chat.
- One milestone = one branch = one pull request. Merge with rebase-and-merge so small commits stay visible.
- Commits follow Conventional Commits. The body is optional: add one only when the *why* is not obvious
  from the subject and the diff.
- Commits are atomic: each one builds and passes tests on its own, and tests go in the same commit as
  the code they cover (or before it).
- Once lint and tests exist, run them and show the real output before asking for commit approval.
- Commits end with a `Co-Authored-By` trailer naming the Claude model that wrote them.
- Record significant design decisions as ADRs in `docs/decisions/`.

## Conventions

- Code, comments, commits and docs in English. UI text in Spanish.
- Secrets never go in the repo. `.env.example` holds placeholders only.

## Commands

Backend (run from `backend/`; uv is the package manager):

- `uv sync`: install dependencies from `uv.lock`
- `uv run pytest`: run the tests
- `uv run ruff check`: lint
- `uv run ruff format`: format (`--check` to only verify)
- `uv run mypy`: type check (strict)

Frontend (run from `frontend/`; npm is the package manager, Node 22):

- `npm ci`: install dependencies from `package-lock.json`
- `npm run dev`: dev server on port 5173, which forwards `/api` to the backend on port 8000
- `npm test`: run the tests
- `npm run check`: lint, format and import order (Biome); `npm run format` fixes them
- `npm run build`: type check (strict) and production build

Docker (run from the repository root):

- `docker compose up -d --build`: build and start the app at http://localhost:8080
- `docker compose ps` / `docker compose logs backend`: state and logs
- `docker compose down`: stop it (`data/` is kept)

Compose reads the root `.env`, not `backend/.env`. Before starting it, make sure that file does not point to
real plugs that something else is polling.
