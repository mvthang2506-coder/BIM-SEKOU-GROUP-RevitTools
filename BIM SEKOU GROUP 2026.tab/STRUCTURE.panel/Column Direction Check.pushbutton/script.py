# -*- coding: utf-8 -*-
import clr, os, math
clr.AddReference("System")
clr.AddReference("System.Drawing")
clr.AddReference("System.Windows.Forms")
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from System import Array
from System.Drawing import Color, Font, Point, Size
from System.Windows.Forms import Form, Label, Button, CheckedListBox, ListBox, MessageBox, MessageBoxButtons, MessageBoxIcon, Panel, FormStartPosition, FormBorderStyle, SelectionMode, DockStyle
from Autodesk.Revit.DB import FilteredElementCollector, BuiltInCategory, FamilyInstance, View3D, ViewFamilyType, ViewFamily, Transaction, OverrideGraphicSettings, Color as RColor, ElementId, BoundingBoxXYZ, XYZ
from pyrevit import revit

uidoc = revit.uidoc
doc = revit.doc
CAT = BuiltInCategory.OST_StructuralColumns
VIEW_NAME = "BIM_Column_Direction_Error"
LANG_FILE = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "BIM_SEKOU_GROUP_language.txt")

LANG = "vi"
try:
    if os.path.exists(LANG_FILE):
        f = open(LANG_FILE, "r")
        x = f.read().strip()
        f.close()
        if x in ("vi", "en", "ja"):
            LANG = x
except:
    pass

TEXT = {
    "vi": {
        "title":"BIM SEKOU GROUP - Kiểm tra hướng cột",
        "header":"KIỂM TRA HƯỚNG CỘT",
        "family":"Chọn Family cột:",
        "all":"CHỌN TẤT CẢ",
        "clear":"BỎ CHỌN",
        "rule":"Quy tắc hướng:\r\n→ X = ĐÚNG\r\n↑ Y = ĐÚNG\r\n← X = SAI\r\n↓ Y = SAI",
        "check":"KIỂM TRA HƯỚNG",
        "close":"ĐÓNG",
        "result":"Kiểm tra hướng cột - Kết quả",
        "wrong_title":"CỘT SAI HƯỚNG",
        "ok_title":"TẤT CẢ CỘT ĐỀU ĐÚNG",
        "total":"Tổng số cột",
        "correct":"Đúng",
        "wrong":"Sai",
        "list":"Danh sách cột sai hướng:",
        "select":"CHỌN CỘT SAI",
        "view":"TẠO VIEW 3D",
        "selected":"{} cột đã được chọn.",
        "none":"Không có cột sai hướng.",
        "created":"Đã tạo View 3D:\r\n\r\n{}",
        "choose":"Vui lòng chọn ít nhất một Family cột.",
        "error":"Lỗi kiểm tra hướng cột:\r\n\r\n{}"
    },
    "en": {
        "title":"BIM SEKOU GROUP - Column Direction Check",
        "header":"COLUMN DIRECTION CHECK",
        "family":"Select Column Family:",
        "all":"SELECT ALL",
        "clear":"CLEAR ALL",
        "rule":"Direction rule:\r\n→ X = CORRECT\r\n↑ Y = WRONG\r\n← X = WRONG\r\n↓ Y = WRONG",
        "check":"CHECK DIRECTION",
        "close":"CLOSE",
        "result":"Column Direction Check - Result",
        "wrong_title":"WRONG COLUMN DIRECTION",
        "ok_title":"ALL COLUMNS CORRECT",
        "total":"Total columns",
        "correct":"Correct",
        "wrong":"Wrong",
        "list":"Wrong direction columns:",
        "select":"SELECT WRONG COLUMNS",
        "view":"CREATE 3D VIEW",
        "selected":"{} columns selected.",
        "none":"No wrong-direction columns.",
        "created":"3D View created:\r\n\r\n{}",
        "choose":"Please select at least one column Family.",
        "error":"Column Direction Check Error:\r\n\r\n{}"
    },
    "ja": {
        "title":"BIM SEKOU GROUP - 柱方向チェック",
        "header":"柱方向チェック",
        "family":"柱ファミリを選択：",
        "all":"すべて選択",
        "clear":"選択解除",
        "rule":"方向ルール：\r\n→ X = 正しい\r\n↑ Y = 間違い\r\n← X = 間違い\r\n↓ Y = 間違い",
        "check":"方向を確認",
        "close":"閉じる",
        "result":"柱方向チェック - 結果",
        "wrong_title":"柱方向が間違っています",
        "ok_title":"すべての柱が正しい方向です",
        "total":"柱の総数",
        "correct":"正しい",
        "wrong":"間違い",
        "list":"方向が間違っている柱：",
        "select":"間違った柱を選択",
        "view":"3Dビューを作成",
        "selected":"{} 本の柱を選択しました。",
        "none":"方向が間違っている柱はありません。",
        "created":"3Dビューを作成しました：\r\n\r\n{}",
        "choose":"少なくとも1つの柱ファミリを選択してください。",
        "error":"柱方向チェックエラー：\r\n\r\n{}"
    }
}

