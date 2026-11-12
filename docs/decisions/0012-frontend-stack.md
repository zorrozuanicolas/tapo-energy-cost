# 0012. Frontend stack

- Status: accepted
- Date: 2026-11-12

## Context

The backend is complete: it serves history over REST ([0007](0007-rest-api.md)) and live readings over SSE
([0009](0009-live-stream.md)). The next step is a web app that shows them. This decision is about the tools
and the conventions of that app, before any screen exists. The screens come in the next milestone.

The same constraints as the backend apply: a small project that one person has to understand and explain, with
CI that rejects a broken change, and the same strictness we use in Python (mypy strict, Ruff).

## Decision

We will build the frontend in `frontend/` with this stack.

- **Vite, React 19 and TypeScript.** Vite gives a fast dev server and a production build with little
  configuration. TypeScript runs in strict mode with `noUncheckedIndexedAccess`, so `array[i]` is typed
  `T | undefined` and a missing element is handled in the code, not discovered at runtime.
- **Tailwind CSS 4**, through its Vite plugin. It needs no config file. Only the classes the code uses end up
  in the CSS.
- **npm and Node 22.** Node 22 is pinned in `frontend/.nvmrc`, which CI also reads, so the version lives in one
  place. `package-lock.json` is committed and CI installs with `npm ci`, which fails if the lockfile and
  `package.json` disagree.
- **Vitest** for tests, in the `node` environment for now. The logic written so far (API client, dates,
  formatting) does not touch the DOM. jsdom and Testing Library arrive with the components.
- **Biome** for lint, formatting and import order, with exact version pinning. One tool and one config file
  (`biome.json`), with the same settings as the editor config (two spaces, LF) and a 120-column limit, like
  Ruff on the backend. `npm run check` is the read-only command CI runs.
- **Hand-written API types.** `src/types.ts` mirrors `backend/app/schemas.py` and says so in its header. When
  one changes, the other changes in the same commit.
- **A dev proxy for `/api`.** The Vite dev server forwards `/api` to the backend on port 8000, so the browser
  talks to one origin and no CORS setup is needed in development. When the API is on another origin,
  `VITE_API_URL` holds its address.
- **Dates are civil-date strings handled in UTC.** `period.ts` works with `YYYY-MM-DD` strings and does its
  arithmetic in UTC, so the result never depends on the time zone of the browser. "Today" is taken with
  `Intl` in the backend's time zone, which the API reports in every response.
- **Errors keep the backend's explanation.** The API client throws `ApiError` with the status and the `detail`
  that FastAPI sends, so a screen can say why a request was refused, such as a range that is too large.

## Alternatives considered

- **ESLint and Prettier**: the usual choice, and the first plan. `typescript-eslint` does not support
  TypeScript 7 yet: its newest release accepts TypeScript below 6.1, and installing it fails. We could
  downgrade TypeScript, or install with `--legacy-peer-deps` and accept an untested combination that every
  install and CI run would need. Neither is a good base. Biome has no such dependency and replaces two tools
  with one.
- **Formatting only, no linter**: it would work, but lint is cheap to keep from the start.
- **pnpm or yarn**: faster installs, but one more tool to install for no gain at this size. npm ships with Node.
- **Types generated from the OpenAPI schema** (`openapi-typescript`): the types could never drift. It adds a
  build step, and the schema describes `/api/live` as JSON when it is an event stream. Hand-written types are
  fewer than 80 lines.
- **Validating responses at runtime** (zod or similar): it would catch a response that does not match its type.
  It is more code and a dependency for a backend we control. It can be added later if the types prove
  unreliable.
- **A UI kit or chart library**: faster to start, but less to explain. The charts are drawn by hand in the next
  milestone, as the plan says.

## Consequences

- Every pull request runs `npm run check`, `npm test` and `npm run build` (which includes `tsc --noEmit`) in a
  CI job next to the backend one.
- Biome's recommended rules are less thorough than `typescript-eslint`'s type-aware ones. For instance, nothing
  flags a promise that is not awaited. Strict `tsc` covers much of the gap. We will revisit ESLint when
  `typescript-eslint` supports TypeScript 7.
- The types and the backend schemas can drift without any check noticing. The way out is generated types or
  runtime validation, as above, if it becomes a problem.
- Biome is pinned to an exact version, because lint rules and formatting can change between minor releases.
  Upgrading it is a deliberate commit.
- The dev proxy only exists in `npm run dev`. The production build needs a reverse proxy or `VITE_API_URL`,
  which the Docker milestone decides.
- The tests cover the pure logic. There is nothing yet that exercises a real browser or the real backend
  together.
