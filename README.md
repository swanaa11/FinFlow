# FinFlow — Automated Personal Finance Intelligence Platform

> A local-first, ₹0-cost data platform that turns raw bank / credit-card / UPI
> statement exports into clean, categorized, deduplicated financial insights —
> with a dashboard, daily Telegram summaries, anomaly detection and budget alerts.

## 🌐 Live demo

A static demo dashboard (built **only** from the synthetic sample corpus) is
deployed on Vercel's free Hobby plan — deployment guide:
[`docs/DEPLOY_VERCEL.md`](docs/DEPLOY_VERCEL.md). Regenerate it locally with
`finflow export-demo` after refreshing the data.

**Status: under active construction.** This README is a stub during Phase-5
implementation; the full product README (architecture diagram, screenshots,
design decisions) lands in Milestone 16. See [`docs/PLAN.md`](docs/PLAN.md) for
the complete approved architecture and implementation plan.

## Quick start (developer)

```bash
pip install -e ".[dev]"
make demo-data     # generate 12 months of synthetic statements into data/sample/
make ci            # lint + typecheck + tests
```

All data shipped in this repository is **synthetically generated**. No real
financial data is ever committed. The platform never connects to banks — you
manually export statements and drop files into `data/incoming/`.

## Documentation

- [Implementation plan](docs/PLAN.md)
- [Architecture decision records](docs/adr/)
- [Implementation log](docs/IMPLEMENTATION_LOG.md)

## License

[MIT](LICENSE)
