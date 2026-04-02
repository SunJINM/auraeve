# AuraEve Remove Identity System Design

Date: 2026-04-02
Status: Draft approved in chat, awaiting user review of written spec

## Summary

AuraEve will completely remove its identity system.

After this change:

- The runtime will no longer distinguish users by `canonical_user_id`
- There will be no identity resolver, identity store, identity relationship, or owner binding
- Prompt construction will no longer inject identity context
- Session history will no longer persist identity snapshots
- Channels and WebUI will only pass plain message routing fields such as `channel`, `sender_id`, and `chat_id`

This is a deletion-focused refactor. The goal is not to replace the identity system with a different abstraction. The goal is to remove it entirely and keep the runtime simple.

## Goals

- Remove all runtime identity resolution and identity metadata injection
- Remove the `auraeve/identity` subsystem completely
- Remove owner-specific message semantics that depend on identity distinctions
- Keep message routing and session behavior stable using simple channel-local keys
- Reduce code size, runtime branching, and maintenance burden

## Non-Goals

- Introducing a new lightweight identity abstraction
- Preserving cross-channel identity merging
- Preserving owner privilege semantics
- Migrating old session data to a new schema
- Rewriting unrelated runtime components

## Design Principles

This refactor follows these rules:

- Keep logic direct and obvious
- Delete unused code instead of wrapping it
- Avoid compatibility layers unless they prevent real breakage
- Prefer a few clear rules over configurable behavior
- Preserve existing message flow and runtime stability where identity is not involved

## Current Identity-Related Surface Area

Identity currently exists in four places.

### 1. Startup Wiring

`main.py` currently:

- creates `IdentityStore`
- creates `IdentityService`
- creates `IdentityResolver`
- creates `identity.db`
- binds owner QQ to a canonical identity
- binds `WEBUI_OWNER_USER_ID` to the same canonical identity
- injects `identity_resolver` into `RuntimeKernel`

### 2. Runtime Processing

`auraeve/agent_runtime/kernel.py` currently:

- writes `display_name` into metadata
- resolves `canonical_user_id`
- builds identity context for prompts
- prepends special owner text when `metadata["is_owner"]` is true
- stores an `identity` snapshot into session history

### 3. Input Metadata

Identity-related metadata is currently added by:

- `auraeve/webui/chat_service.py`
  - `webui_user_id`
  - `webui_display_name`
- `auraeve/channels/napcat.py`
  - `is_owner`

### 4. Standalone Identity Subsystem

The following directory exists only to support identity:

- `auraeve/identity/`

This includes:

- binding storage
- profile storage
- relationship storage
- canonical identity generation
- metadata injection

## Target Behavior After Removal

After removal, the runtime will use only simple routing fields:

- `channel`
- `sender_id`
- `chat_id`

There will be no runtime concept of:

- canonical identity
- relationship to assistant
- identity confidence
- identity source
- owner privilege

Prompt construction will not receive identity context.

Session persistence will record:

- user message content
- assistant message content
- channel
- chat id
- sender id
- tools used

and nothing identity-specific.

## Session Key Rules

To keep session behavior simple and stable, session keys should follow this rule:

1. If `chat_id` exists, use `channel:chat_id`
2. Else if `sender_id` exists, use `sender_id`
3. Else use `global`

There will be no `canonical_user_id` override.

This preserves current channel-local session continuity without cross-channel merging.

## Owner Semantics

Owner semantics will be removed completely.

That means:

- no owner canonical binding in startup
- no owner relationship such as `brother`
- no `is_owner` metadata in NapCat
- no owner-only prompt prefix in the runtime

NapCat group and private message handling should keep existing routing and mention behavior where that behavior does not depend on owner identity.

Important distinction:

- group filtering and `at_me` behavior are message-routing rules
- owner privilege is identity behavior

The refactor should only delete the latter.

## File-Level Changes

### `main.py`

Delete:

- identity imports
- `identity.db` creation and wiring
- owner binding logic
- WebUI owner binding logic
- `identity_resolver` injection into `RuntimeKernel`

Keep:

- all non-identity startup behavior

### `auraeve/agent_runtime/kernel.py`

Delete:

- `identity_resolver` constructor parameter
- `self._identity_resolver`
- `_resolve_identity_metadata()`
- `_build_identity_context()`
- owner prefix handling
- `identity_snapshot` persistence

Update:

- `_process_message()` should no longer compute or pass `identity_context`
- metadata should only carry non-identity operational fields

### `auraeve/agent_runtime/prompt/assembler.py`

Remove:

- `identity_context` parameter
- any merge logic that only exists for identity context

### `auraeve/agent/engines/base.py`
### `auraeve/agent/engines/legacy.py`
### `auraeve/agent/engines/vector/engine.py`

Remove:

- `identity_context` from method signatures and call paths

### `auraeve/agent/context.py`

Remove:

- identity-related prompt lines or helper methods

### `auraeve/webui/chat_service.py`

Remove:

- `webui_display_name` metadata injection

Keep:

- `user_id` as plain sender id for routing and auditing

### `auraeve/channels/napcat.py`

Remove:

- `is_owner` metadata injection
- owner-specific parsing branches

Keep:

- non-identity group filtering
- at-mention based routing

### `auraeve/bus/events.py`

Simplify:

- `InboundMessage.session_key`

New rule:

- `channel:chat_id` if chat id exists
- otherwise sender id
- otherwise `global`

Delete all comments referencing canonical identity.

### `auraeve/identity/`

Delete the entire directory.

## Data Migration

No migration script is needed.

Reasons:

- old `identity.db` becomes unused and can remain on disk harmlessly
- old session history may still contain `identity` fields, but runtime code can safely ignore them
- deleting old metadata from historical files is unnecessary risk for little value

This is intentionally conservative.

## Testing Strategy

Add or update tests to prove:

- `RuntimeKernel` no longer accepts or uses `identity_resolver`
- no identity context is passed into prompt assembly
- session persistence no longer writes identity snapshots
- WebUI no longer injects `webui_display_name`
- NapCat no longer injects `is_owner`
- no production imports of `auraeve.identity` remain
- no production references to:
  - `canonical_user_id`
  - `relationship_to_assistant`
  - `identity_confidence`
  - `identity_source`

Also re-run full test suite to confirm ordinary chat, cron, heartbeat, queue scheduling, and channel behavior remain stable.

## Risks and Mitigations

### Risk 1: NapCat owner logic is partially mixed with routing logic

Mitigation:

- remove only owner privilege branches
- keep ordinary mention-based and group routing behavior intact
- cover with focused channel tests

### Risk 2: Prompt assembler and engine interface changes ripple broadly

Mitigation:

- delete `identity_context` in one pass across all call sites
- do not leave compatibility parameters behind

### Risk 3: Old historical data still contains identity fields

Mitigation:

- ignore them
- do not mutate history files

This keeps runtime code simple and avoids risky migrations.

## Recommended Implementation Order

1. Add regression tests for identity-free runtime behavior
2. Remove identity handling from `RuntimeKernel`
3. Remove `identity_context` from prompt and engine interfaces
4. Remove identity metadata injection from WebUI and NapCat
5. Simplify `InboundMessage.session_key`
6. Remove identity startup wiring from `main.py`
7. Delete `auraeve/identity/`
8. Run full test suite and text scans

## Expected Outcome

After this refactor, AuraEve will no longer contain a runtime identity system.

The messaging model will be simpler:

- channels provide message routing fields
- the kernel processes messages directly
- sessions remain channel-local
- no hidden cross-channel identity layer exists

This reduces complexity, removes dead conceptual weight, and makes the runtime easier to understand and maintain.
