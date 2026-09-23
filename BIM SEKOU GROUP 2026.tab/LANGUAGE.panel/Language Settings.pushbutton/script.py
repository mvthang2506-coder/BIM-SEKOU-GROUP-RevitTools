# -*- coding: utf-8 -*-

import clr
import os

clr.AddReference("System.Drawing")
clr.AddReference("System.Windows.Forms")

from System.Drawing import Font, Point, Size
from System.Windows.Forms import ComboBoxStyle
from System.Windows.Forms import (
    Form, Label, ComboBox, Button, MessageBox, ComboBoxStyle,
    MessageBoxButtons, MessageBoxIcon, FormStartPosition,
    FormBorderStyle
)

LANG_FILE = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")),
    "BIM_SEKOU_GROUP_language.txt"
)

LANGUAGES = [
    ("Tiếng Việt", "vi"),
    ("English", "en"),
    ("日本語", "ja")
]

def load_language():
    try:
        if os.path.exists(LANG_FILE):
            f = open(LANG_FILE, "r")
            value = f.read().strip()
            f.close()
            if value in ("vi", "en", "ja"):
                return value
    except:
        pass
    return "vi"

def save_language(value):
    f = open(LANG_FILE, "w")
    f.write(value)
    f.close()

class LanguageForm(Form):
    def __init__(self):
        Form.__init__(self)
        self.Text = "BIM SEKOU GROUP - Language Settings"
        self.Width = 460
        self.Height = 250
        self.StartPosition = FormStartPosition.CenterScreen
        self.FormBorderStyle = FormBorderStyle.FixedDialog
        self.MaximizeBox = False
        self.MinimizeBox = False

        title = Label()
        title.Text = "Language / 言語 / Ngôn ngữ"
        title.Font = Font("Arial", 16)
        title.AutoSize = True
        title.Location = Point(30, 25)
        self.Controls.Add(title)

        label = Label()
        label.Text = "Select language:"
        label.Font = Font("Arial", 11)
        label.AutoSize = True
        label.Location = Point(30, 75)
        self.Controls.Add(label)

        self.combo = ComboBox()
        self.combo.Location = Point(30, 105)
        self.combo.Size = Size(360, 30)
        self.combo.DropDownStyle = ComboBoxStyle.DropDownList
        self.Controls.Add(self.combo)

        current = load_language()
        current_index = 0
        for i, item in enumerate(LANGUAGES):
            self.combo.Items.Add(item[0])
            if item[1] == current:
                current_index = i
        self.combo.SelectedIndex = current_index

        apply_btn = Button()
        apply_btn.Text = "APPLY"
        apply_btn.Location = Point(30, 155)
        apply_btn.Width = 160
        apply_btn.Height = 40
        apply_btn.Click += self.apply
        self.Controls.Add(apply_btn)

        close_btn = Button()
        close_btn.Text = "CLOSE"
        close_btn.Location = Point(230, 155)
        close_btn.Width = 160
        close_btn.Height = 40
        close_btn.Click += self.close_form
        self.Controls.Add(close_btn)

    def apply(self, sender, args):
        index = self.combo.SelectedIndex
        if index < 0:
            return
        code = LANGUAGES[index][1]
        save_language(code)
        MessageBox.Show(
            "Language saved.\r\n\r\nPlease reopen Beam Direction Check to apply the new language.",
            "BIM SEKOU GROUP",
            MessageBoxButtons.OK,
            MessageBoxIcon.Information)

    def close_form(self, sender, args):
        self.Close()

try:
    LanguageForm().ShowDialog()
except Exception as error:
    MessageBox.Show(
        "Language Settings Error:\r\n\r\n{}".format(error),
        "BIM SEKOU GROUP",
        MessageBoxButtons.OK,
        MessageBoxIcon.Error)
