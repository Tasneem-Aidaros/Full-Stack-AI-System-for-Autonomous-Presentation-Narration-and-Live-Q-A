# AI Presenter — Console (Frontend)

A React control console for running your AI Presenter backend live: upload a
deck, start/stop the presentation, watch live captions, adjust narration
speed, and field audience questions (typed or spoken).

## Setup

```
cd frontend
npm install
npm run dev
```

This starts the dev server at **http://localhost:5173**.

Make sure your FastAPI backend is running separately at
**http://127.0.0.1:8000** (`uvicorn main:app --reload`, as usual). If your
backend runs somewhere else, change `API_BASE` at the top of
`src/api.js`.

## What's in here

- `src/api.js` — every backend call in one place (upload, start/stop,
  subtitle polling, speed, ask, chat history).
- `src/App.jsx` — top-level state + polling loops (status every 1.2s,
  subtitle every 400ms, chat history every 1.8s while a deck is loaded).
- `src/components/` — one file per panel: status bar, upload, the live
  caption ("teleprompter") panel, transport (start/stop), tempo (speed),
  and intercom (typed Q&A + log).
- `src/index.css` — the whole design system (colors, type, panels) as
  plain CSS custom properties — no framework, so every value is easy to
  find and tweak by hand.

## A note on how I verified this

I don't have network access to npm's registry in the environment I built
this in, so I couldn't actually run `npm install` / `npm run dev` here.
What I *did* verify: every `.jsx` file individually parses and transforms
cleanly, and a full bundle from `main.jsx` through every component and
`api.js` resolves without errors (using a bundler already available in my
environment, pointed at a real React install). That catches syntax errors,
typos in imports/exports, and undefined references — the most common
things that break on a first run — but it is **not** the same as actually
opening this in a browser. Please do a real `npm install && npm run dev`
and click through it before assuming everything renders/behaves exactly
as intended, especially the polling timing and the CORS handshake against
your live backend.

## Design notes

The look is a broadcast/stage-manager control-room aesthetic — a
charcoal console background, amber for "cued," green for "on air," a
monospace teleprompter panel for the live caption. That's meant to fit
what this actually is: an operator's console for running a live event,
not a marketing page. If you want a different direction entirely, the
whole palette and type scale lives at the top of `src/index.css` as
named custom properties, so it's a small, contained edit rather than a
rewrite.
