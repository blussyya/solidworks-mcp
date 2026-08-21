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
detection was tripping over — the registered TypeLib entry here points at a
stale 1.0 version while the installed file is actually 30.0), generate the
win32com wrapper module from that file directly, and then manually wrap the
live (plain-Dispatch) COM objects in the generated wrapper classes. This
gives every subsequent call full, correct early-bound behavior — proper
method/property distinction, correct return-type wrapping for nested objects
(SketchManager, FeatureManager, Extension, etc. all come back correctly
typed once the top-level app and active document are wrapped) — without
ever needing the live object to answer GetTypeInfo().

If any step of that (file-based generation) fails on a given machine, this
falls back to plain late-bound Dispatch with the hard-coded constants table
below, so the server keeps working, just with the method/property caveat.

Reference: https://help.solidworks.com/2022/english/api/swconst/
"""

import logging
import os
from typing import Optional

logger = logging.getLogger("solidworks_mcp")

SW_APP_PROGID = "SldWorks.Application"
SW_TYPELIB_CLSID = "{83A33D31-27C5-11CE-BFD4-00400513BB57}"  # "SOLIDWORKS OLE Automation 1.0 Type Library"

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


def _load_typed_module():
    """Try to build the early-bound win32com wrapper module for the
    installed SolidWorks type library, loading it directly from its file
    path instead of going through the registry-version lookup that
    EnsureModule/EnsureDispatch normally use (see module docstring for why
    that lookup fails on this API).

    Returns the generated module, or None if any step fails.
    """
    try:
        import winreg
        import pythoncom
        from win32com.client import makepy, gencache

        # Find the .tlb file path from the registry's win32 (32-bit) key —
        # present regardless of the *process's* bitness, since this is just
        # reading metadata about where the file lives, not loading a binary.
        tlb_path = None
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
        # This reads the typelib's own internal version (e.g. 30.0 for
        # SolidWorks 2022), which is what actually matters — the registry
        # entry above can be a stale version number from an older install.
        attrs = tlb.GetLibAttr()
        major, minor, lcid = attrs[3], attrs[4], attrs[1]

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
        """Attach to a running SolidWorks 2022, or launch it if needed."""
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

        try:
            raw_app = win32com.client.Dispatch(SW_APP_PROGID)
        except Exception as exc:
            raise RuntimeError(
                "Could not start or attach to SolidWorks 2022 via COM. Make sure "
                "SolidWorks 2022 is installed on this machine and that this server "
                "is running on Windows (not WSL/Linux). "
                f"Underlying error: {exc}"
            ) from exc

        if self._typed_module is None:
            self._typed_module = _load_typed_module()

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
