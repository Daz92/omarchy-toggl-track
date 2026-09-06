"""Secret Service access beyond what `secret-tool` can express.

The default path stores the Toggl token in the login keyring through
`secret-tool`, and needs nothing from this module.

It needs saying plainly, because it decides whether the second mode is worth
having: Omarchy's installer creates a *passwordless* login keyring
(`install/user/default-keyring.sh`) and strips `pam_gnome_keyring` from the
SDDM auth stack, and a passwordless gnome-keyring is not encrypted. The token
sits in `~/.local/share/keyrings/Default_keyring.keyring` in the clear,
protected by file permissions alone -- verified by finding the token verbatim
inside that file. `setup --secure-keyring` moves it into a collection with its
own password, which is encrypted at rest.

That mode needs three things `secret-tool` cannot do: create a collection with
a known password and no GUI prompt, ask whether a collection is locked, and
unlock it. All three are D-Bus calls, made here through PyGObject
(`python-gobject`, part of Omarchy's base install) and only on the paths that
need them -- the default mode never imports gi.

**A read must never block.** `secret-tool lookup` against a locked collection
waits forever on a `gcr-prompter` dialog; that was measured, not assumed. The
panel spawns this code with stdin closed and gives it ten seconds, so the wait
would end in a timeout with a password dialog stranded on the user's screen.
Every read here asks about the lock first, over D-Bus, and refuses with a
message naming the fix rather than summoning a prompt nobody asked for.
"""

import os
import subprocess

SERVICE_ID = "daz.toggl-track"
ACCOUNT = "api-token"
COLLECTION_LABEL = "Omarchy Toggl Track"

SECRETS_NAME = "org.freedesktop.secrets"
SECRETS_ROOT = "/org/freedesktop/secrets"
SERVICE_IFACE = "org.freedesktop.Secret.Service"
COLLECTION_IFACE = "org.freedesktop.Secret.Collection"
PROPERTIES_IFACE = "org.freedesktop.DBus.Properties"
# gnome-keyring's own extension. The standard CreateCollection returns a prompt
# object and drives a GUI; this takes the password directly, which is what lets
# setup run over SSH or a bare TTY.
GUILT_IFACE = "org.gnome.keyring.InternalUnsupportedGuiltRiddenInterface"

CALL_TIMEOUT_MS = 10000

MODE_DEFAULT = "default"
MODE_SECURE = "secure"


class SecretError(Exception):
    """Raised with a message meant for the person reading it, not a log."""


def data_root():
    data_home = os.environ.get("XDG_DATA_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "share")
    return os.path.join(data_home, "omarchy-toggl-track")


def mode_path():
    return os.path.join(data_root(), "keyring-mode")


def mode():
    """Which collection holds the token. Unreadable marker means default: the
    plugin must keep working when $XDG_DATA_HOME is missing or unwritable."""
    try:
        with open(mode_path(), "r", encoding="utf-8") as handle:
            value = handle.read().strip()
    except (OSError, ValueError):
        return MODE_DEFAULT
    return MODE_SECURE if value == MODE_SECURE else MODE_DEFAULT


def set_mode(value):
    if value not in (MODE_DEFAULT, MODE_SECURE):
        raise SecretError("unknown keyring mode: %s" % value)
    root = data_root()
    os.makedirs(root, mode=0o700, exist_ok=True)
    path = mode_path()
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(value + "\n")
    os.chmod(path, 0o600)


# --- D-Bus ------------------------------------------------------------------

def _gi():
    try:
        import gi  # noqa: F401  -- imported for the side effect of the check
        from gi.repository import Gio, GLib
    except (ImportError, ValueError) as error:
        # No package-manager command in the text. The marketplace's security
        # baseline reads one as a package-management capability even inside an
        # error string, and this module installs nothing.
        raise SecretError(
            "the secure keyring needs the system python-gobject package; "
            "install it, or run setup --plain-keyring to use the login "
            "keyring instead. (%s)" % error)
    return Gio, GLib


def _bus():
    Gio, GLib = _gi()
    try:
        return Gio.bus_get_sync(Gio.BusType.SESSION, None), Gio, GLib
    except GLib.Error as error:
        raise SecretError("no D-Bus session bus; is this a desktop session? (%s)"
                          % error.message)


def _call(bus, Gio, GLib, path, iface, method, params, reply):
    try:
        return bus.call_sync(SECRETS_NAME, path, iface, method, params, reply,
                             Gio.DBusCallFlags.NONE, CALL_TIMEOUT_MS, None)
    except GLib.Error as error:
        raise SecretError(error.message)


def service_running():
    """True when something owns org.freedesktop.secrets. Distinguishes 'no
    token' from 'no keyring daemon', which secret-tool reports identically --
    both are a bare exit 1 with no output."""
    try:
        bus, Gio, GLib = _bus()
    except SecretError:
        return False
    try:
        reply = bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus",
                              "org.freedesktop.DBus", "NameHasOwner",
                              GLib.Variant("(s)", (SECRETS_NAME,)),
                              GLib.VariantType("(b)"), Gio.DBusCallFlags.NONE,
                              CALL_TIMEOUT_MS, None)
    except GLib.Error:
        return False
    return bool(reply.unpack()[0])


