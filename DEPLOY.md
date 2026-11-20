# Deploy to Render (web + API together)

1. Upload the contents of this folder to a **private GitHub repository** (Dockerfile and render.yaml must be at repository root).
2. On Render, select **New > Blueprint**, connect your GitHub repository and deploy using `render.yaml`. If Blueprint/free plan is unavailable, create a Docker Web Service from the same repository instead.
3. Open the HTTPS URL provided by Render. The web UI is served at `/` and the API at `/api/...` from the same origin. No local HTML files and no separate frontend hosting.
4. Check `/api/health`, then try a small scan at `/api/opportunities?universe_limit=10` before running a full scan.

## Important caveats
- Hosting provider availability, free-tier limits, and Binance access depend on provider, location and current policies. Free instances may sleep, have cold starts, or time out on long scans.
- A full scan can take minutes and may exceed provider request limits or Binance rate limits. This prototype has no background queue.
- Some cloud-host IP addresses are blocked by Binance; in that case choose a compliant supported host/region, not a bypass.
- No Binance keys or trading execution. Signals are heuristic and **do not** account for trading fees, spread, slippage, or funding.
- Never treat a 100-point score as a win probability. Test before risking money.
