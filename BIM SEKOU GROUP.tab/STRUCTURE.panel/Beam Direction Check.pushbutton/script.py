# -*- coding: utf-8 -*-

import clr
import os

clr.AddReference("System")
clr.AddReference("System.Drawing")
clr.AddReference("System.Windows.Forms")
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from System import Array
from System.Drawing import Color, Font, Point, Size
from System.Windows.Forms import (
    Form, Label, Button, CheckedListBox, ListBox, MessageBox,
    MessageBoxButtons, MessageBoxIcon, Panel, FormStartPosition,
    FormBorderStyle, SelectionMode, DockStyle
)

from Autodesk.Revit.DB import (
    FilteredElementCollector, BuiltInCategory, FamilyInstance,
    LocationCurve, View3D, ViewFamilyType, ViewFamily,
    Transaction, OverrideGraphicSettings, Color as RevitColor,
    ElementId, BoundingBoxXYZ, XYZ
)

from pyrevit import revit

uidoc = revit.uidoc
doc = revit.doc

WINDOW_WIDTH = 850
WINDOW_HEIGHT = 650
VIEW_NAME = "BIM_Beam_Direction_Error"
BEAM_CATEGORY = BuiltInCategory.OST_StructuralFraming

beam_families = []
wrong_beams = []

LANG_FILE = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")),
    "BIM_SEKOU_GROUP_language.txt"
)

LANG = "vi"

TEXT = {
    "vi": {
        "title": "BIM SEKOU GROUP - Kiểm tra hướng dầm",
        "header": "KIỂM TRA HƯỚNG DẦM",
        "select_family": "Chọn Family dầm:",
        "select_all": "CHỌN TẤT CẢ",
        "clear_all": "BỎ CHỌN",
        "rule": "Quy tắc hướng:\r\n→ X+ = ĐÚNG\r\n↑ Y+ = ĐÚNG\r\n← X- = SAI\r\n↓ Y- = SAI",
        "check": "KIỂM TRA HƯỚNG",
        "close": "ĐÓNG",
        "result": "Kiểm tra hướng dầm - Kết quả",
        "wrong_title": "DẦM SAI HƯỚNG",
        "correct_title": "TẤT CẢ DẦM ĐỀU ĐÚNG",
        "total": "Tổng số dầm",
        "correct": "Đúng",
        "wrong": "Sai",
        "wrong_list": "Danh sách dầm sai hướng:",
        "select_wrong": "CHỌN DẦM SAI",
        "create_3d": "TẠO VIEW 3D",
        "selected": "{} dầm đã được chọn.",
        "no_wrong": "Không có dầm sai hướng.",
        "view_created": "Đã tạo View 3D:\r\n\r\n{}",
        "no_view_type": "Không tìm thấy 3D View Type.",
        "create_error": "Không thể tạo 3D View.\r\n\r\n{}",
        "select_error": "Không thể chọn dầm.\r\n\r\n{}",
        "choose_family": "Vui lòng chọn ít nhất một Family dầm.",
        "error": "Lỗi kiểm tra hướng dầm:\r\n\r\n{}",
    },
    "en": {
        "title": "BIM SEKOU GROUP - Beam Direction Check",
        "header": "BEAM DIRECTION CHECK",
        "select_family": "Select Beam Family:",
        "select_all": "SELECT ALL",
        "clear_all": "CLEAR ALL",
        "rule": "Direction rule:\r\n→ X+ = CORRECT\r\n↑ Y+ = CORRECT\r\n← X- = WRONG\r\n↓ Y- = WRONG",
        "check": "CHECK DIRECTION",
        "close": "CLOSE",
        "result": "Beam Direction Check - Result",
        "wrong_title": "WRONG BEAM DIRECTION",
        "correct_title": "ALL BEAMS CORRECT",
        "total": "Total beams",
        "correct": "Correct",
        "wrong": "Wrong",
        "wrong_list": "Wrong direction beams:",
        "select_wrong": "SELECT WRONG BEAMS",
        "create_3d": "CREATE 3D VIEW",
        "selected": "{} beams selected.",
        "no_wrong": "No wrong-direction beams.",
        "view_created": "3D View created:\r\n\r\n{}",
        "no_view_type": "3D View Type not found.",
        "create_error": "Could not create 3D View.\r\n\r\n{}",
        "select_error": "Could not select beams.\r\n\r\n{}",
        "choose_family": "Please select at least one beam Family.",
        "error": "Beam Direction Check Error:\r\n\r\n{}",
    },
    "ja": {
        "title": "BIM SEKOU GROUP - 梁方向チェック",
        "header": "梁方向チェック",
        "select_family": "梁ファミリを選択：",
        "select_all": "すべて選択",
        "clear_all": "選択解除",
        "rule": "方向ルール：\r\n→ X+ = 正しい\r\n↑ Y+ = 正しい\r\n← X- = 間違い\r\n↓ Y- = 間違い",
        "check": "方向を確認",
        "close": "閉じる",
        "result": "梁方向チェック - 結果",
        "wrong_title": "梁方向が間違っています",
        "correct_title": "すべての梁が正しい方向です",
        "total": "梁の総数",
        "correct": "正しい",
        "wrong": "間違い",
        "wrong_list": "方向が間違っている梁：",
        "select_wrong": "間違った梁を選択",
        "create_3d": "3Dビューを作成",
        "selected": "{} 本の梁を選択しました。",
        "no_wrong": "方向が間違っている梁はありません。",
        "view_created": "3Dビューを作成しました：\r\n\r\n{}",
        "no_view_type": "3Dビュータイプが見つかりません。",
        "create_error": "3Dビューを作成できません。\r\n\r\n{}",
        "select_error": "梁を選択できません。\r\n\r\n{}",
        "choose_family": "少なくとも1つの梁ファミリを選択してください。",
        "error": "梁方向チェックエラー：\r\n\r\n{}",
    }
}

