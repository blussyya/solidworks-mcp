"""
connection.py — manages the single COM connection to SolidWorks and resolves
SolidWorks API enum constants (swEndConditions_e, swDocumentTypes_e, etc.)

SolidWorks automation over COM is inherently single-threaded: only one thread
should ever touch the SldWorks.Application object. This module keeps a single
process-wide connection and every tool call goes through it sequentially,
which matches how a person driving the SolidWorks UI works anyway.

Why this isn't a plain `gencache.EnsureDispatch("SldWorks.Application")`
--------------------------------------------------------------------------
That's the normal, correct way to get an early-bound (properly typed) COM
wrapper — and it's what this module still produces. But on this machine (and
apparently not an isolated case — see SolidWorks API forum threads on this
exact error), calling EnsureDispatch directly on the *live* Application
object fails:

    TypeError: This COM object can not automate the makepy process -
    please run makepy manually for this object

The underlying cause, confirmed by testing: the live SldWorks.Application
object's IDispatch::GetTypeInfo() call itself fails ("Element not found"),
which is what EnsureDispatch uses to identify which generated module to bind
to. It's not a registry/gencache-cache problem — clearing the gen_py cache
and retrying doesn't help, because the live object never successfully
answers "what's your type info" in the first place.

Plain late-bound `Dispatch("SldWorks.Application")` sidesteps that (it
doesn't need GetTypeInfo up front) and connects fine. But late-bound calls
without any type info have a real footgun: pywin32's dynamic dispatch can't
tell a zero-argument *method* (e.g. `EditRebuild3()`) from a *property*, so
attribute access alone triggers it, and the subsequent `()` in the caller's
code then tries to call whatever value came back — a confusing runtime
error, and it affects nearly every method call in this codebase.

The fix used here: load the SolidWorks type library directly from its file
path (bypassing the registry lookup that EnsureDispatch's automatic version
detection was tripping over), generate the win32com wrapper module from that
file directly, and then manually wrap the live (plain-Dispatch) COM objects
in the generated wrapper classes. This gives every subsequent call full,
correct early-bound behavior — proper method/property distinction, correct
return-type wrapping for nested objects (SketchManager, FeatureManager,
Extension, etc. all come back correctly typed once the top-level app and
active document are wrapped) — without ever needing the live object to
answer GetTypeInfo().

Which install, and which type library
--------------------------------------------------------------------------
Both of those choices have to be made explicitly, because getting either
one wrong fails *silently* rather than loudly:

  * The bare "SldWorks.Application" ProgID belongs to whichever install
    registered it last. With two SolidWorks versions installed side by side
    it can point at the older one, and since every interface name is
    identical you simply end up driving a different application than you
    think you are.

  * The registry's generic "1.0" TypeLib entry likewise names only one
    install. Generating wrappers from one version's type library and then
    calling a different version's live objects through them does not
    reliably raise — mismatched dispatch IDs can land on the wrong member.

So: resolve a version-specific ProgID (see resolve_target), then load the
sldworks.tlb sitting next to whatever executable that actually gave us.

If any step of that (file-based generation) fails on a given machine, this
falls back to plain late-bound Dispatch with the hard-coded constants table
below, so the server keeps working, just with the method/property caveat.

Reference: https://help.solidworks.com/2022/english/api/swconst/
"""

import logging
import os
from typing import Optional

logger = logging.getLogger("solidworks_mcp")

SW_TYPELIB_CLSID = "{83A33D31-27C5-11CE-BFD4-00400513BB57}"  # "SOLIDWORKS OLE Automation 1.0 Type Library"