def _open_session(bus, Gio, GLib):
    reply = _call(bus, Gio, GLib, SECRETS_ROOT, SERVICE_IFACE, "OpenSession",
                  GLib.Variant("(sv)", ("plain", GLib.Variant("s", ""))),
                  GLib.VariantType("(vo)"))
    return reply.unpack()[1]


def _collections(bus, Gio, GLib):
    reply = _call(bus, Gio, GLib, SECRETS_ROOT, PROPERTIES_IFACE, "Get",
                  GLib.Variant("(ss)", (SERVICE_IFACE, "Collections")),
                  GLib.VariantType("(v)"))
    return list(reply.unpack()[0])


def _label(bus, Gio, GLib, path):
    try:
        reply = _call(bus, Gio, GLib, path, PROPERTIES_IFACE, "Get",
                      GLib.Variant("(ss)", (COLLECTION_IFACE, "Label")),
                      GLib.VariantType("(v)"))
    except SecretError:
        return None
    return reply.unpack()[0]


def find_collection(label=COLLECTION_LABEL):
    """Object path of the collection with this label, or None."""
    bus, Gio, GLib = _bus()
    for path in _collections(bus, Gio, GLib):
        if _label(bus, Gio, GLib, path) == label:
            return path
    return None


def is_locked(path):
    bus, Gio, GLib = _bus()
    reply = _call(bus, Gio, GLib, path, PROPERTIES_IFACE, "Get",
                  GLib.Variant("(ss)", (COLLECTION_IFACE, "Locked")),
                  GLib.VariantType("(v)"))
    return bool(reply.unpack()[0])


def create_secure_collection(password, label=COLLECTION_LABEL):
    """A collection with its own password, created without a GUI prompt."""
    if not password:
        raise SecretError("a keyring password is required.")
    bus, Gio, GLib = _bus()
    session = _open_session(bus, Gio, GLib)
    properties = {COLLECTION_IFACE + ".Label": GLib.Variant("s", label)}
    master = (session, b"", password.encode("utf-8"), "text/plain")
    reply = _call(bus, Gio, GLib, SECRETS_ROOT, GUILT_IFACE,
                  "CreateWithMasterPassword",
                  GLib.Variant("(a{sv}(oayays))", (properties, master)),
                  GLib.VariantType("(o)"))
    return reply.unpack()[0]


def unlock(password, path=None):
    """Unlock without a prompt. Wrong password raises, so the caller can say so
    rather than leaving a dialog to explain it."""
    bus, Gio, GLib = _bus()
    target = path or find_collection()
    if not target:
        raise SecretError("no %s keyring exists; run setup --secure-keyring."
                          % COLLECTION_LABEL)
    if not is_locked(target):
        # gnome-keyring accepts any password for a collection that is already
        # open, so without this an unlock with the wrong password would report
        # success and teach the user the wrong password.
        return target
    session = _open_session(bus, Gio, GLib)
    master = (session, b"", (password or "").encode("utf-8"), "text/plain")
    try:
        _call(bus, Gio, GLib, SECRETS_ROOT, GUILT_IFACE, "UnlockWithMasterPassword",
              GLib.Variant("(o(oayays))", (target, master)), None)
    except SecretError as error:
        # gnome-keyring answers a bad password with a D-Bus error name and a
        # stack-shaped string; the person typing deserves the short version.
        if "Denied" in str(error) or "password was invalid" in str(error):
            raise SecretError("wrong password.")
        raise
    if is_locked(target):
        raise SecretError("the keyring is still locked; wrong password?")
    return target


def lock(path=None):
    bus, Gio, GLib = _bus()
    target = path or find_collection()
    if not target:
        return None
    _call(bus, Gio, GLib, SECRETS_ROOT, SERVICE_IFACE, "Lock",
          GLib.Variant("(ao)", ([target],)), GLib.VariantType("(aoo)"))
    return target