def load_language():
    global LANG
    try:
        if os.path.exists(LANG_FILE):
            f = open(LANG_FILE, "r")
            value = f.read().strip()
            f.close()
            if value in TEXT:
                LANG = value
    except:
        pass
    return LANG

def tr(key):
    return TEXT.get(load_language(), TEXT["vi"]).get(key, key)

load_language()

def get_element_id_int(element):
    try:
        return element.Id.IntegerValue
    except:
        return -1

def get_family_name(beam):
    try:
        return beam.Symbol.Family.Name
    except:
        return ""

def get_type_name(beam):
    try:
        return beam.Symbol.Name
    except:
        return ""

def get_all_beams():
    collector = (FilteredElementCollector(doc)
                 .OfCategory(BEAM_CATEGORY)
                 .WhereElementIsNotElementType())
    result = []
    for element in collector:
        if not isinstance(element, FamilyInstance):
            continue
        try:
            location = element.Location
            if not isinstance(location, LocationCurve):
                continue
            if location.Curve is None:
                continue
            result.append(element)
        except:
            continue
    return result

def get_family_list():
    families = {}
    for beam in get_all_beams():
        name = get_family_name(beam)
        if name:
            families[name] = families.get(name, 0) + 1
    return sorted(families.items(), key=lambda x: x[0].lower())

def get_beam_direction(beam):
    try:
        curve = beam.Location.Curve
        p0 = curve.GetEndPoint(0)
        p1 = curve.GetEndPoint(1)
        dx = p1.X - p0.X
        dy = p1.Y - p0.Y
        tol = 1e-9
        if abs(dx) < tol and abs(dy) < tol:
            return "UNKNOWN"
        if abs(dx) >= abs(dy):
            return "RIGHT" if dx > 0 else "LEFT"
        return "UP" if dy > 0 else "DOWN"
    except:
        return "UNKNOWN"

def is_wrong_direction(beam):
    return get_beam_direction(beam) in ("LEFT", "DOWN")

def get_direction_symbol(direction):
    return {
        "RIGHT": "→",
        "UP": "↑",
        "LEFT": "←",
        "DOWN": "↓",
        "UNKNOWN": "?"
    }.get(direction, "?")

