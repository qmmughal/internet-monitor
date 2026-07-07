# Security Policy

## Supported Versions

We actively maintain the following versions:

| Version | Supported |
|---------|-----------|
| 1.x     | ✅ Yes    |
| < 1.0   | ❌ No     |

## Reporting a Vulnerability

**Please do NOT open a public GitHub issue for security vulnerabilities.**

Instead, please report security vulnerabilities via one of these methods:

1. **GitHub Security Advisories** (preferred):
   [Report a Vulnerability](https://github.com/qmmughal/wifi-monitor/security/advisories/new)

2. **Email**: security@qmmughal.example.com
   - Subject: `[SECURITY] WiFi Monitor - Brief Description`
   - Include: steps to reproduce, impact assessment, and suggested fix if known

### What to include

- Type of vulnerability (XSS, data exposure, dependency issue, etc.)
- Steps to reproduce
- Affected version(s)
- Potential impact
- Suggested mitigation or fix

### What to expect

- **24 hours**: Initial acknowledgment
- **72 hours**: Assessment and severity classification
- **7 days**: Patch development begins
- **14 days**: Patch released (if confirmed critical)

We follow [responsible disclosure](https://en.wikipedia.org/wiki/Responsible_disclosure) and will credit reporters in release notes unless they prefer anonymity.

## Scope

WiFi Monitor is a **client-side web application** that:
- Runs entirely in the browser
- Does not transmit data to external servers
- Stores data only in `localStorage`

Out-of-scope for security reports:
- Theoretical attacks requiring physical access to the device
- Attacks on third-party dependencies with no exploit path
- Social engineering or phishing
