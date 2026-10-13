---
name: using-codaki-pc-use
description: Use when operating a paired Windows PC through Mini Codex Portable UI operations, especially window sessions, batches, native images, pending jobs or uncertain input.
---

# Windows Portable inside Mini Codex

Select the intended host with mini_connections and retain its connection_id.
Call mini_pc_call(connection_id,tool="pc_status",arguments={},request_id=<stable
cloud ID>); poll mini_pc_result(connection_id,job_id) when pending. The local chat
host may be a different PC. Check live local capabilities and portable_use;
configured means a local endpoint descriptor exists, not proven runtime health.
Verify the backend with tool="pc_use_capabilities" and tool="pc_use_diagnostics".

All pc_use operations run through **mini_pc_call**, with operation arguments
inside arguments. They are not separate top-level client tools. Available:
pc_use_apps/capabilities/diagnostics/session_start/session_extend/session_stop/
observe/launch/action/batch/result/reconcile. The chosen PC must run Portable
with --local-ipc-windows. There is one existing engine; no new desktop is created.
If the client schema still lacks these enum choices, refresh the same plugin or
open a fresh chat; do not fabricate a callable tool or bypass its access checks.

## Grants and identities

Portable UI requires the existing locally approved **terminal** capability,
which already permits processes with Windows-user rights. The worker intersects
local and cloud grants at execution. A local revoke wins over a retained cloud
grant. Do not edit grants or start a second engine to bypass an unavailable tool.
Only the selected Mini connection's sessions and request receipts are accessible.

Each call has two stable IDs:
- outer mini_pc_call.request_id identifies the cloud queue operation;
- inner arguments.request_id identifies the Portable operation (8–80 ASCII
  letters, digits, underscore or hyphen).
Use new IDs for new operations and retain both for identical transport retries.
Changing either ID to poll input could repeat the action. A returned cloud job_id
is a third identifier: poll mini_pc_result with it, never resubmit UI to poll.

## Windows sessions

Discover applications via pc_use_apps, select their returned windows[].window_id,
then pass that exact value as target to
pc_use_session_start. Retain session_id; establish ownership before reusing or
stopping an existing session. Observe that session with pc_use_observe, then use
its fresh observation_id for action/batch. Stop only a session this task owns;
stopping it leaves the application open. Do not close unrelated windows.

Up to eight **window leases** can coexist. They share a desktop, user account,
mouse and keyboard. Physical input is serialized; another window's action can
invalidate your observation. Screenshots and physical keyboard/coordinates need
the selected window in the foreground. Semantic UIA depends on actual app
support; a lease does not authorize background keyboard input. There are no
eight isolated desktops, secure-desktop access or implicit focus changes.

## Batch and uncertain outcomes

A batch has 1–12 sequential semantic steps, timeout_ms at most30000, and stops
at the first error, ambiguous selector, timeout or uncertain effect. Completed
steps remain applied. Use stable selectors (text/resource_id/description/role,
optional zero-based occurrence), not positional IDs or coordinates. Unsupported
Windows actions are rejected before first input. Observe unknown next screens
instead of guessing a long recipe. Read completed, steps and stopped_at.

For an uncertain child C, call:
```json
{"connection_id":"<selected>","tool":"pc_use_result","arguments":{"request_id":"lookup_child_0001","target_request_id":"<C>"},"request_id":"cloud_lookup_0001"}
```
Inspect the owned window and actual evidence, then call pc_use_reconcile with
target_request_id=C, outcome=applied or not_applied, evidence and its own stable
inner/outer IDs. Never invent evidence. After a crash, diagnostics/result may
show uncertain parent and child; preserve checkpoint completed steps and
inflight_request_id. Reconcile each actually uncertain receipt separately.
Do not reconcile not_started steps. Lookup/reconcile execute no original input.

After resolving the effect, observe again and submit only remaining necessary
authorized steps. Never replay completed steps or silently resume a stopped
batch. Unknown input in one window can block further input globally because
Windows shares physical input; other leases need not be stopped.

mini_pc_cancel(connection_id,job_id) cancels only a still-queued job. A running
or uncertain job cannot be cancelled this way; inspect its original result and
actual PC. Cancellation cannot undo applied input. Deadline pressure never
justifies replay, killing the engine or claiming an unconfirmed cancellation.

MCP images accompany text receipts. An omitted/oversized screenshot does not
erase an applied action; read the warning and observe again. Search and save
only confirmed sanitized reusable findings with using-codaki-memory.