def get_beam_result_text(beam):
    return "{} | {} | {} | ID: {}".format(
        get_direction_symbol(get_beam_direction(beam)),
        get_family_name(beam),
        get_type_name(beam),
        get_element_id_int(beam)
    )

def get_unique_view_name():
    existing = set()
    for view in FilteredElementCollector(doc).OfClass(View3D):
        try:
            if not view.IsTemplate:
                existing.add(view.Name)
        except:
            pass
    if VIEW_NAME not in existing:
        return VIEW_NAME
    i = 2
    while True:
        name = "{}_{}".format(VIEW_NAME, i)
        if name not in existing:
            return name
        i += 1

def get_3d_view_type():
    for vt in FilteredElementCollector(doc).OfClass(ViewFamilyType):
        try:
            if vt.ViewFamily == ViewFamily.ThreeDimensional:
                return vt
        except:
            pass
    return None

def get_section_box_for_beams(beams):
    min_x = min_y = min_z = max_x = max_y = max_z = None
    for beam in beams:
        try:
            bbox = beam.get_BoundingBox(None)
            if bbox is None:
                continue
            if min_x is None:
                min_x, min_y, min_z = bbox.Min.X, bbox.Min.Y, bbox.Min.Z
                max_x, max_y, max_z = bbox.Max.X, bbox.Max.Y, bbox.Max.Z
            else:
                min_x = min(min_x, bbox.Min.X)
                min_y = min(min_y, bbox.Min.Y)
                min_z = min(min_z, bbox.Min.Z)
                max_x = max(max_x, bbox.Max.X)
                max_y = max(max_y, bbox.Max.Y)
                max_z = max(max_z, bbox.Max.Z)
        except:
            continue
    if min_x is None:
        return None
    padding = 2.0
    box = BoundingBoxXYZ()
    box.Min = XYZ(min_x-padding, min_y-padding, min_z-padding)
    box.Max = XYZ(max_x+padding, max_y+padding, max_z+padding)
    return box

def create_3d_view(beams):
    if not beams:
        MessageBox.Show(tr("no_wrong"), tr("header"),
                        MessageBoxButtons.OK, MessageBoxIcon.Information)
        return None
    view_type = get_3d_view_type()
    if view_type is None:
        MessageBox.Show(tr("no_view_type"), tr("header"),
                        MessageBoxButtons.OK, MessageBoxIcon.Error)
        return None
    t = Transaction(doc, "Create Beam Direction Error 3D View")
    try:
        t.Start()
        view = View3D.CreateIsometric(doc, view_type.Id)
        view.Name = get_unique_view_name()
        framing_category_id = ElementId(BuiltInCategory.OST_StructuralFraming).IntegerValue
        try:
            for category in doc.Settings.Categories:
                try:
                    if not category.AllowsVisibilityControl:
                        continue
                    if category.Id.IntegerValue == framing_category_id:
                        continue
                    if view.CanCategoryBeHidden(category.Id):
                        view.SetCategoryHidden(category.Id, True)
                except:
                    continue
        except:
            pass
        wrong_ids = set()
        for beam in beams:
            try:
                wrong_ids.add(beam.Id.IntegerValue)
            except:
                pass
        hide_ids = []
        all_framing = (FilteredElementCollector(doc)
                       .OfCategory(BEAM_CATEGORY)
                       .WhereElementIsNotElementType())
        for element in all_framing:
            try:
                if element.Id.IntegerValue not in wrong_ids:
                    hide_ids.append(element.Id)
            except:
                continue
        if hide_ids:
            try:
                view.HideElements(Array[ElementId](hide_ids))
            except:
                for element_id in hide_ids:
                    try:
                        view.HideElements(Array[ElementId]([element_id]))
                    except:
                        pass
        red = RevitColor(255, 0, 0)
        ogs = OverrideGraphicSettings()
        ogs.SetProjectionLineColor(red)
        ogs.SetCutLineColor(red)
        for beam in beams:
            try:
                view.SetElementOverrides(beam.Id, ogs)
            except:
                pass
        try:
            section_box = get_section_box_for_beams(beams)
            if section_box is not None:
                view.IsSectionBoxActive = True
                view.SectionBox = section_box
        except:
            pass
        t.Commit()
        try:
            uidoc.Selection.SetElementIds(Array[ElementId]([beam.Id for beam in beams]))
        except:
            pass
        uidoc.ActiveView = view
        return view
    except Exception as error:
        try:
            if t.HasStarted():
                t.RollBack()
        except:
            pass
        MessageBox.Show(tr("create_error").format(error), tr("header"),
                        MessageBoxButtons.OK, MessageBoxIcon.Error)
        return None

