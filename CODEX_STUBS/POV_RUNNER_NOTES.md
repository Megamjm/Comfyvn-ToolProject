# POV Runner Scratchpad

- Use `from comfyvn.pov import POV_RUNNER` when prototyping filters.
- Example filter skeleton:

```python
def only_allow_cast(candidate, context):
    cast_ids = {member["id"] for member in context["scene"].get("cast", []) if isinstance(member, dict)}
    return candidate.get("id") in cast_ids

POV_RUNNER.register_filter("cast-only", only_allow_cast)
```

- Toggle tracing via `POV_RUNNER.candidates(scene, with_trace=True)` to inspect filter decisions.
- Remember to unregister experimental filters when running tests: `POV_RUNNER.unregister_filter("cast-only")`.
