# Contributing

Issues and pull requests are welcome. This is a small, opinionated plugin, so please open an issue before a large change.

## Development setup

```bash
git clone https://github.com/abhishek085/jevcontrol-hermes
cd jevcontrol-hermes
python -m pip install pytest httpx
python -m pytest -q          # 38 tests, no Hermes install needed
```

The compressor tests need Hermes importable (they are skipped otherwise):

```bash
PYTHONPATH=/path/to/hermes-agent python -m pytest -q      # 43 tests
```

To try a change in your own Hermes, link the checkout as a user plugin:

```bash
ln -s "$PWD" ~/.hermes/plugins/jev-control
hermes plugins enable jev-control
hermes jev-control doctor
```

## Before you open a pull request

- `python -m pytest -q` passes.
- `hermes plugins validate .` (from a Hermes checkout: `.venv/bin/hermes plugins validate /path/to/jevcontrol-hermes`)
  passes, and a fresh `hermes plugins install` of your branch is not blocked by the install scan. Hermes' scanner
  flags words like "exfiltrate" and credential paths even in docs; build such strings from fragments in tests.
- New behaviour has a test. Features must **fail open**: a decision-model outage must never stop the agent.
- A new feature needs a labelled evaluation set written *before* looking at model output, and an honest result,
  including a negative one.
- Do not log prompts, tool arguments or conversation text unless `log_content` is on.

## Continuous integration

A ready-made GitHub Actions workflow is in [`ci/github-actions-tests.yml`](ci/github-actions-tests.yml). Copy it to
`.github/workflows/tests.yml` to enable it (pushing workflow files needs a token with the `workflow` scope).

## Principles

1. The decision model answers small, bounded, pick-one questions. It never writes the answer for the user.
2. Every feature is off by default and reversible by config.
3. Say what was measured, on what, and what was not tested.