def tr(k):
    return TEXT[LANG][k]

def get_family(e):
    try:
        return e.Symbol.Family.Name
    except:
        return ""

def get_type(e):
    try:
        return e.Symbol.Name
    except:
        return ""

def get_columns():
    result=[]
    for e in FilteredElementCollector(doc).OfCategory(CAT).WhereElementIsNotElementType():
        if isinstance(e, FamilyInstance):
            result.append(e)
    return result

def get_families():
    d={}
    for e in get_columns():
        n=get_family(e)
        if n:
            d[n]=d.get(n,0)+1
    return sorted(d.items(), key=lambda x:x[0].lower())

def get_angle(e):
    try:
        b=e.GetTransform().BasisX
        a=math.degrees(math.atan2(b.Y,b.X))
        if a<0: a+=360
        return a
    except:
        return None

def is_correct(e):
    a=get_angle(e)
    return a is not None and (a<=5 or a>=355)

def symbol(e):
    a=get_angle(e)
    if a is None:return "?"
    if a<=5 or a>=355:return "→"
    if 85<=a<=95:return "↑"
    if 175<=a<=185:return "←"
    if 265<=a<=275:return "↓"
    return "↗"

def item_text(e):
    a=get_angle(e)
    angle="?" if a is None else "{:.1f}°".format(a)
    return "{} | {} | {} | {} | ID: {}".format(symbol(e),get_family(e),get_type(e),angle,e.Id.IntegerValue)

def unique_view_name():
    names=set()
    for v in FilteredElementCollector(doc).OfClass(View3D):
        try:
            if not v.IsTemplate:names.add(v.Name)
        except:pass
    if VIEW_NAME not in names:return VIEW_NAME
    i=2
    while VIEW_NAME+"_"+str(i) in names:i+=1
    return VIEW_NAME+"_"+str(i)

def make_view(bad):
    if not bad:
        MessageBox.Show(tr("none"),tr("header"),MessageBoxButtons.OK,MessageBoxIcon.Information)
        return
    vt=None
    for x in FilteredElementCollector(doc).OfClass(ViewFamilyType):
        try:
            if x.ViewFamily==ViewFamily.ThreeDimensional:
                vt=x
                break
        except:pass
    if vt is None:
        MessageBox.Show("3D View Type not found.",tr("header"),MessageBoxButtons.OK,MessageBoxIcon.Error)
        return
    t=Transaction(doc,"Create Column Direction Error 3D View")
    try:
        t.Start()
        v=View3D.CreateIsometric(doc,vt.Id)
        v.Name=unique_view_name()
        cid=ElementId(CAT).IntegerValue
        for c in doc.Settings.Categories:
            try:
                if c.AllowsVisibilityControl and c.Id.IntegerValue!=cid and v.CanCategoryBeHidden(c.Id):
                    v.SetCategoryHidden(c.Id,True)
            except:pass
        keep=set([e.Id.IntegerValue for e in bad])
        hide=[]
        for e in get_columns():
            if e.Id.IntegerValue not in keep:hide.append(e.Id)
        if hide:
            v.HideElements(Array[ElementId](hide))
        og=OverrideGraphicSettings()
        og.SetProjectionLineColor(RColor(255,0,0))
        og.SetCutLineColor(RColor(255,0,0))
        for e in bad:
            v.SetElementOverrides(e.Id,og)
        t.Commit()
        uidoc.Selection.SetElementIds(Array[ElementId]([e.Id for e in bad]))
        uidoc.ActiveView=v
        MessageBox.Show(tr("created").format(v.Name),tr("header"),MessageBoxButtons.OK,MessageBoxIcon.Information)
    except Exception as ex:
        try:t.RollBack()
        except:pass
        MessageBox.Show(str(ex),tr("header"),MessageBoxButtons.OK,MessageBoxIcon.Error)

