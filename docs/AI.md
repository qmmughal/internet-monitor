# AI Explanations ("Wi-Fi copilot")

`internet-monitor ask "why are my video calls unstable?"` (and the **Explain** box on the dashboard)
turns the measurements into a plain-language answer with observations, possible causes and
suggested steps.

**AI is off by default.** Without it you still get an answer, assembled from the rule-based
diagnostics. With it, a model reads a summary of your measurements and answers free-form questions.

## What the model sees

Run `internet-monitor ask --preview "your question"` to print the exact text that would be sent.
It contains:

- the latest diagnostics report (findings and evidence),
- current Wi-Fi status and Wi-Fi generation,
- one-hour statistics, baseline comparison, recent roaming/disconnect events and active alerts
  (when asked through `serve`),
- the last speed test, if any,
- current download/upload rates of the primary interface and the names and byte counts of the five
  busiest apps in the last 5 minutes (no remote addresses or connection lists).

By default SSIDs, BSSIDs/MAC addresses, device names and private IP addresses are replaced with
placeholders such as `network-1`, `mac-2`, `lan-ip-1`. Public test endpoints (`1.1.1.1`, `8.8.8.8`)
are kept. Set `"send_identifiers": true` only if you accept sending the real values.

The model gets **no tools**: it cannot run commands, read files or change settings. Its answer is
validated against a fixed schema and shown as text; suggestions are never applied automatically.

## Safety measures

| Risk | Mitigation |
|---|---|
| Prompt injection through SSIDs/device names (anyone nearby can name a network "Ignore previous instructions…") | Data is redacted by default, control characters are stripped, strings are truncated, the data block is delimited and the system prompt says it is untrusted data |
| Invented conclusions | The prompt requires evidence for every observation, separates facts / hypotheses / recommendations, and tells the model that `simulated` data is not real and `unavailable` is unknown |
| Malformed or unsafe output | Strict schema validation; anything else falls back to the rule-based answer |
| Leaked credentials | API keys are read only from environment variables, never written to config or logs and never placed in the prompt |
| Provider outage, quota, refusal | The rule-based answer is returned with the reason |

## Enabling

Create `config.json` in the config directory (`%APPDATA%\internet-monitor` on Windows,
`~/.config/internet-monitor` elsewhere, or `$INTERNET_MONITOR_HOME`):

### Claude (Anthropic)

```bash
pip install "internet-monitor[ai]"          # official anthropic SDK (Python 3.10+)
export ANTHROPIC_API_KEY=...            # Windows: setx ANTHROPIC_API_KEY ...
```

```json
{ "ai": { "enabled": true, "provider": "anthropic", "model": "claude-opus-5-5" } }
```

Requests use structured JSON output. Server-side refusal fallbacks are enabled
(`fallbacks: "default"`), so a declined request is retried on a fallback model chosen by
Anthropic; if the chain still declines, you get the rule-based answer.

### Local or OpenAI-compatible models (Ollama, LM Studio, vLLM, hosted services)

```json
{
  "ai": {
    "enabled": true,
    "provider": "openai-compatible",
    "base_url": "http://localhost:11434/v1",
    "model": "llama3.1",
    "api_key_env": null
  }
}
```

A `localhost` base URL keeps everything on your machine. For hosted services set
`api_key_env` to the name of the environment variable that holds the key.

## Disabling

Set `"enabled": false` (the default) or delete `config.json`.
