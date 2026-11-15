import argparse
import json
import os
import sys

from .adb import Adb
from .server import App, make_server


def import_legacy(app, directory):
    """Import tvs.json/state.json from the earlier standalone watcher script."""
    with open(os.path.join(directory, "tvs.json")) as f:
        tvs = json.load(f)
    try:
        with open(os.path.join(directory, "state.json")) as f:
            state = json.load(f)
    except Exception:
        state = {}
    for t in tvs:
        try:
            d = app.store.add_device(t["name"], t["addr"])
            if state.get(t["addr"]):
                app.store.update_device(d["id"], restore={"enabled": True, "last": state[t["addr"]]})
            print("imported", t["name"])
        except ValueError as e:
            print("skipped", t["name"], e)


def main():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p = argparse.ArgumentParser(description="TV ADB Manager")
    p.add_argument("--host", default=os.environ.get("TVM_HOST", "0.0.0.0"))
    p.add_argument("--port", type=int, default=int(os.environ.get("TVM_PORT", "8420")))
    p.add_argument("--data", default=os.environ.get("TVM_DATA", os.path.join(here, "data")))
    p.add_argument("--adb", default=os.environ.get("TVM_ADB", "adb"), help="path to the adb binary (or a fake for testing)")
    p.add_argument("--poll", type=float, default=float(os.environ.get("TVM_POLL", "3")), help="seconds between device polls")
    p.add_argument("--import-legacy", metavar="DIR", help="import devices from an old tvs.json and exit")
    args = p.parse_args()

    app = App(args.data, os.path.join(here, "web"), adb=Adb(args.adb), env_password=os.environ.get("TVM_PASSWORD"),
              poll=args.poll, start_threads=not args.import_legacy)
    if args.import_legacy:
        import_legacy(app, args.import_legacy)
        return
    srv = make_server(app, args.host, args.port)
    print("TV ADB Manager listening on http://%s:%d" % (args.host, args.port), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.shutdown()


if __name__ == "__main__":
    sys.exit(main())
