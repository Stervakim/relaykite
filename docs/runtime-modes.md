# RelayKite Android runtime 0.2.5

The signed `org.relaykite.runtime` APK includes arm64 Bionic Python and Node, the original Tencent memory adapter and the original Graphify reader. Executable libraries stay in Android's PackageManager native library directory. The root component verifies the matching APK digest and stages immutable runtime versions under `/data/adb/relaykite-runtime/versions`.

Choose a mode in the APK:

| Mode | Identity and capabilities |
|---|---|
| Without root or Termux | Ordinary app UID and Android sandbox; network, original memory, own-permission files, jobs and PTYs. Root/system shells and cross-app virtual-screen control are unavailable. No implicit `su`. |
| Root without Termux | Embedded Python/Node; root and system UID 2000 shells, privileged tools and virtual screens. Termux shell backend is explicitly disabled. |
| Root with Termux | The same embedded main runtime; optional Termux shell tools run under Termux's separate UID. |

Import your private relay configuration through the APK's document picker on a fresh installation. Installing a public APK/card never supplies credentials. Install the matching root ZIP through Magisk only when root capabilities are wanted; existing technical module/storage IDs are preserved.

For an existing Termux-backed owner installation, first stage the matching APK and perform the explicit private migration in `scripts/migrate_private_runtime.py`. The original credentials, notes, task IDs and separate Android Use installation are retained. Inspect the migration receipt before retrying any interrupted transition. An already committed migration is never rerun blindly.

Mode switching stops the old worker, snapshots SQLite including committed WAL data and immutable memory records, then commits the selected authority before starting one new worker. A failure after that commit is uncertain, with the selected copy authoritative. Use the APK's interrupted-switch check for reconciliation. Never manually run workers against both copies.

Stop is durable across controller restarts and boot. Resume requires explicit mode selection. Staging a new verified runtime does not by itself restart a running process; stop through the APK, update the controller, inspect the existing receipt, then resume. Rollback selects a retained verified runtime while stopped; it does not replace newer memory or re-execute uncertain tasks. Keep the matching signed APK when rolling back its app runtime.

The main GPT connection and authoritative memory remain on the phone. Optional local background summaries may be unavailable when their selected PC backend is offline; that does not disable normal phone tools or memory. Model output is proposed evidence, never verified authorization or a tool command.