# -- Which SolidWorks this server drives ---------------------------------
#
# Never dispatch the bare "SldWorks.Application" ProgID. It belongs to
# whichever install registered it last, which is NOT necessarily the newest
# one. On the machine this was developed against, SolidWorks 2011 and 2022
# are installed side by side and the bare ProgID resolved to *2011* — so a
# server that believed it was driving 2022 silently drove 2011 instead.
# Nothing errors when that happens: the interface names are the same, so you
# just get a different application quietly building your geometry.
#
# Instead we resolve a version-specific ProgID, "SldWorks.Application.<major>",
# and dispatch only that. The major number maps to the release year as:
#
#     year = 1992 + major      (19 -> 2011, 30 -> 2022, 31 -> 2023, ...)
#
# This server is the SolidWorks 2011 one: it is pinned to major 19 and will
# not attach to anything else, not even as a fallback. The modern line has
# its own server (claude/ and opencode/ in this repo, registered as
# "solidworks") precisely so that neither side has to guess which install
# it got.
SW_MIN_MAJOR = 19            # pinned: SolidWorks 2011 only
SW_MAX_MAJOR = 19            # pinned: never attach to a newer line
SW_PROGID_ENV = "SOLIDWORKS_MCP_PROGID"   # escape hatch: force one exact ProgID

# Range probed when discovering installed versions. Cheap direct key opens,
# rather than enumerating all of HKEY_CLASSES_ROOT (which is enormous).
_MAJOR_PROBE_RANGE = range(19, 61)   # SW2011 .. SW2052, generous headroom

# Hard-coded SolidWorks API enum values, used as a fallback when the typed
# module isn't available (see get_const below) and always used for a few
# values that are genuinely just bitmask/enum ints rather than COM members.
# Grouped by confidence:
#
#   HIGH   — confirmed against SolidWorks API documentation and/or matched
#            exactly against a real published macro example.
#   MEDIUM — well-established community knowledge, not independently
#            re-verified for this project.
_CONSTANTS = {
    # swDocumentTypes_e — HIGH
    "swDocNONE": 0,
    "swDocPART": 1,
    "swDocASSEMBLY": 2,
    "swDocDRAWING": 3,
    # swEndConditions_e — HIGH
    "swEndCondBlind": 0,
    "swEndCondThroughAll": 1,
    "swEndCondThroughNext": 2,
    "swEndCondUpToVertex": 3,
    "swEndCondUpToSurface": 4,
    "swEndCondOffsetFromSurface": 5,
    "swEndCondUpToBody": 6,
    "swEndCondMidPlane": 7,
    "swEndCondThroughAllBoth": 8,
    # swStartConditions_e — MEDIUM
    "swStartSketchPlane": 0,
    "swStartOffset": 1,
    "swStartSurface": 2,
    # swBodyType_e — MEDIUM
    "swSolidBody": 0,
    "swSheetBody": 1,
    # swCustomInfoType_e — MEDIUM
    "swCustomInfoText": 30,
    "swCustomInfoNumber": 3,
    "swCustomInfoDouble": 10,
    "swCustomInfoYesOrNo": 11,
    "swCustomInfoDate": 64,
    # swCustomPropertyAddOption_e — MEDIUM
    "swCustomPropertyOnlyIfNew": 0,
    "swCustomPropertyDeleteAndAdd": 1,
    "swCustomPropertyReplaceValue": 2,
    # swOpenDocOptions_e (bitmask) — MEDIUM
    "swOpenDocOptions_Silent": 1,
    "swOpenDocOptions_ReadOnly": 2,
    # swStandardViews_e — MEDIUM
    "swFrontView": 1,
    "swBackView": 2,
    "swLeftView": 3,
    "swRightView": 4,
    "swTopView": 5,
    "swBottomView": 6,
    "swIsometricView": 7,
    "swTrimetricView": 8,
    "swDimetricView": 9,
    # swChamferType_e — LOW/MEDIUM (sw_feature_chamfer is already flagged
    # BEST-EFFORT in its docstring; this is the least-confident entry here)
    "swChamferAngleDistance": 1,
}


class SolidWorksNotConnectedError(RuntimeError):
    pass


