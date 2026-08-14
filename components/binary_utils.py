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

        # Check the DLLs survey2gis ships next to the exe.
        bin_dir = os.path.dirname(binary_path)
        required_dlls = [
            "libglib-2.0-0.dll",
            "libgobject-2.0-0.dll",
            "libiconv-2.dll",
            "libintl-8.dll",
            "zlib1.dll",
        ]
        for dll in required_dlls:
            present = os.path.isfile(os.path.join(bin_dir, dll))
            info["dependencies"].append((dll, present))
            if not present:
                info["notes"].append(f"Missing runtime dependency: {dll}")
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
        if os.access(binary_path, os.X_OK):
            return True, msg
        return False, (
            f"chmod ran but binary still not executable: {binary_path}"
        )
    except OSError as error:
        return False, (
            f"Could not set executable permissions for {binary_path}: {error}"
        )
