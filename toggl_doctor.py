"""Checks that everything this plugin depends on is present and answering.

    python3 toggl_doctor.py [--offline] [--json]

`setup` runs it last, so an install ends by saying what works rather than by
saying nothing. Run it again at any time with `setup --check`.

Design rules, both learned the hard way:

* A check reports what it *observed*. "ActivityWatch is running" is not the
  same claim as "ActivityWatch has recorded anything today", and the Day scope
  needs the second one -- a bucket that exists but stopped updating looks
  healthy to anything that only asks whether the server answers.
* Nothing here may hang. Every socket gets a timeout and every subprocess a
  deadline, because the one call that famously blocks forever -- a lookup
  against a locked keyring, waiting on a GUI prompt -- is exactly the thing a
  health check is supposed to *report*.

Exit status is 1 if any check failed, 0 if only warnings remain. A warning is
for something optional (idle notifications, the browser bucket); a failure is
for something the plugin cannot work without.
"""

import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

ACTIVITYWATCH_URL = "http://127.0.0.1:5600"
REQUIRED_BUCKETS = {"currentwindow": "window titles", "afkstatus": "idle detection"}
OPTIONAL_BUCKETS = {"web.tab.current": "browser domains"}
CLASSIFIER_PORTS = {8127: "description model", 8128: "embedder"}
PLUGIN_ID = "daz.toggl-track"

OK, WARN, FAIL = "ok", "warn", "fail"


class Report(object):
    def __init__(self):
        self.rows = []

    def add(self, section, name, status, detail):
        self.rows.append({"section": section, "name": name, "status": status,
                          "detail": detail})
        return status

    @property
    def failed(self):
        return any(row["status"] == FAIL for row in self.rows)


def _get(url, timeout=4):
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _run(command, timeout=15, stdin_text=None):
    try:
        return subprocess.run(command, input=stdin_text, text=True, check=False,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=timeout)
    except (OSError, subprocess.TimeoutExpired, FileNotFoundError):
        return None


# --- checks -----------------------------------------------------------------

def check_runtime(report):
    version = "%d.%d.%d" % sys.version_info[:3]
    # zoneinfo, used for the local day boundary, arrived in 3.9.
    status = OK if sys.version_info >= (3, 9) else FAIL
    report.add("Runtime", "python3", status,
               version if status == OK else version + " (3.9 or newer required)")

    for tool, why, required in (("secret-tool", "token storage (libsecret)", True),
                                ("notify-send", "idle reminders", False),
                                ("systemctl", "the optional local classifier", False)):
        path = shutil.which(tool)
        if path:
            report.add("Runtime", tool, OK, why)
        else:
            report.add("Runtime", tool, FAIL if required else WARN,
                       "missing -- needed for " + why)


