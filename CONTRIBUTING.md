# Contributing

Thanks for your interest in contributing to options-skill-pack! All contributions are welcome — bug fixes, new skills, web app features, and docs improvements.

## Getting started

1. Fork the repo and clone your fork
2. Install dependencies:
   ```bash
   pip install -r app/requirements.txt
   ```
3. Run the web app locally:
   ```bash
   export ANTHROPIC_API_KEY=your-key
   python3 -m uvicorn app.main:app --reload
   ```

## Making changes

1. Create a branch from `main`:
   ```bash
   git checkout -b your-branch-name
   ```
2. Make your changes
3. Test manually — run the web app and verify your changes work end-to-end
4. Commit with a clear message describing what and why

## Pull requests

- Keep PRs focused — one feature or fix per PR
- Describe what the PR does and why in the description
- Include steps to test your changes
- If adding a new skill, include eval test cases (see existing skills for the pattern)

## Adding a new skill

Each skill lives in `.claude/local-marketplace/plugins/<skill-name>/skills/<skill-name>/` and needs:

1. **`prompt.md`** — Skill prompt with trigger description and instructions
2. **Python script(s)** — Fetch data and compute results (use `yfinance`, keep `shell=False`)
3. **`eval/`** — At least 3 test cases for benchmarking

Follow the existing skills as examples. Key conventions:
- Validate ticker format (1–5 uppercase letters) before any API calls
- Use `subprocess` with `shell=False` — never pass user input to a shell
- Return structured JSON from scripts
- Keep the skill prompt focused on when to trigger and how to interpret output

If adding a skill to the web app, also update:
- `app/tools.py` — Add tool definition and script mapping
- `app/prompts.py` — Add skill guidance for result interpretation

## Security

- Never commit API keys or credentials
- Use `shell=False` for all subprocess calls
- Validate and sanitize user inputs
- See the Security notes section in README for full guidelines

## Code of conduct

This project follows the [Contributor Covenant](https://www.contributor-covenant.org/version/2/1/code_of_conduct/) code of conduct. Please be respectful and constructive in all interactions.

## Questions?

Open an issue if something is unclear — happy to help.
