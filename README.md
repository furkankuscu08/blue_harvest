# Mortgage pricing exception requests

A small internal service: a relationship manager requests a rate discount for a mortgage application, a reviewer approves or declines it, and the mortgage process reads the approved discount.

Work in progress. This README is completed at the end of the work.

## Run it

Requires Docker.

```bash
docker compose up --build
```

Then open http://localhost:8000/health. If port 8000 is taken, run with `APP_PORT=8001 docker compose up --build`.

## Develop

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv venv --python 3.12 && source .venv/bin/activate
uv pip install -r requirements-dev.txt
pytest
```

More commands are in [AGENTS.md](AGENTS.md#commands). Design documents are in [docs/](docs/).
