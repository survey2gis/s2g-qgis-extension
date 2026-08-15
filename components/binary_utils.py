# -*- coding: utf-8 -*-
"""
Shared helpers to locate the bundled survey2gis binary, check whether it is
executable, and make it executable in a cross-platform way.

This is the single source of truth for binary handling. Both the dockwidget
and the Logs-tab diagnostics use it, so the resolution logic can never drift
apart again.
"""

import os
import platform
import subprocess


def resolve_binary_path(base_path, global_override=None):
    """Return the absolute, normalized path to the survey2gis binary.

    :param base_path: directory the plugin lives in (dirname of the caller)
    :param global_override: optional path from the QGIS global var ``s2g_path``
    :returns: normalized path (may or may not exist on disk)
    """
    if global_override:
        return os.path.normpath(global_override)

    system = platform.system().lower()
    architecture = platform.machine().lower()

    if system == "windows":
        rel = ("survey2gis", "win32", "cli-only", "survey2gis.exe")
    elif system == "linux":
        rel = ("survey2gis", "linux64", "cli-only", "survey2gis")
    elif system == "darwin":
        if architecture in ("arm64", "aarch64"):
            macos_folder = "macosx-silicon"
        elif architecture in ("x86_64", "amd64"):
            macos_folder = "macosx"
        else:
            raise NotImplementedError(
                f"Unsupported macOS architecture: {architecture}"
            )
        rel = ("survey2gis", macos_folder, "cli-only", "survey2gis")
    else:
        raise NotImplementedError(
            f"Operating system '{system}' is not supported."
        )

    return os.path.normpath(os.path.join(base_path, *rel))


def inspect_binary(binary_path):
    """Collect diagnostic facts about the binary without changing anything.

    :returns: dict with keys: system, architecture, path, exists, is_file,
              size, executable, readable, mode_octal, dependencies (list of
              (name, present) for adjacent DLLs on Windows), notes (list of str)
    """
    system = platform.system().lower()
    info = {
        "system": system,
        "architecture": platform.machine().lower(),
        "path": binary_path,
        "exists": os.path.exists(binary_path),
        "is_file": os.path.isfile(binary_path),
        "size": None,
        "executable": False,
        "readable": False,
        "mode_octal": None,
        "dependencies": [],
        "notes": [],
    }

    if not info["is_file"]:
        info["notes"].append("Binary file does not exist at the resolved path.")
        return info

    try:
        st = os.stat(binary_path)
        info["size"] = st.st_size
        info["mode_octal"] = oct(st.st_mode & 0o777)
    except OSError as error:
        info["notes"].append(f"Could not stat binary: {error}")

    info["readable"] = os.access(binary_path, os.R_OK)

    if system == "windows":
        # On Windows every file with a valid PE header is "executable"; the
        # X_OK bit is not meaningful. What actually breaks execution is a
        # zero-byte / truncated download, a Zone.Identifier (Mark of the Web)
        # block, or missing sibling DLLs.
        info["executable"] = info["is_file"] and (info["size"] or 0) > 0

        if info["size"] == 0:
            info["notes"].append("Binary is 0 bytes - download is incomplete.")

        # Mark of the Web / blocked-file check.
        ads_path = binary_path + ":Zone.Identifier"
        try:
            if os.path.exists(ads_path):
                info["notes"].append(
                    "File carries a Zone.Identifier (Mark of the Web). "
                    "Windows may block execution. Use the unblock action."
                )
        except OSError:
            pass

        # List the DLLs that actually sit next to the exe. This is purely
        # informational: the cli-only build ships a different (smaller) set of
        # DLLs than the full GUI build, so a hard "required" list produces
        # false alarms. We only report what is there and never treat a missing
        # entry as a blocker.
        bin_dir = os.path.dirname(binary_path)
        try:
            found_dlls = sorted(
                name for name in os.listdir(bin_dir)
                if name.lower().endswith(".dll")
            )
        except OSError:
            found_dlls = []
        for dll in found_dlls:
            info["dependencies"].append((dll, True))
        if not found_dlls:
            info["notes"].append(
                "No DLLs found next to the exe. If the program fails to "
                "start, the runtime libraries may be missing."
            )
    else:
        info["executable"] = os.access(binary_path, os.X_OK)
        if not info["executable"]:
            info["notes"].append(
                "Binary lacks the executable bit. Use the "
                "'make executable' action or chmod +x it."
            )

    return info