def check_secrets(report, offline=False):
    try:
        import toggl_secret
    except Exception as error:
        report.add("Token", "secret service", FAIL, "cannot load toggl_secret (%s)" % error)
        return

    if not shutil.which("secret-tool"):
        report.add("Token", "secret service", FAIL,
                   "secret-tool is missing; install libsecret")
        return

    if not toggl_secret.service_running():
        report.add("Token", "secret service", FAIL,
                   "nothing owns org.freedesktop.secrets; start gnome-keyring-daemon")
        return
    report.add("Token", "secret service", OK, "org.freedesktop.secrets is answering")

    mode = toggl_secret.mode()
    if mode == toggl_secret.MODE_SECURE:
        path, problem = toggl_secret.secure_ready()
        if problem:
            report.add("Token", "keyring", FAIL, problem)
            return
        report.add("Token", "keyring", OK,
                   "'%s', password-protected and unlocked -- encrypted at rest"
                   % toggl_secret.COLLECTION_LABEL)
    else:
        report.add("Token", "keyring", WARN,
                   "login keyring. Omarchy's default keyring has no password, so "
                   "the token is stored unencrypted; run setup --secure-keyring "
                   "to protect it")

    # Never `lookup` before the lock check above: against a locked collection it
    # waits on a GUI prompt rather than returning.
    found = _run(["secret-tool", "lookup", "service", toggl_secret.SERVICE_ID,
                  "account", toggl_secret.ACCOUNT], timeout=15)
    if found is None or found.returncode != 0 or not (found.stdout or "").strip():
        report.add("Token", "stored token", FAIL, "no token stored; run setup")
        return
    report.add("Token", "stored token", OK, "present (%d characters)"
               % len((found.stdout or "").strip()))

    if offline:
        report.add("Token", "accepted by Toggl", WARN, "skipped (--offline)")
        return
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "toggl_api.py")
    probe = _run([sys.executable, script], timeout=45,
                 stdin_text=json.dumps({"action": "bootstrap", "skip_sync": True}))
    if probe is None:
        report.add("Token", "accepted by Toggl", FAIL, "the backend did not answer")
        return
    try:
        answer = json.loads(probe.stdout or "{}")
    except ValueError:
        answer = {}
    if answer.get("ok"):
        user = (answer.get("data") or {}).get("user") or {}
        report.add("Token", "accepted by Toggl", OK,
                   "signed in as %s" % (user.get("name") or "this account"))
    else:
        message = ((answer.get("error") or {}).get("message")
                   or "no response from the Toggl API")
        report.add("Token", "accepted by Toggl", FAIL, message)


def check_activitywatch(report):
    try:
        _get(ACTIVITYWATCH_URL + "/api/0/info")
    except (urllib.error.URLError, OSError, ValueError) as error:
        report.add("ActivityWatch", "server", FAIL,
                   "%s is not answering (%s). The Day scope needs it; install "
                   "ActivityWatch (aw-server-rust + aw-awatcher) or the Omalog "
                   "plugin, which manages them." % (ACTIVITYWATCH_URL, error))
        return
    report.add("ActivityWatch", "server", OK, ACTIVITYWATCH_URL + " is answering")

    try:
        buckets = _get(ACTIVITYWATCH_URL + "/api/0/buckets/")
    except (urllib.error.URLError, OSError, ValueError) as error:
        report.add("ActivityWatch", "buckets", FAIL, "cannot list buckets (%s)" % error)
        return
    if not isinstance(buckets, dict):
        report.add("ActivityWatch", "buckets", FAIL, "unexpected bucket listing")
        return

    by_type = {}
    for bucket_id, bucket in buckets.items():
        if isinstance(bucket, dict):
            by_type.setdefault(bucket.get("type"), []).append(bucket_id)

    for bucket_type, why in REQUIRED_BUCKETS.items():
        found = by_type.get(bucket_type)
        if not found:
            report.add("ActivityWatch", bucket_type, FAIL,
                       "no %s bucket; %s will not work. Is aw-awatcher running?"
                       % (bucket_type, why))
            continue
        # A bucket that exists but has stopped recording looks identical to a
        # healthy one until the Day scope comes back empty.
        report.add("ActivityWatch", bucket_type, *_bucket_freshness(found[0], why))

    for bucket_type, why in OPTIONAL_BUCKETS.items():
        if by_type.get(bucket_type):
            report.add("ActivityWatch", bucket_type, OK, why)
        else:
            report.add("ActivityWatch", bucket_type, WARN,
                       "absent -- %s will be missing from day blocks" % why)


def _bucket_freshness(bucket_id, why):
    try:
        events = _get("%s/api/0/buckets/%s/events?limit=1"
                      % (ACTIVITYWATCH_URL, urllib.parse.quote(bucket_id)))
    except Exception as error:
        return WARN, "%s exists, but its events could not be read (%s)" % (bucket_id, error)
    if not isinstance(events, list):
        return WARN, "%s answered with something other than an event list" % bucket_id
    if not events:
        return WARN, "%s exists but has recorded nothing yet (%s)" % (bucket_id, why)
    first = events[0] if isinstance(events[0], dict) else {}
    stamp = first.get("timestamp") or "an unknown time"
    return OK, "%s, last event %s" % (why, stamp)