def _select_by_id2(model, name: str, sel_type: str, x: float, y: float, z: float,
                   append: bool, mark: int) -> bool:
    """SelectByID2 with SW2011 COM compatibility.

    SW2011's COM interface requires integer booleans (0/1) and a VT_DISPATCH
    variant for the Callout parameter.
    """
    import pythoncom
    from win32com.client import VARIANT
    ext = model.Extension
    callout = VARIANT(pythoncom.VT_DISPATCH, None)
    return bool(ext.SelectByID2(
        name, sel_type, x, y, z,
        1 if append else 0, mark, callout, 0,
    ))


def year_for_major(major: Optional[int]) -> Optional[int]:
    """Release year for a SolidWorks API major number (19 -> 2011, 30 -> 2022)."""
    return None if major is None else 1992 + major


def _install_dir(path):
    """Directory of a SolidWorks install, given either its executable path or
    the directory itself.

    These two sources disagree in practice: the registry's LocalServer32 gives
    a full path to sldworks.exe, while ISldWorks.GetExecutablePath() — despite
    the name — returns the install *directory*. Taking os.path.dirname() of the
    latter would climb one level too far and quietly miss the type library.
    """
    if not path:
        return None
    path = path.strip().strip('"')
    d = path if os.path.isdir(path) else os.path.dirname(path)
    # realpath also expands 8.3 short names, which matters here: the registry
    # stores e.g. C:\PROGRA~1\SOLIDW~1\SOLIDW~1 while SolidWorks itself
    # reports the long form, and comparing the two raw would always disagree.
    try:
        return os.path.normpath(os.path.realpath(d))
    except OSError:
        return os.path.normpath(d)


def _progid_exe_path(progid: str) -> Optional[str]:
    """The .exe a ProgID actually launches, via its CLSID's LocalServer32
    registration.

    This is how we can state, without guessing, *which install* a given
    ProgID will hand us — and it's what picks the matching type library.
    """
    import winreg

    try:
        clsid = winreg.QueryValue(winreg.HKEY_CLASSES_ROOT, f"{progid}\\CLSID")
    except OSError:
        return None
    if not clsid:
        return None
    try:
        raw = winreg.QueryValue(winreg.HKEY_CLASSES_ROOT, f"CLSID\\{clsid}\\LocalServer32")
    except OSError:
        return None
    if not raw:
        return None
    # LocalServer32 may be quoted and may carry trailing arguments.
    raw = raw.strip()
    if raw.startswith('"'):
        end = raw.find('"', 1)
        path = raw[1:end] if end > 0 else raw[1:]
    else:
        # Unquoted: split off anything after ".exe".
        low = raw.lower()
        cut = low.find(".exe")
        path = raw[: cut + 4] if cut >= 0 else raw
    try:
        return os.path.normpath(os.path.abspath(path))
    except Exception:
        return path


def discover_installs() -> "list[tuple[int, str, Optional[str]]]":
    """Every version-specific SolidWorks ProgID registered on this machine.

    Returns [(major, progid, exe_path), ...], newest first.
    """
    import winreg

    found = []
    for major in _MAJOR_PROBE_RANGE:
        progid = f"SldWorks.Application.{major}"
        try:
            winreg.QueryValue(winreg.HKEY_CLASSES_ROOT, f"{progid}\\CLSID")
        except OSError:
            continue
        found.append((major, progid, _progid_exe_path(progid)))
    found.sort(key=lambda row: row[0], reverse=True)
    return found


