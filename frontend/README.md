# Omniscient — frontend

React + TypeScript + Vite, mobile-first. See the [root README](../README.md) and [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) for the full picture.

## Development

```bash
npm install
echo "VITE_API_URL=http://localhost:8000" > .env
npm run dev
```

## Scripts

- `npm run dev` — start the Vite dev server
- `npm run build` — type-check (`tsc -b`) and produce a production build in `dist/`
- `npm test` — run the Vitest component/unit test suite
- `npm run lint` — run oxlint
- `npm run preview` — preview the production build locally

## Structure

- `src/pages/` — route-level screens (Home/chat, Housing, Academics, Past Papers, Complaints, auth, profile)
- `src/components/` — `layout/` (app shell, sidebar, top bar, bottom nav), `chat/` (composer, message list, live execution trace/activity panel), and one folder per domain (`housing/`, `academics/`, `pastpapers/`, `complaints/`)
- `src/api/client.ts` — typed REST client + the SSE consumer for `/api/chat`
- `src/hooks/useChatStream.ts` — chat + streaming trace state
- `src/context/AuthContext.tsx` — JWT auth state, backed by `localStorage`
- `src/styles/tokens.css` — design tokens (brand color, spacing, radius, shadows, type scale)