def select_beams(beams):
    try:
        uidoc.Selection.SetElementIds(Array[ElementId]([beam.Id for beam in beams]))
    except Exception as error:
        MessageBox.Show(tr("select_error").format(error), tr("header"),
                        MessageBoxButtons.OK, MessageBoxIcon.Error)

class ResultForm(Form):
    def __init__(self, target_beams, wrong_beams, correct_count):
        Form.__init__(self)
        self.target_beams = target_beams
        self.wrong_beams = wrong_beams
        self.Text = tr("result")
        self.Width = 900
        self.Height = 650
        self.StartPosition = FormStartPosition.CenterScreen
        self.FormBorderStyle = FormBorderStyle.FixedDialog
        self.MaximizeBox = False
        self.create_ui(correct_count)

    def create_ui(self, correct_count):
        header = Panel()
        header.Dock = DockStyle.Top
        header.Height = 90
        header.BackColor = (Color.FromArgb(190, 60, 40)
                            if self.wrong_beams
                            else Color.FromArgb(40, 140, 80))
        self.Controls.Add(header)
        title = Label()
        title.Text = tr("wrong_title") if self.wrong_beams else tr("correct_title")
        title.ForeColor = Color.White
        title.Font = Font("Arial", 20)
        title.AutoSize = True
        title.Location = Point(25, 25)
        header.Controls.Add(title)
        summary = Label()
        summary.Text = (
            "{}   : {}\r\n"
            "{}   : {}\r\n"
            "{}   : {}"
        ).format(tr("total"), len(self.target_beams),
                 tr("correct"), correct_count,
                 tr("wrong"), len(self.wrong_beams))
        summary.Font = Font("Arial", 12)
        summary.AutoSize = True
        summary.Location = Point(30, 110)
        self.Controls.Add(summary)
        label = Label()
        label.Text = tr("wrong_list")
        label.Font = Font("Arial", 11)
        label.AutoSize = True
        label.Location = Point(30, 190)
        self.Controls.Add(label)
        self.result_list = ListBox()
        self.result_list.Location = Point(30, 220)
        self.result_list.Size = Size(820, 280)
        self.result_list.HorizontalScrollbar = True
        self.result_list.SelectionMode = SelectionMode.MultiExtended
        self.Controls.Add(self.result_list)
        for beam in self.wrong_beams:
            self.result_list.Items.Add(get_beam_result_text(beam))
        select_button = Button()
        select_button.Text = tr("select_wrong")
        select_button.Location = Point(30, 525)
        select_button.Width = 190
        select_button.Height = 45
        select_button.Click += self.select_wrong
        self.Controls.Add(select_button)
        view_button = Button()
        view_button.Text = tr("create_3d")
        view_button.Font = Font("Arial", 11)
        view_button.Location = Point(250, 525)
        view_button.Width = 190
        view_button.Height = 45
        view_button.Click += self.create_view
        self.Controls.Add(view_button)
        close_button = Button()
        close_button.Text = tr("close")
        close_button.Location = Point(660, 525)
        close_button.Width = 190
        close_button.Height = 45
        close_button.Click += self.close_form
        self.Controls.Add(close_button)

    def select_wrong(self, sender, args):
        select_beams(self.wrong_beams)
        MessageBox.Show(tr("selected").format(len(self.wrong_beams)),
                        tr("header"), MessageBoxButtons.OK,
                        MessageBoxIcon.Information)

    def create_view(self, sender, args):
        if not self.wrong_beams:
            MessageBox.Show(tr("no_wrong"), tr("header"),
                            MessageBoxButtons.OK, MessageBoxIcon.Information)
            return
        view = create_3d_view(self.wrong_beams)
        if view:
            MessageBox.Show(tr("view_created").format(view.Name),
                            tr("header"), MessageBoxButtons.OK,
                            MessageBoxIcon.Information)

    def close_form(self, sender, args):
        self.Close()