class ResultForm(Form):
    def __init__(self,allc,bad):
        Form.__init__(self)
        self.bad=bad
        self.Text=tr("result"); self.Width=900; self.Height=620
        self.StartPosition=FormStartPosition.CenterScreen
        self.FormBorderStyle=FormBorderStyle.FixedDialog
        h=Panel(); h.Dock=DockStyle.Top; h.Height=80
        h.BackColor=Color.FromArgb(190,60,40) if bad else Color.FromArgb(40,140,80)
        self.Controls.Add(h)
        title=Label(); title.Text=tr("wrong_title") if bad else tr("ok_title")
        title.ForeColor=Color.White; title.Font=Font("Arial",18); title.AutoSize=True
        title.Location=Point(25,22); h.Controls.Add(title)
        s=Label(); s.Text="{}: {}\r\n{}: {}\r\n{}: {}".format(tr("total"),len(allc),tr("correct"),len(allc)-len(bad),tr("wrong"),len(bad))
        s.Location=Point(30,100); s.AutoSize=True; self.Controls.Add(s)
        l=Label(); l.Text=tr("list"); l.Location=Point(30,175); l.AutoSize=True; self.Controls.Add(l)
        self.lb=ListBox(); self.lb.Location=Point(30,205); self.lb.Size=Size(840,280); self.lb.HorizontalScrollbar=True; self.Controls.Add(self.lb)
        for e in bad:self.lb.Items.Add(item_text(e))
        b=Button(); b.Text=tr("select"); b.Location=Point(30,510); b.Width=220; b.Height=45; b.Click+=self.select_bad; self.Controls.Add(b)
        b=Button(); b.Text=tr("view"); b.Location=Point(270,510); b.Width=220; b.Height=45; b.Click+=self.view; self.Controls.Add(b)
        b=Button(); b.Text=tr("close"); b.Location=Point(680,510); b.Width=190; b.Height=45; b.Click+=lambda s,a:self.Close(); self.Controls.Add(b)
    def select_bad(self,s,a):
        uidoc.Selection.SetElementIds(Array[ElementId]([e.Id for e in self.bad]))
        MessageBox.Show(tr("selected").format(len(self.bad)),tr("header"),MessageBoxButtons.OK,MessageBoxIcon.Information)
    def view(self,s,a):
        make_view(self.bad)

class MainForm(Form):
    def __init__(self):
        Form.__init__(self); self.Text=tr("title"); self.Width=850; self.Height=600
        self.StartPosition=FormStartPosition.CenterScreen; self.FormBorderStyle=FormBorderStyle.FixedDialog
        h=Panel(); h.Dock=DockStyle.Top; h.Height=75; h.BackColor=Color.FromArgb(40,90,140); self.Controls.Add(h)
        z=Label(); z.Text=tr("header"); z.ForeColor=Color.White; z.Font=Font("Arial",20); z.AutoSize=True; z.Location=Point(25,20); h.Controls.Add(z)
        l=Label(); l.Text=tr("family"); l.Location=Point(25,95); l.AutoSize=True; self.Controls.Add(l)
        self.lb=CheckedListBox(); self.lb.Location=Point(25,125); self.lb.Size=Size(380,220); self.lb.CheckOnClick=True; self.Controls.Add(self.lb)
        self.names=[]
        for n,c in get_families():self.lb.Items.Add("{}   [{} columns]".format(n,c));self.names.append(n)
        b=Button();b.Text=tr("all");b.Location=Point(25,360);b.Width=120;b.Click+=lambda s,a:[self.lb.SetItemChecked(i,True) for i in range(self.lb.Items.Count)];self.Controls.Add(b)
        b=Button();b.Text=tr("clear");b.Location=Point(160,360);b.Width=120;b.Click+=lambda s,a:[self.lb.SetItemChecked(i,False) for i in range(self.lb.Items.Count)];self.Controls.Add(b)
        r=Label();r.Text=tr("rule");r.Font=Font("Arial",11);r.AutoSize=True;r.Location=Point(450,110);self.Controls.Add(r)
        b=Button();b.Text=tr("check");b.Font=Font("Arial",12);b.Location=Point(450,230);b.Width=300;b.Height=55;b.Click+=self.check;self.Controls.Add(b)
        b=Button();b.Text=tr("close");b.Location=Point(450,300);b.Width=300;b.Height=40;b.Click+=lambda s,a:self.Close();self.Controls.Add(b)
    def check(self,s,a):
        selected=[self.names[i] for i in self.lb.CheckedIndices]
        if not selected:
            MessageBox.Show(tr("choose"),tr("header"),MessageBoxButtons.OK,MessageBoxIcon.Warning);return
        allc=[e for e in get_columns() if get_family(e) in selected]
        bad=[e for e in allc if not is_correct(e)]
        ResultForm(allc,bad).ShowDialog()

try:
    MainForm().ShowDialog()
except Exception as ex:
    MessageBox.Show(tr("error").format(ex),"BIM SEKOU GROUP",MessageBoxButtons.OK,MessageBoxIcon.Error)