def delete_collection(path=None):
    bus, Gio, GLib = _bus()
    target = path or find_collection()
    if not target:
        return None
    _call(bus, Gio, GLib, target, COLLECTION_IFACE, "Delete", None,
          GLib.VariantType("(o)"))
    return target


# --- token storage ----------------------------------------------------------

def _attributes():
    return ["service", SERVICE_ID, "account", ACCOUNT]


def store(token, collection=None, runner=subprocess.run):
    """The token travels on stdin, never in argv -- argv is world-readable in
    /proc and lands in shell history."""
    command = ["secret-tool", "store", "--label=" + COLLECTION_LABEL]
    if collection:
        command.append("--collection=" + collection)
    command.extend(_attributes())
    try:
        result = runner(command, input=token, text=True, check=False,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    except FileNotFoundError:
        raise SecretError("secret-tool is not installed (package: libsecret).")
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SecretError("could not reach the secret service (%s)." % error)
    if result.returncode != 0:
        raise SecretError((result.stderr or "").strip()
                          or "the secret service refused to store the token.")
    return True


def clear(runner=subprocess.run):
    command = ["secret-tool", "clear"] + _attributes()
    try:
        runner(command, check=False, stdout=subprocess.DEVNULL,
               stderr=subprocess.DEVNULL, timeout=30)
    except (OSError, subprocess.TimeoutExpired, FileNotFoundError):
        return False
    return True


def secure_ready():
    """(path, problem). A problem is a sentence for the user; path is None when
    there is one. Called before any lookup in secure mode, so that a locked
    collection is reported rather than waiting on a dialog."""
    try:
        path = find_collection()
    except SecretError as error:
        return None, str(error)
    if not path:
        return None, ("the %s keyring is missing; run setup --secure-keyring "
                      "again." % COLLECTION_LABEL)
    try:
        if is_locked(path):
            return None, ("the %s keyring is locked; unlock it with: setup "
                          "--unlock" % COLLECTION_LABEL)
    except SecretError as error:
        return None, str(error)
    return path, None


def describe_failure(has_secret_tool=True):
    """Why a lookup came back empty, in the words the user needs.

    `secret-tool lookup` exits 1 with no output whether the item is absent, the
    keyring daemon is dead, or there is no session bus at all. Telling someone
    with a broken keyring to 'run setup first' sends them round a loop, so this
    runs only on the failure branch and pays for the D-Bus round trip there."""
    if not has_secret_tool:
        return "secret-tool is not installed (package: libsecret); install it and run setup."
    try:
        _gi()
    except SecretError:
        # Without PyGObject there is no way to ask D-Bus anything, and the
        # default keyring path never needed it. Blaming a missing optional
        # package for what is almost always a missing token would send the
        # user off installing something they do not need.
        return "Toggl API token not found; run setup first."
    try:
        _bus()
    except SecretError as error:
        return str(error)
    if not service_running():
        return ("no secret service is running; start gnome-keyring-daemon "
                "(or another Secret Service provider) and run setup.")
    if mode() == MODE_SECURE:
        _, problem = secure_ready()
        if problem:
            return problem
    return "Toggl API token not found; run setup first."


# --- command line -----------------------------------------------------------
# `setup` drives the D-Bus work through this. Passwords arrive on stdin and
# never in argv, which is world-readable in /proc and lands in shell history.

USAGE = """usage: toggl_secret.py <command>

  mode                  print 'default' or 'secure'
  set-mode <mode>       record which keyring holds the token
  path                  print the protected collection's object path
  create                create the protected collection (password on stdin)
  unlock                unlock it (password on stdin)
  lock                  lock it
  delete                delete it and everything in it
  ready                 exit 0 if a lookup would succeed without a prompt
"""


def main(argv=None):
    import sys

    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        sys.stderr.write(USAGE)
        return 2
    command, rest = argv[0], argv[1:]
    try:
        if command == "mode":
            sys.stdout.write(mode() + "\n")
        elif command == "set-mode":
            if not rest:
                sys.stderr.write(USAGE)
                return 2
            set_mode(rest[0])
        elif command == "path":
            path = find_collection()
            if not path:
                return 1
            sys.stdout.write(path + "\n")
        elif command == "create":
            sys.stdout.write(create_secure_collection(sys.stdin.read().strip("\n")) + "\n")
        elif command == "unlock":
            unlock(sys.stdin.read().strip("\n"))
        elif command == "lock":
            lock()
        elif command == "delete":
            delete_collection()
        elif command == "ready":
            _, problem = secure_ready()
            if problem:
                sys.stderr.write(problem + "\n")
                return 1
        else:
            sys.stderr.write(USAGE)
            return 2
    except SecretError as error:
        sys.stderr.write(str(error) + "\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
