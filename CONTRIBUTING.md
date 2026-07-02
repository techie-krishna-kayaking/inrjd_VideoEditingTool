# Contributing

Thank you for contributing.

## Development Setup
1. Create a Python 3.12 environment.
2. Install dependencies:
   - pip install -r requirements.txt
3. Run checks:
   - PYTHONPATH=. python3 -m pytest -q
   - python3 -m ruff check src tests

## Branching
- Use short feature branches from main.
- Keep pull requests focused and small.

## Pull Request Checklist
- Tests updated or added.
- No dead code or unused imports.
- CLI help text updated if behavior changed.
- README and config documentation updated when needed.
- Render behavior validated with dry-run for new workflows.

## Coding Standards
- Keep modules single-purpose.
- Favor small pure helpers over monolithic functions.
- Avoid hardcoded paths and magic numbers.
- Keep ffmpeg options centralized in rendering modules.