def make_binary_executable(binary_path):
    """Make the binary runnable on the current platform.

    On Linux/macOS this sets the executable bits. On Windows it removes the
    Zone.Identifier (Mark of the Web) block if present.

    :returns: (success: bool, message: str)
    """
    system = platform.system().lower()

    if not os.path.isfile(binary_path):
        return False, f"Binary not found: {binary_path}"

    if system == "windows":
        ads_path = binary_path + ":Zone.Identifier"
        try:
            if os.path.exists(ads_path):
                os.remove(ads_path)
                return True, (
                    "Removed Zone.Identifier (unblocked the executable)."
                )
        except OSError as error:
            # Fall back to PowerShell Unblock-File.
            try:
                subprocess.run(
                    [
                        "powershell", "-NoProfile", "-Command",
                        f"Unblock-File -LiteralPath '{binary_path}'",
                    ],
                    check=True,
                    capture_output=True,
                    timeout=30,
                )
                return True, "Unblocked the executable via Unblock-File."
            except Exception as ps_error:  # noqa: BLE001
                return False, (
                    f"Could not unblock file: {error} / {ps_error}"
                )
        return True, "No block found - executable is ready to run."

    if system not in ("linux", "darwin"):
        return False, f"Unsupported operating system: {system}"

    try:
        current_mode = os.stat(binary_path).st_mode
        if not current_mode & 0o111:
            os.chmod(binary_path, current_mode | 0o111)
            msg = f"Set executable permissions for {binary_path}"
        else:
            msg = f"{binary_path} is already executable"

        # On macOS, also strip the Gatekeeper quarantine flag if present.
        # Without this the OS refuses to run a downloaded binary with
        # "cannot verify that survey2gis is free of malware".
        if system == "darwin":
            try:
                subprocess.run(
                    ["xattr", "-d", "com.apple.quarantine", binary_path],
                    capture_output=True,
                    timeout=15,
                )
                # xattr fails harmlessly if the attribute isn't set; that's fine.
                msg += " (and cleared macOS quarantine flag if present)"
            except Exception:  # noqa: BLE001
                pass

        if os.access(binary_path, os.X_OK):
            return True, msg
        return False, (
            f"chmod ran but binary still not executable: {binary_path}"
        )
    except OSError as error:
        return False, (
            f"Could not set executable permissions for {binary_path}: {error}"
        )


def test_run_binary(binary_path, timeout=15):
    """Actually launch the binary once to see whether it starts at all.

    Runs ``survey2gis --help``, which starts the program, prints usage and
    exits without needing any input files. We don't care about the exact
    output - what matters is whether the OS lets the binary run. This surfaces
    the failures that a permission/size check cannot see:

      * macOS Gatekeeper quarantine ("cannot verify that ... is free of
        malware") - the process is killed by signal SIGKILL (-9)
      * Windows missing DLLs - the process fails to start
      * Linux missing shared libraries - non-zero exit / OSError

    :returns: dict with keys: launched (bool), returncode, stdout, stderr,
              signal, message
    """
    import subprocess
    import platform as _platform

    result = {
        "launched": False,
        "returncode": None,
        "stdout": "",
        "stderr": "",
        "signal": None,
        "message": "",
    }

    if not os.path.isfile(binary_path):
        result["message"] = f"Binary not found: {binary_path}"
        return result

    try:
        completed = subprocess.run(
            [binary_path, "--help"],
            capture_output=True,
            timeout=timeout,
            cwd=os.path.dirname(binary_path) or None,
        )
        result["launched"] = True
        result["returncode"] = completed.returncode
        result["stdout"] = completed.stdout.decode("utf-8", errors="replace")
        result["stderr"] = completed.stderr.decode("utf-8", errors="replace")

        # A negative return code on POSIX means the process was killed by a
        # signal. On macOS a Gatekeeper block shows up as SIGKILL (-9).
        if completed.returncode is not None and completed.returncode < 0:
            sig = -completed.returncode
            result["signal"] = sig
            if _platform.system().lower() == "darwin" and sig == 9:
                result["message"] = (
                    "The binary was killed by the operating system (SIGKILL). "
                    "On macOS this is almost always Gatekeeper quarantine: "
                    "'cannot verify that survey2gis is free of malware'. "
                    "Remove the quarantine flag (see the 'make executable' "
                    "action) or allow it under System Settings > Privacy & "
                    "Security."
                )
            else:
                result["message"] = (
                    f"The binary was terminated by signal {sig}."
                )
        elif completed.returncode == 0:
            result["message"] = "Binary started and exited cleanly."
        else:
            # survey2gis returns non-zero for usage errors, which is still a
            # successful launch - the program clearly ran.
            result["message"] = (
                f"Binary started (exit code {completed.returncode})."
            )
        return result

    except subprocess.TimeoutExpired:
        result["message"] = (
            f"Binary did not respond within {timeout}s - it may be hanging "
            "or waiting for input."
        )
        return result
    except OSError as error:
        # Typical on Windows for missing DLLs, or a corrupt/blocked binary.
        result["message"] = (
            f"Operating system refused to launch the binary: {error}. "
            "On Windows this usually means a required DLL is missing; on "
            "macOS/Linux it can mean a missing shared library or a block."
        )
        return result
