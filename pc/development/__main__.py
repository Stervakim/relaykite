"""Run: python -m development serve --data <private-directory> --open."""
import argparse
from pathlib import Path
import signal
import threading
import webbrowser

from .server import DevelopmentServer


def main(argv=None):
    parser = argparse.ArgumentParser(description='RelayKite autonomous development control room')
    parser.add_argument('operation', choices=['serve'])
    parser.add_argument('--data', type=Path, default=Path.cwd() / '.relaykite-dev')
    parser.add_argument('--port', type=int, default=8768)
    parser.add_argument('--open', action='store_true', help='Open the local authenticated control room')
    parser.add_argument('--execution-policy', choices=['workspace-write', 'android-root'], default='workspace-write',
                        help='Codex workspace sandbox, or explicit unsandboxed root control on an Android root service')
    parser.add_argument('--android-ui', action='store_true',
                        help='Use the local Android ChatGPT UI driver instead of a desktop browser')
    options = parser.parse_args(argv)
    service = DevelopmentServer(options.data, port=options.port,
                                execution_policy=options.execution_policy, android_ui=options.android_ui).start()
    stopped = threading.Event()
    for item in (signal.SIGINT, signal.SIGTERM):
        signal.signal(item, lambda *_: stopped.set())
    print('RelayKite control room: ' + service.url + '/#token=' + service.token, flush=True)
    print('Local access key is private. ChatGPT login is configured separately; no model API key is required.', flush=True)
    print('Execution policy: ' + service.execution_policy, flush=True)
    if options.open:
        webbrowser.open(service.url + '/#token=' + service.token)
    try:
        stopped.wait()
    finally:
        service.close()


if __name__ == '__main__':
    main()
