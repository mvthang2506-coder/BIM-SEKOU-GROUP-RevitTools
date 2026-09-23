# -*- coding: utf-8 -*-

from pyrevit import forms
from pyrevit.loader import sessionmgr
from pyrevit import script
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


def run_git_pull():

    try:
        process = subprocess.Popen(
            [
                "git",
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


# ------------------------------------------------------------
# Update
# ------------------------------------------------------------

return_code, output = run_git_pull()


# ------------------------------------------------------------
# Error
# ------------------------------------------------------------

if return_code != 0:

    forms.alert(
        "Không thể cập nhật BIM SEKOU GROUP Tools.\n\n"
        + output,
        title="BIM SEKOU GROUP - Update Error"
    )

else:

    # --------------------------------------------------------
    # Reload pyRevit
    # --------------------------------------------------------

    sessionmgr.reload_pyrevit()