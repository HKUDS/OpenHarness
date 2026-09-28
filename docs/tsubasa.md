# Tsubasa profile

You can configure Tsubasa through OpenHarness's existing OpenAI-compatible
profile. The profile keeps its credential separate from your OpenAI key and
sets a 32,768-token context window.

## Configure the profile

Merge this configuration into `~/.openharness/settings.json`, preserving your
other profiles. `max_tokens` is a global output limit, so this example also
affects your other profiles.

```json
{
  "active_profile": "tsubasa",
  "max_tokens": 8192,
  "profiles": {
    "tsubasa": {
      "label": "Tsubasa",
      "provider": "openai",
      "api_format": "openai",
      "auth_source": "tsubasa_api_key",
      "credential_slot": "tsubasa",
      "default_model": "tsubasa-pro",
      "allowed_models": ["tsubasa-fast", "tsubasa-pro"],
      "context_window_tokens": 32768,
      "base_url": "https://api.tsubasa.sh/v1"
    }
  }
}
```

Store your Tsubasa key with the profile setup flow. Use the key prompt so the
key is not included in shell history:

```sh
oh setup tsubasa
oh provider list
oh provider use tsubasa
```

`oh setup tsubasa` stores the key in the profile's `tsubasa` credential slot.
This custom profile does not read `OPENAI_API_KEY` or `TSUBASA_API_KEY`.
`oh auth login tsubasa` is not a built-in authentication command; use the
profile setup flow above.

## Choose a model

The default model is `tsubasa-pro`. To select either public model for a session:

```sh
oh --model tsubasa-fast
oh --model tsubasa-pro
```

Both models have a 32,768-token combined input/output budget. Fast allows up to
8,192 output tokens, and Pro allows up to 16,384. The example uses 8,192 for both;
long prompts, tool schemas, and conversation history still consume context.
