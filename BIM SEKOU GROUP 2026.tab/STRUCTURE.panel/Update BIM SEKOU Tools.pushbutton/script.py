# -*- coding: utf-8 -*-

from pyrevit import forms
from pyrevit.loader import sessionmgr
import os
import subprocess


# ============================================================
# BIM SEKOU GROUP - Update Tools
# ============================================================

EXTENSION_ROOT = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        ".."
    )
)

REPO_URL = "https://github.com/mvthang2506-coder/BIM-SEKOU-GROUP-RevitTools.git"


# ============================================================
# Find Git
# ============================================================

def find_git():

    # Git available in PATH
    try:
        result = subprocess.Popen(
            ["git", "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        result.communicate()

        if result.returncode == 0:
            return "git"

    except:
        pass

    # Standard Git installation
    git_paths = [
        r"C:\Program Files\Git\cmd\git.exe",
        r"C:\Program Files\Git\bin\git.exe",
        r"C:\Program Files (x86)\Git\cmd\git.exe",
        r"C:\Program Files (x86)\Git\bin\git.exe"
    ]

    for git_path in git_paths:

        if os.path.exists(git_path):
            return git_path

    return None


# ============================================================
# Git Pull
# ============================================================

def run_git_pull(git_exe):

    try:

        process = subprocess.Popen(
            [
                git_exe,
                "-C",
                EXTENSION_ROOT,
                "pull",
                "origin",
                "master"
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )

        output = process.communicate()[0]

        try:
            output = output.decode("utf-8")
        except:
            output = output.decode("mbcs", errors="replace")

        return process.returncode, output

    except Exception as ex:

        return -1, str(ex)


# ============================================================
# Main
# ============================================================

# ------------------------------------------------------------
# Find Git
# ------------------------------------------------------------

git_exe = find_git()


if not git_exe:

    forms.alert(
        "Không tìm thấy Git trên máy này.\n\n"
        "Vui lòng cài Git trước khi sử dụng chức năng Update.",
        title="BIM SEKOU GROUP - Update Error"
    )

else:

    # --------------------------------------------------------
    # Update
    # --------------------------------------------------------

    return_code, output = run_git_pull(git_exe)


    # --------------------------------------------------------
    # Error
    # --------------------------------------------------------

    if return_code != 0:

        forms.alert(
            "Không thể cập nhật BIM SEKOU GROUP Tools.\n\n"
            + output,
            title="BIM SEKOU GROUP - Update Error"
        )

    else:

        # ----------------------------------------------------
        # Success
        # ----------------------------------------------------

        forms.alert(
            "BIM SEKOU GROUP Tools đã được cập nhật.\n\n"
            "Git:\n"
            + git_exe
            + "\n\n"
            + output,
            title="BIM SEKOU GROUP - Update Complete"
        )

        # ----------------------------------------------------
        # Reload pyRevit
        # ----------------------------------------------------

        sessionmgr.reload_pyrevit()