def resolve_target() -> "tuple[str, Optional[str], Optional[int]]":
    """Pick which SolidWorks install this server will drive.

    Returns (progid, exe_path, major). Raises RuntimeError with an
    actionable message when nothing in range is installed — deliberately
    rather than silently falling back to the bare ProgID, because that
    fallback is exactly how you end up driving the wrong version.
    """
    forced = os.environ.get(SW_PROGID_ENV)
    if forced:
        major = None
        tail = forced.rsplit(".", 1)[-1]
        if tail.isdigit():
            major = int(tail)
        logger.info("Using SolidWorks ProgID forced via %s: %s", SW_PROGID_ENV, forced)
        return forced, _progid_exe_path(forced), major

    installs = discover_installs()
    if not installs:
        raise RuntimeError(
            "No version-specific SolidWorks ProgID (SldWorks.Application.<major>) is "
            "registered on this machine, so there's no way to target a specific "
            "install. Check that SolidWorks is installed, or set "
            f"{SW_PROGID_ENV} to the ProgID you want to use."
        )

    in_range = [
        row for row in installs
        if (SW_MIN_MAJOR is None or row[0] >= SW_MIN_MAJOR)
        and (SW_MAX_MAJOR is None or row[0] <= SW_MAX_MAJOR)
    ]
    if not in_range:
        available = ", ".join(f"{p} (SolidWorks {year_for_major(m)})" for m, p, _ in installs)
        wanted = f"major >= {SW_MIN_MAJOR}" if SW_MAX_MAJOR is None else f"major {SW_MIN_MAJOR}-{SW_MAX_MAJOR}"
        raise RuntimeError(
            f"This server targets SolidWorks {wanted}, but the only installs registered "
            f"here are: {available}. Use the server built for that version (the modern "
            f"line is served by claude/ and opencode/ in this repo, registered as "
            f"\"solidworks\"), or set {SW_PROGID_ENV} to override."
        )

    major, progid, exe_path = in_range[0]
    return progid, exe_path, major


def _load_typed_module(exe_path: Optional[str] = None):
    """Build the early-bound win32com wrapper module for the SolidWorks type
    library, loading it directly from its file path rather than through the
    registry-version lookup EnsureModule/EnsureDispatch normally use (see the
    module docstring for why that lookup fails on this API).

    IMPORTANT: load the .tlb belonging to the install we are *actually*
    driving. The registry's generic "1.0" TypeLib pointer names only one
    install, and on a multi-version machine that can easily be a different
    one — binding 2022 objects through a wrapper generated from a 2011 type
    library does not reliably raise, it can just as well invoke the wrong
    member. So the caller passes the live executable's path and we take the
    sldworks.tlb sitting next to it; the registry lookup is a last resort.

    Returns the generated module, or None if any step fails.
    """
    try:
        import winreg
        import pythoncom
        from win32com.client import makepy, gencache

        tlb_path = None

        # Preferred: the type library shipped inside the install we're on.
        install_dir = _install_dir(exe_path)
        if install_dir:
            candidate = os.path.join(install_dir, "sldworks.tlb")
            if os.path.exists(candidate):
                tlb_path = candidate
            else:
                logger.warning(
                    "No sldworks.tlb in %s; falling back to the registry's "
                    "generic TypeLib pointer, which may name a different install.",
                    install_dir,
                )

        # Fallback: the registry's win32 (32-bit) key — present regardless of
        # the *process's* bitness, since this is just reading metadata about
        # where the file lives, not loading a binary.
        if tlb_path is None:
            for arch_key in ("win32", "win64"):
                try:
                    key = winreg.OpenKey(
                        winreg.HKEY_CLASSES_ROOT,
                        f"TypeLib\\{SW_TYPELIB_CLSID}\\1.0\\409\\{arch_key}",
                    )
                    tlb_path = winreg.QueryValue(key, None)
                    break
                except OSError:
                    continue

        if not tlb_path or not os.path.exists(tlb_path):
            logger.info("Could not locate SolidWorks type library file for typed binding.")
            return None

        tlb = pythoncom.LoadTypeLib(tlb_path)
        # The typelib's own internal version (e.g. 30.0 for SolidWorks 2022),
        # which is what actually matters — the registry entry can carry a
        # stale version number from an older install.
        attrs = tlb.GetLibAttr()
        major, minor, lcid = attrs[3], attrs[4], attrs[1]
        logger.info("Bound SolidWorks type library %s (v%s.%s)", tlb_path, major, minor)

        makepy.GenerateFromTypeLibSpec(tlb)
        mod = gencache.EnsureModule(SW_TYPELIB_CLSID, lcid, major, minor)
        return mod
    except Exception as exc:
        logger.info("Typed SolidWorks module unavailable, falling back to late-bound only: %s", exc)
        return None


