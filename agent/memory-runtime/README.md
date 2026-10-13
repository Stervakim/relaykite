# Optional Tencent external memory and Graphify runtime

The unmodified legacy SQLite path remains available until the owner configures
the optional local service. The bundled entry uses original Tencent VectorStore
and LocalStorageBackend; GPT in the active chat supplies distilled records.
There is no automatic model/embedding API, full-chat import or background LLM.

Versions and upstream source are pinned in versions.json. Apply
tencent-external.patch to the indicated TencentDB Agent Memory revision and
bundle MemoryCore/src/codaki/external.ts with esbuild, platform=node,
format=esm, packages=external to reproduce codaki-external.mjs. Keep the original
upstream license. Graphify/NetworkX Python sources in graph-runtime.zip are
query-only; their licenses are supplied alongside it.

Setup requires existing Termux Python and Node24 with node:sqlite/FTS5. It does
not require the Termux GUI during operation. Do not remove Termux: a fully
independent Android runtime is future work.

An authorized maintainer builds a code-only graph for the owner's actual source
using scripts/build_project_graph.py, stages the explicit code/runtime/graph
allowlist and uses scripts/install_phone_memory.py. Its default staging path is
/data/local/tmp/codaki-memory-in. The installer makes a phone-local SQLite/code
backup, generates a local key, binds only127.0.0.1:8420, runs Node as the existing
Termux UID and preserves relay credentials. Import is a separate migrate step.
Never ship a service.json, memory-service.json, memory database, graph of private
files or owner notes in a public release. The public ZIP includes the reader and
source adapter, not a graph of the author's device.

Verify engine=tencentdb-original-external, matching adapter_revision, read-back,
FTS recall and supervisor recovery before relying on the new store. Search is
bounded to6KiB; individual reads use a separate bounded envelope. Keep backups
for a controlled code rollback and never erase either memory store during it.