class BeamDirectionForm(Form):
    def __init__(self):
        Form.__init__(self)
        self.Text = tr("title")
        self.Width = 850
        self.Height = 650
        self.StartPosition = FormStartPosition.CenterScreen
        self.FormBorderStyle = FormBorderStyle.FixedDialog
        self.MaximizeBox = False
        self.MinimizeBox = False
        self.create_ui()

    def create_ui(self):
        header = Panel()
        header.Dock = DockStyle.Top
        header.Height = 75
        header.BackColor = Color.FromArgb(40, 90, 140)
        self.Controls.Add(header)
        title = Label()
        title.Text = tr("header")
        title.ForeColor = Color.White
        title.Font = Font("Arial", 20)
        title.AutoSize = True
        title.Location = Point(25, 20)
        header.Controls.Add(title)
        label = Label()
        label.Text = tr("select_family")
        label.Font = Font("Arial", 11)
        label.AutoSize = True
        label.Location = Point(25, 95)
        self.Controls.Add(label)
        self.family_list = CheckedListBox()
        self.family_list.Location = Point(25, 125)
        self.family_list.Size = Size(380, 230)
        self.family_list.CheckOnClick = True
        self.Controls.Add(self.family_list)
        beam_families[:] = []
        for family_name, count in get_family_list():
            self.family_list.Items.Add("{}   [{} beams]".format(family_name, count))
            beam_families.append(family_name)
        select_all = Button()
        select_all.Text = tr("select_all")
        select_all.Location = Point(25, 370)
        select_all.Width = 120
        select_all.Height = 35
        select_all.Click += self.select_all
        self.Controls.Add(select_all)
        clear_all = Button()
        clear_all.Text = tr("clear_all")
        clear_all.Location = Point(160, 370)
        clear_all.Width = 120
        clear_all.Height = 35
        clear_all.Click += self.clear_all
        self.Controls.Add(clear_all)
        rule = Label()
        rule.Text = tr("rule")
        rule.Font = Font("Arial", 11)
        rule.AutoSize = True
        rule.Location = Point(450, 110)
        self.Controls.Add(rule)
        check = Button()
        check.Text = tr("check")
        check.Font = Font("Arial", 12)
        check.Location = Point(450, 230)
        check.Width = 300
        check.Height = 55
        check.Click += self.check_direction
        self.Controls.Add(check)
        close = Button()
        close.Text = tr("close")
        close.Location = Point(450, 300)
        close.Width = 300
        close.Height = 40
        close.Click += self.close_form
        self.Controls.Add(close)

    def select_all(self, sender, args):
        for i in range(self.family_list.Items.Count):
            self.family_list.SetItemChecked(i, True)

    def clear_all(self, sender, args):
        for i in range(self.family_list.Items.Count):
            self.family_list.SetItemChecked(i, False)

    def get_selected_families(self):
        return [beam_families[i] for i in self.family_list.CheckedIndices]

    def check_direction(self, sender, args):
        selected = self.get_selected_families()
        if not selected:
            MessageBox.Show(tr("choose_family"), tr("header"),
                            MessageBoxButtons.OK, MessageBoxIcon.Warning)
            return
        target = [b for b in get_all_beams() if get_family_name(b) in selected]
        wrong = [b for b in target if is_wrong_direction(b)]
        correct = len(target) - len(wrong)
        ResultForm(target, wrong, correct).ShowDialog()

    def close_form(self, sender, args):
        self.Close()

try:
    BeamDirectionForm().ShowDialog()
except Exception as error:
    MessageBox.Show(tr("error").format(error),
                    "BIM SEKOU GROUP",
                    MessageBoxButtons.OK, MessageBoxIcon.Error)