class SolidWorksConnection:
    """Process-wide singleton wrapping the SldWorks.Application COM object."""

    _instance: Optional["SolidWorksConnection"] = None

    def __init__(self) -> None:
        self.sw_app = None
        self._com_ready = False
        self._typed_module = None  # set on first successful connect()
        self._sw_version: Optional[int] = None  # major year, e.g. 2011, 2022
        # What we actually ended up attached to, so tools can report it
        # instead of anyone having to infer the version from behaviour.
        self.progid: Optional[str] = None
        self.exe_path: Optional[str] = None
        self.major: Optional[int] = None
        # Sketch/feature entities created by the most recent sketch tool call,
        # so a follow-up tool (e.g. "dimension the thing I just drew") can
        # reference them without a fragile by-name re-selection. Reset each
        # time a new sketch entity is created.
        self.last_entities: list = []

    @classmethod
    def instance(cls) -> "SolidWorksConnection":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # -- COM lifecycle ----------------------------------------------------

    def _ensure_com(self) -> None:
        if self._com_ready:
            return
        import pythoncom

        pythoncom.CoInitialize()
        self._com_ready = True

    def connect(self, visible: bool = True, launch_if_needed: bool = True) -> object:
        """Attach to a running SolidWorks 2011, or launch it if needed.

        Pinned to the 2011 line (major 19) and deliberately without a
        fallback: attaching to whatever else answers is how you end up
        driving the wrong application without noticing.
        """
        self._ensure_com()
        import win32com.client

        # If we already hold a live app object, reuse it. RevisionNumber may
        # come back as a bound method (typed wrapper) or a plain value
        # (late-bound fallback, where attribute access alone already
        # invoked it) — handle both.
        if self.sw_app is not None:
            try:
                rev = self.sw_app.RevisionNumber
                if callable(rev):
                    rev = rev()
                if not rev:
                    raise RuntimeError("empty revision")
                return self.sw_app
            except Exception:
                self.sw_app = None  # stale handle (SW was closed) — reconnect below

        progid, exe_path, major = resolve_target()

        try:
            raw_app = win32com.client.Dispatch(progid)
        except Exception as exc:
            raise RuntimeError(
                f"Could not start or attach to SolidWorks via COM using {progid} "
                f"(SolidWorks {year_for_major(major)}, {exe_path or 'path unknown'}). "
                "Make sure SolidWorks 2011 is installed on this machine and that "
                "this server is running on Windows (not WSL/Linux). "
                f"Underlying error: {exc}"
            ) from exc

        # Confirm what COM actually handed us. The ProgID says which install
        # *should* answer; this says which one did. Worth surfacing loudly
        # rather than discovering later via wrong geometry.
        live_exe = None
        try:
            ep = raw_app.GetExecutablePath
            live_exe = ep() if callable(ep) else ep
        except Exception:
            logger.warning("Could not read the live SolidWorks executable path.")

        live_dir, expected_dir = _install_dir(live_exe), _install_dir(exe_path)
        if live_dir and expected_dir and os.path.normcase(live_dir) != os.path.normcase(expected_dir):
            logger.warning(
                "%s was expected to launch %s but COM returned an instance running "
                "%s — binding to the instance we actually got.",
                progid, exe_path, live_exe,
            )

        self.progid = progid
        self.major = major
        self.exe_path = live_exe or exe_path

        if self._typed_module is None:
            self._typed_module = _load_typed_module(self.exe_path)

        if self._typed_module is not None:
            try:
                self.sw_app = self._typed_module.ISldWorks(raw_app._oleobj_)
            except Exception:
                logger.warning("Could not wrap SldWorks.Application in typed module; using late-bound object.")
                self.sw_app = raw_app
        else:
            self.sw_app = raw_app

        try:
            self.sw_app.Visible = visible
        except Exception:
            logger.warning("Could not set SolidWorks window visibility.")

        return self.sw_app

    @property
    def sw_version(self) -> int:
        """Return the major SolidWorks year (e.g. 2011, 2022). Cached after first call."""
        if self._sw_version is not None:
            return self._sw_version
        try:
            rev = self.sw_app.RevisionNumber
            if callable(rev):
                rev = rev()
            # RevisionNumber looks like "30.1.0" for SW2022, "19.1.0" for SW2011
            major = int(rev.split(".")[0])
            # Map API revision major to year: 19=2011, 20=2012, ..., 30=2022
            self._sw_version = 2000 + major - 11  # rev 19 → 2011-11=2000+19-11=2008? No.
            # Actually: SW2011 has API version ~19, SW2022 has ~30
            # Formula: year = 1992 + major (rev 19 → 2011, rev 30 → 2022)
            self._sw_version = 1992 + major
        except Exception:
            self._sw_version = 2022  # assume newest if detection fails
        return self._sw_version

    def try_method(self, obj, *method_names):
        """Try calling methods on obj by name (newest first). Returns the first that exists.
        Usage: feat = sw().try_method(model.FeatureManager, 'FeatureExtrusion3', 'FeatureExtrusion2', 'FeatureExtrusion')
        """
        for name in method_names:
            meth = getattr(obj, name, None)
            if meth is not None:
                return meth
        raise AttributeError(f"None of these methods exist on {obj}: {', '.join(method_names)}")

    @property
    def app(self):
        if self.sw_app is None:
            raise SolidWorksNotConnectedError(
                "Not connected to SolidWorks. Call the sw_connect tool first."
            )
        return self.sw_app

    def wrap_model(self, model):
        """Wrap a raw document object (returned from NewPart/NewDocument/
        OpenDoc6/ActiveDoc — all of which are declared as generic IDispatch
        in the SolidWorks API, so they don't auto-wrap even when the caller
        is already typed) in the typed IModelDoc2 class, so every downstream
        call on it (SketchManager, FeatureManager, Extension, EditRebuild3,
        GetTitle, ...) behaves like a normal, correctly-typed COM call.

        Safe to call on an already-wrapped model, or with None. Falls back
        to returning the object unchanged if typed wrapping isn't available.
        """
        if model is None or self._typed_module is None:
            return model
        try:
            return self._typed_module.IModelDoc2(model._oleobj_)
        except Exception:
            return model

    def active_doc(self):
        """Return the active ModelDoc2, raising a clear error if none is open."""
        model = self.app.ActiveDoc
        if model is None:
            raise RuntimeError(
                "No document is open in SolidWorks. Use sw_new_part / "
                "sw_new_assembly / sw_new_drawing / sw_open_document first."
            )
        return self.wrap_model(model)

    def disconnect(self, close_solidworks: bool = False) -> None:
        if self.sw_app is not None and close_solidworks:
            try:
                self.sw_app.ExitApp()
            except Exception:
                logger.warning("SolidWorks did not shut down cleanly.")
        self.sw_app = None


def get_const(name: str) -> int:
    """Resolve a SolidWorks API enum constant (e.g. 'swEndCondBlind') to its int value."""
    if name in _CONSTANTS:
        return _CONSTANTS[name]

    try:
        from win32com.client import constants as sw_constants

        return getattr(sw_constants, name)
    except (AttributeError, ImportError):
        pass

    raise RuntimeError(
        f"Unknown SolidWorks constant '{name}' — it's not in this project's hard-coded "
        f"table (connection.py) and live lookup isn't available either. Check spelling "
        f"against https://help.solidworks.com/2022/english/api/swconst/ and add it to "
        f"_CONSTANTS if it's correct."
    )


def sw() -> SolidWorksConnection:
    """Shorthand accessor used throughout the tools/ modules."""
    return SolidWorksConnection.instance()
