Place local tiktoken vocabulary files here to avoid first-run network fetch.

Supported file:
- `cl100k_base.tiktoken`

Runtime behavior:
1. If `resources/tiktoken/cl100k_base.tiktoken` exists, AuraEve loads it directly.
2. Otherwise it falls back to `tiktoken.get_encoding("cl100k_base")`.

This is useful in regions with slow outbound network access.