def check_classifier(report):
    try:
        import toggl_secret

        root = toggl_secret.data_root()
    except Exception:
        root = os.path.join(os.path.expanduser("~"), ".local", "share",
                            "omarchy-toggl-track")
    models = os.path.join(root, "models")
    if not os.path.isdir(models) or not os.listdir(models):
        report.add("Classifier", "installed", WARN,
                   "not installed (optional); run setup --classifier to add it")
        return
    report.add("Classifier", "models", OK, models)
    for port, why in CLASSIFIER_PORTS.items():
        try:
            _get("http://127.0.0.1:%d/health" % port, timeout=3)
        except Exception as error:
            report.add("Classifier", "port %d" % port, WARN,
                       "%s is not answering (%s); start it with systemctl --user"
                       % (why, error))
        else:
            report.add("Classifier", "port %d" % port, OK, why)


def check_plugin(report):
    listing = _run(["omarchy-plugin-list", "--json"], timeout=15)
    if listing is None or listing.returncode != 0:
        report.add("Plugin", "installed", WARN,
                   "omarchy-plugin-list did not answer; cannot confirm the "
                   "plugin is registered")
        return
    try:
        plugins = json.loads(listing.stdout or "[]")
    except ValueError:
        plugins = []
    for plugin in plugins:
        if isinstance(plugin, dict) and plugin.get("id") == PLUGIN_ID:
            where = plugin.get("sourceDir") or "registered with the shell"
            if plugin.get("enabled"):
                report.add("Plugin", "installed", OK, where + ", enabled")
            else:
                # Installed but not enabled is the quiet failure: everything
                # below is healthy and no widget ever appears in the bar.
                report.add("Plugin", "installed", WARN,
                           "%s, but not enabled -- run: omarchy plugin enable %s"
                           % (where, PLUGIN_ID))
            return
    report.add("Plugin", "installed", WARN,
               "%s is not registered with the shell yet; add it with "
               "`omarchy plugin add`, or ./install --dev --enable to work on it"
               % PLUGIN_ID)


# --- output -----------------------------------------------------------------

MARKS = {OK: "  ok  ", WARN: " warn ", FAIL: " FAIL "}


def run(offline=False):
    report = Report()
    check_runtime(report)
    check_secrets(report, offline=offline)
    # ActivityWatch is on loopback, so --offline does not exempt it; the flag
    # exists to skip the one check that leaves the machine.
    check_activitywatch(report)
    check_classifier(report)
    check_plugin(report)
    return report


def render(report, stream=sys.stderr):
    section = None
    width = max([len(row["name"]) for row in report.rows] or [0])
    for row in report.rows:
        if row["section"] != section:
            section = row["section"]
            stream.write("\n%s\n" % section)
        stream.write("  [%s] %-*s  %s\n"
                     % (MARKS[row["status"]], width, row["name"], row["detail"]))
    failures = [row for row in report.rows if row["status"] == FAIL]
    warnings = [row for row in report.rows if row["status"] == WARN]
    stream.write("\n%d ok, %d warning%s, %d failure%s\n"
                 % (len(report.rows) - len(failures) - len(warnings),
                    len(warnings), "" if len(warnings) == 1 else "s",
                    len(failures), "" if len(failures) == 1 else "s"))
    return 1 if failures else 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    offline = "--offline" in argv
    as_json = "--json" in argv
    for argument in argv:
        if argument not in ("--offline", "--json"):
            sys.stderr.write("usage: toggl_doctor.py [--offline] [--json]\n")
            return 2
    report = run(offline=offline)
    if as_json:
        sys.stdout.write(json.dumps({"rows": report.rows,
                                     "ok": not report.failed}, indent=2) + "\n")
        return 1 if report.failed else 0
    return render(report)


if __name__ == "__main__":
    raise SystemExit(main())
