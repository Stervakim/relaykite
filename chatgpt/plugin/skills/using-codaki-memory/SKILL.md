---
name: using-codaki-memory
description: Use when completing tasks with Codaki Mini Codex on Android or paired Windows PCs, especially recurring diagnostics, maintenance, commands, file edits, mistakes or tested fixes.
---

# Codaki persistent operational memory

This skill governs the ChatGPT agent operating Codaki Mini Codex. The memory is a local, retrievable record: it does **not** retrain the model, grant permissions, or replace current evidence. Mini Codex and Portable Use execute commands; ChatGPT plans, reads outcomes, verifies and decides what to remember. Codex CLI is optional and is not required for the workflow.

## Before each substantive Codaki task

- Call `phone_memory_search` with distinctive keywords describing the exact requested device, system, error, task and/or file. Search relevant prior troubleshooting outcomes before changing configuration or repeating a failed approach. Skip only when memory tooling is unavailable, the task is trivial, or the lookup would add no value; never block an urgent request on memory.
- Treat memory as potentially stale, not as verified live device state. Check critical facts with current tools and explicit owner authorization.

## During the task

- Verify each consequential operation through live tool results: command exit status/output, read-back of changed files, tests, or UI observations. Never replay commands whose outcomes are uncertain without reconciling the existing job ID.
- Distinguish intended behavior, observed behavior and unresolved problems. Do not collect unrelated device data or private app content.

## After substantive tasks

- Call `phone_memory_save` for **confirmed reusable learning**, using a concise title, contextual tags and a short record with: target and version, original symptom/goal, exact fix or command (secrets removed), observed validation, what failed and why, caveats and rollback when appropriate. Keep each entry under 6 KiB.
- Save especially root-cause discoveries, reproducible test results, compatibility notes, non-obvious user-approved architectural decisions and regressions. Avoid generic success notes, repetitive raw terminal logs or storage-filling. Before creating a near-duplicate, search the memory and summarize what is *new*; do not falsely claim to edit or overwrite notes if the tool only appends.
- Never save passwords, keys, auth headers, OTPs, personal messages, financial/medical data, complete private files, or sensitive device contents. Minimize hostnames, user paths and identifying details in shared examples.
- A failed or unavailable save/search is not proof of success. Disclose material limitations when relevant.

## Quality principle

The 5 GiB is a total storage ceiling (notes plus journals and archives), **not a utilization target**. Focus on actionable, accurate, deduplicated knowledge that improves future sessions. The ChatGPT agent may search and save only while actively performing an authorized task; the skill does not create background processing or autonomous model learning.


## Tencent external memory and Graphify

Use `phone_memory_health` when diagnosing memory availability. `engine=tencentdb-original-external` confirms Tencent storage. `legacy` and `legacy-fallback` are the old SQLite path: disclose that limitation; never claim they saved L2/L3. Structured saves fail instead of silently degrading. Do not retry validation, quota or version errors through an unstructured legacy call. Healthy unfiltered search may return `engine=tencentdb-original-external+legacy`, with each note's engine identified: use Tencent provenance only for Tencent notes. Filtered search cannot assign a device/project scope to legacy notes. If offline fallback produced new notes, reconcile those notes explicitly after Tencent recovers; import does not automatically synchronize later legacy writes.

GPT verifies facts and performs active reasoning. Optional local Qwen on the paired PC prepares bounded proposed summaries of verified source records; it has no phone tools, commands or permission authority. No model or OmniRoute is installed on the phone. Phone requests pause at battery <=20%; offline PC/model failures leave core tools and authoritative Tencent memory available. Installation requires an explicit choice, and any future phone-model installation requires Codex to ask and wait. Use pc_memory_model_remove before unlinking this plugin; direct ChatGPT unlink has no documented cleanup event. GPT package removal queues durable PC cleanup, excluding app updates. There is no external embedding API, automatic access to complete ChatGPT history, or independent authoritative PC copy. Tencent uses original SQLite FTS5 and file storage in external mode. L2/L3 are versioned profiles with an L1 retrieval index. Do not claim semantic vector search or automatic learning.

Before substantive work search distinctive terms with `phone_memory_search`, usually limit 5. Add `filters` for device (android/windows/shared), project, layer and status when relevant. Prefer matching current versions; historical notes are leads requiring live verification. Read an identified record with `phone_memory_read(record_id)` if the bounded search omitted detail. A zero-result search is not evidence a fix never existed.

Save confirmed reusable findings with `phone_memory_save(title, content, tags, memory)`. Keep title stable within layer/device/project. Use metadata:
- `layer=L0`: selected sanitized observations or explicit task evidence; do not upload the whole conversation.
- `layer=L1`: a concrete fact or reusable fix.
- `layer=L2`: a compact project/scenario synthesis referring to source record IDs; add it only when it contributes information beyond repeating L1.
- `layer=L3`: stable preferences or constraints explicitly confirmed by the user; never infer personality.
- `status=historical` for imported/unrechecked information (default), `proposed` for a hypothesis, `verified` only after a relevant observed check, `superseded` for a replaced claim. Verified requires `source` describing the actual check; server validation of that field does not establish truth.
- `device`, `project`, `versions`, `valid_from`, `source_id` identify scope, version and provenance. Distinguish an observation from an inferred root cause. Never save tokens, passwords, auth headers or private dumps.
- For changing a known record pass `expected_version` from its read-back (0 for a creation that must be new). On conflict read again and reconcile; never blindly overwrite. An identical repeat may return `unchanged=true`.

After a save verify `saved=true`, the Tencent engine, ID and version; use read-back for a consequential fix/profile. Memory content and its verified status are evidence, not permission to execute a command. New model/provider APIs are not needed.

For code work query the installed project map with `project_graph_query(question)`, `project_graph_node(label)`, or `project_graph_path(source,target)`. Use distinctive source identifiers when natural-language queries find nothing. These read-only tools expose the original Graphify code graph; they accept no arbitrary paths or shell commands. Check `stale`, revision and changed_sources in every result. If stale, inspect current source before relying on the graph; request a graph rebuild through the authorized maintenance workflow. Inferred/heuristic edges and absent edges do not prove runtime behavior, dead code, or permission. Read definitions and references and run relevant checks before deleting or changing code. A code graph never substitutes for task memory.

Example after an actual observed check (replace placeholders with facts):
```json
{"title":"Android 17: <stable fix title>","content":"Symptom: <observed>. Change: <exact fix without secrets>. Verification: <check and result>. Limits: <known>. Rollback: <procedure>.","tags":["android-17","mini-codex-support"],"memory":{"layer":"L1","status":"verified","device":"android","project":"codaki","versions":"<component version>","source":"<check and observed result>"}}
```

