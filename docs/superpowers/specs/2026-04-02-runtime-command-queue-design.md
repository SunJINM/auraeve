# AuraEve Runtime Command Queue Design

Date: 2026-04-02
Status: Draft approved in chat, awaiting user review of written spec

## Summary

AuraEve will replace its current multi-entry inbound runtime with a single command queue entrypoint modeled on Claude Code.

After this refactor:

- Every runtime input enters through one API: `enqueue_command(...)`
- The runtime no longer uses inbound `MessageBus` delivery as a first-class execution path
- `RuntimeKernel` no longer exposes `process_direct(...)`
- Subagent completion no longer resumes the main agent via synthetic `tool_result`
- Subagent completion becomes a queued `task-notification` event consumed only when the scheduler is idle or reaches a turn checkpoint

The first migration scope includes exactly four command modes:

- `prompt`
- `task-notification`
- `cron`
- `heartbeat`

This refactor is intended to align AuraEve's main-thread wakeup and background-task semantics with Claude Code rather than layering a compatibility shim on top of the current model.

## Goals

- Establish a single inbound runtime entrypoint for all supported message sources
- Align scheduling semantics with Claude Code's queue-driven model
- Remove direct async resume callbacks from subagent completion
- Introduce explicit command priorities and scoped draining
- Preserve current agent execution, session persistence, and tool execution behavior where possible

## Non-Goals

- Rebuild the outbound reply path into a universal event bus
- Expand the first version beyond the four approved command modes
- Redesign the prompt assembler, tool registry, or session store unless required to support queue semantics
- Add remote subagent transport back into the system

## Current Problems

AuraEve currently has multiple inbound execution paths:

- Channels create `InboundMessage` and call `MessageBus.publish_inbound()`
- WebUI creates `InboundMessage` and calls `MessageBus.publish_inbound()`
- `cron` calls `RuntimeKernel.process_direct(...)`
- `heartbeat` calls `RuntimeKernel.process_direct(...)`
- Subagent completion enqueues a notification but also directly resumes the kernel

This creates several architectural mismatches with Claude Code:

- There is no single runtime entrypoint
- Background completions can directly inject themselves into the main execution path
- Subagent completion is modeled as a synthetic tool result instead of a new background event
- Scheduling policy is split across unrelated code paths

## Target Architecture

The runtime will be reorganized into four core layers.

### 1. Command Types

Add `auraeve/agent_runtime/command_types.py` to define the canonical runtime input model.

Key types:

- `QueuedCommand`
- `CommandMode`
- `CommandPriority`
- `CommandOrigin`

Required `QueuedCommand` fields:

- `id`
- `session_key`
- `source`
- `mode`
- `priority`
- `payload`
- `origin`
- `created_at`
- `agent_id` for scoped drain behavior

### 2. Command Queue

Add `auraeve/agent_runtime/command_queue.py`.

Responsibilities:

- Hold the process-local runtime command queue
- Provide the only inbound runtime API: `enqueue_command(...)`
- Support queue subscriptions for scheduler wakeup
- Dequeue by priority with FIFO within a priority level
- Support scoped drain by session, agent, mode, and priority ceiling
- Support removal of only commands actually consumed at a checkpoint

Priority order matches Claude Code:

- `now`
- `next`
- `later`

Initial defaults:

- `prompt` -> `next`
- `task-notification` -> `later`
- `cron` -> `later`
- `heartbeat` -> `later`

### 3. Command Projection

Add `auraeve/agent_runtime/command_projection.py`.

Responsibilities:

- Convert queued commands into the message objects the runtime actually feeds into the model
- Centralize the text and metadata representation of background events

Projection rules:

- `prompt` becomes a standard user input
- `task-notification` becomes a background event message
- `cron` becomes a system-triggered input
- `heartbeat` becomes a system-triggered input

Important semantic change:

Subagent completion must no longer project into a fake `tool_call` plus `tool_result` pair. It must project into a new event message semantically equivalent to "a background agent completed a task".

### 4. Runtime Scheduler

Add `auraeve/agent_runtime/runtime_scheduler.py`.

Responsibilities:

- Subscribe to queue changes
- Start a new main-thread turn when idle and a queued command is available
- During a running turn, drain eligible queued commands only at explicit checkpoints
- Enforce main-thread vs subagent drain scope
- Batch command consumption for a turn when appropriate

The scheduler replaces the current mix of inbound bus delivery and direct kernel callbacks.

## Kernel Boundary After Refactor

`RuntimeKernel` remains the execution engine for a scheduled turn, but it no longer acts as the system-wide ingress.

After refactor, `RuntimeKernel` should:

- execute a scheduled turn
- assemble prompts and run tools
- return final output for dispatch

`RuntimeKernel` should no longer:

- own the global inbound message loop
- consume `MessageBus` inbound messages as its main ingress
- expose `process_direct(...)`
- register a direct subagent-completion resume callback

## Checkpoint Semantics

AuraEve should mirror Claude Code's two main consumption points.

### Idle Wakeup

When the main thread is idle and the queue becomes non-empty, the scheduler dequeues the next eligible command and starts a new turn.

### Mid-Turn Checkpoint

When the main thread is already running, queued commands must not interrupt the current execution stack directly. Instead, the runtime drains eligible commands only at a safe checkpoint before the next model request.

First implementation scope:

- Add one checkpoint before each new model request within the turn loop
- Do not add drains after every tool execution or hook callback

Initial checkpoint behavior:

- Main thread drains only commands addressed to the main thread
- Subagents drain only `task-notification` commands addressed to themselves
- `prompt` commands remain main-thread only
- Mid-turn drain initially consumes at most `next`
- `later` commands naturally wait for end-of-turn idle scheduling unless a later extension introduces a wider drain rule

## Source Migration Plan

The first migration covers four input sources.

### Prompt

Current paths:

- channel adapters -> `InboundMessage` -> `MessageBus.publish_inbound()`
- WebUI -> `InboundMessage` -> `MessageBus.publish_inbound()`

Target:

- all prompt producers create `QueuedCommand(mode="prompt", priority="next")`
- all prompt producers call `enqueue_command(...)`

### Task Notification

Current path:

- subagent lifecycle enqueues a notification and then directly resumes the main kernel using synthetic result injection

Target:

- subagent lifecycle creates `QueuedCommand(mode="task-notification", priority="later")`
- no direct resume callback
- no synthetic `subagent_result` tool messages

### Cron

Current path:

- `main.py` directly calls `RuntimeKernel.process_direct(...)`

Target:

- cron handler creates `QueuedCommand(mode="cron", priority="later")`
- scheduler decides when it runs

### Heartbeat

Current path:

- heartbeat callback directly calls `RuntimeKernel.process_direct(...)`

Target:

- heartbeat callback creates `QueuedCommand(mode="heartbeat", priority="later")`
- scheduler decides when it runs

## Module-Level Changes

### New modules

- `auraeve/agent_runtime/command_types.py`
- `auraeve/agent_runtime/command_queue.py`
- `auraeve/agent_runtime/command_projection.py`
- `auraeve/agent_runtime/runtime_scheduler.py`

### Modules to rewrite or substantially change

- `auraeve/agent_runtime/kernel.py`
- `auraeve/subagents/lifecycle.py`
- `auraeve/subagents/notification.py`
- `auraeve/webui/chat_service.py`
- `auraeve/channels/base.py`
- `main.py`
- turn-loop code in `RunOrchestrator` and/or `SessionAttemptRunner` to add checkpoint draining

### Old runtime paths to remove from the core flow

- inbound `MessageBus` execution path
- `RuntimeKernel.process_direct(...)`
- direct subagent resume callback path
- synthetic `subagent_result` message injection

## Outbound Behavior

Outbound delivery is not the focus of this refactor.

The current send/dispatch path may remain temporarily, but it should no longer define runtime ingress semantics. If retained, it should be treated as a response dispatcher rather than as a bidirectional message bus abstraction.

## Error Handling

- Queue operations must not drop commands silently
- Scheduler failures must fail the affected turn without corrupting queue state
- Consumed commands must only be removed after they have been projected into the running turn
- Failed subagent completions still enqueue a `task-notification`; the payload includes failure status and summary
- Commands for the wrong scope must remain queued, not be discarded

## Testing Strategy

The refactor should be validated primarily through scheduling semantics rather than superficial response tests.

Required coverage:

1. `CommandQueue` unit tests
   - priority ordering
   - FIFO within same priority
   - scoped dequeue and snapshot behavior
   - remove-consumed behavior

2. `RuntimeScheduler` unit tests
   - idle wakeup
   - no direct interruption while running
   - checkpoint drain behavior
   - scope separation between main thread and subagents

3. `task-notification` behavior tests
   - subagent completion enqueues a command only
   - no direct kernel resume
   - projected message matches background-event semantics

4. source integration tests
   - prompt sources enqueue commands instead of publishing inbound messages
   - cron no longer uses `process_direct(...)`
   - heartbeat no longer uses `process_direct(...)`

5. end-to-end regression tests
   - basic chat still works
   - cron-triggered run
   - heartbeat-triggered run
   - subagent completion is consumed on a later turn boundary or checkpoint

## Implementation Sequence

1. Introduce command types and queue
2. Route the four approved sources into `enqueue_command(...)`
3. Replace synthetic subagent result injection with queued `task-notification`
4. Shrink `RuntimeKernel` to scheduled-turn execution only
5. Add `RuntimeScheduler` as the new top-level runtime loop
6. Add checkpoint drain behavior in the turn loop
7. Remove inbound bus execution and `process_direct(...)`
8. Migrate and stabilize tests

## Risks and Mitigations

### Risk: hidden dependencies on `InboundMessage`

Mitigation:

- keep a short-lived adapter layer during migration if needed
- remove it only after queue-based tests pass

### Risk: race conditions around queue consumption

Mitigation:

- centralize dequeue and remove-consumed behavior in `CommandQueue`
- keep scheduler as the only consumer coordinator

### Risk: regressions in session routing

Mitigation:

- require `session_key` on all queued commands
- add explicit tests for multi-session isolation

### Risk: half-migrated subagent semantics

Mitigation:

- remove direct kernel resume in the same change set that introduces queued `task-notification`
- delete synthetic result injection tests and replace them with notification-event tests

## Acceptance Criteria

The design is considered implemented when all of the following are true:

- there is exactly one inbound runtime API used by production paths: `enqueue_command(...)`
- `prompt`, `task-notification`, `cron`, and `heartbeat` all use that API
- `RuntimeKernel.process_direct(...)` no longer exists
- inbound `MessageBus` delivery is no longer part of the production execution path
- subagent completion no longer resumes the main agent directly
- subagent completion is represented as a queued background event
- the runtime supports idle wakeup and mid-turn checkpoint draining
- the migrated test suite passes
