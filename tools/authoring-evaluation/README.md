# Dataviz Authoring Evaluation

Repository-only maintainer tool for paired Dataviz/standalone-HTML authoring trials. It is intentionally excluded from the `ai-dataviz` wheel, sdist, pip ZIP, product documentation, and `dataviz --help`.

```bash
uv run --project tools/authoring-evaluation --no-editable -- dataviz-authoring-eval --help
```

It records only measurements reported by the actual client. It never estimates tokens or substitutes repository tests for a real paired trial.
