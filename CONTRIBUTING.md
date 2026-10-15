# Contributing to Internet Monitor

Thank you for investing your time in contributing to Internet Monitor! 🎉

This document outlines the contribution process, coding standards, and community guidelines.

## 📋 Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [How to Contribute](#how-to-contribute)
- [Development Setup](#development-setup)
- [Coding Standards](#coding-standards)
- [Commit Message Format](#commit-message-format)
- [Pull Request Process](#pull-request-process)
- [Issue Reporting](#issue-reporting)

---

## Code of Conduct

This project follows our [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold these standards.

---

## Getting Started

1. **Fork** the repository on GitHub
2. **Clone** your fork: `git clone https://github.com/YOUR_USERNAME/internet-monitor.git`
3. **Create a branch**: `git checkout -b type/short-description`
4. **Make changes**, then commit with a conventional commit message
5. **Push** and open a Pull Request

---

## How to Contribute

### 🐛 Bug Reports
- Use the [Bug Report template](.github/ISSUE_TEMPLATE/bug_report.md)
- Include steps to reproduce, expected vs actual behavior, and browser/OS details
- Attach screenshots or recordings if possible

### 💡 Feature Requests
- Use the [Feature Request template](.github/ISSUE_TEMPLATE/feature_request.md)
- Describe the problem it solves, not just the solution
- Check existing issues to avoid duplicates

### 🔧 Code Contributions
- Look for issues labeled `good first issue` or `help wanted`
- Comment on an issue before starting work on it (to avoid duplication)
- Keep PRs focused — one feature or bug fix per PR

### 📚 Documentation
- Fix typos, improve explanations, add examples
- Documentation PRs are always welcome!

---

## Development Setup

### Prerequisites
- Python 3.9+ (core, CLI, local API)
- Optional: Node.js 18+ for the dashboard tests
- Any modern browser for the dashboard

### Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### Running

```bash
internet-monitor serve               # dashboard with real data: http://127.0.0.1:8765
internet-monitor serve --demo        # dashboard with labelled simulated data
internet-monitor diagnose            # troubleshooter
```

### Running Tests

```bash
python -m pytest -q              # Python: parsers, diagnostics, CLI, server
npm test                         # Dashboard: loads the shipped src/js files
```

Tests never need Wi-Fi hardware or network access. When you add support for new OS output,
add a sample to `tests/python/fixtures.py` (replace real SSIDs/MACs with `02:…` addresses).

### Data integrity rules for contributions

- Never fall back to invented values. Return `mode="unavailable"` with an `error` (and a `hint`
  when the user can fix it).
- Label derived values `estimated`; label demo data `simulated`.
- Treat SSIDs and all OS output as untrusted: escape before rendering, never pass to a shell.

---

## Coding Standards

### JavaScript

- Use `'use strict'` at the top of every module
- Prefer `const` and `let`, avoid `var`
- Use descriptive variable names
- Add JSDoc comments for public functions
- Keep functions small (< 40 lines ideally)
- Handle errors gracefully with try/catch

```javascript
// ✅ Good
/**
 * Convert dBm signal strength to quality percentage.
 * @param {number} dbm - Signal in dBm (typically -30 to -100)
 * @returns {number} Quality percentage 0–100
 */
function dbmToPercent(dbm) {
  if (dbm >= -50) return 100;
  if (dbm <= -100) return 0;
  return Math.round(((dbm + 100) / 50) * 100);
}

// ❌ Bad
function calc(x) { return x > -50 ? 100 : x < -100 ? 0 : Math.round(((x+100)/50)*100); }
```

### CSS

- Use CSS custom properties (variables) for all colors, spacing, and typography
- Follow BEM-like naming: `.component-element--modifier`
- Prefer `flex` and `grid` layouts
- Always include dark mode styles via `[data-theme="dark"]`
- Mobile-first responsive design

### HTML

- Use semantic elements (`<nav>`, `<main>`, `<section>`, `<header>`, etc.)
- Every interactive element must have a descriptive `id` attribute
- Add ARIA labels for accessibility
- Include meta description and title tags

### Python (CLI)

- Follow PEP 8 style guide
- Use type hints
- Add docstrings to all functions
- Handle `KeyboardInterrupt` gracefully

---

## Commit Message Format

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

### Types

| Type | Description |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation changes |
| `style` | Formatting, no logic change |
| `refactor` | Code restructuring |
| `perf` | Performance improvements |
| `test` | Tests only |
| `chore` | Build, CI, dependencies |

### Examples

```
feat(scanner): add 6 GHz band detection
fix(charts): resolve gauge rendering on mobile Safari
docs(readme): add Electron integration guide
perf(logger): debounce localStorage writes
```

---

## Pull Request Process

1. **Ensure your branch is up to date** with `main`:
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Run tests** before submitting: `npm test`

3. **Fill out the PR template** completely — describe what, why, and how

4. **Request review** from at least one maintainer

5. **Address review feedback** promptly (within 7 days)

6. **Squash commits** if requested before merge

### PR Checklist

- [ ] Tested in Chrome and Firefox
- [ ] Dark mode and light mode tested
- [ ] Mobile/responsive layout tested
- [ ] No console errors
- [ ] Code follows the style guide
- [ ] Documentation updated if needed
- [ ] Tests pass

---

## Issue Reporting

### Before opening an issue:
- Search existing [issues](https://github.com/qmmughal/internet-monitor/issues)
- Check the [usage guide](docs/USAGE.md) and [troubleshooting](docs/TROUBLESHOOTING.md)
- Try the latest `main` branch

### Security issues:
Please do **not** open a public issue for security vulnerabilities. Follow the [Security Policy](SECURITY.md).

---

## Recognition

All contributors are recognized in our [CHANGELOG.md](CHANGELOG.md) and on the GitHub contributors page. Thank you for making Internet Monitor better! 🙏
