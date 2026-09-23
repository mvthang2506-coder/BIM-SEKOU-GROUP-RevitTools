# -*- coding: utf-8 -*-
from pyrevit import revit, DB, forms, script
import clr

doc = revit.doc
uidoc = revit.uidoc
output = script.get_output()

# ============================================================
# Autojoin/Unjoin V12
# Revit 2025 / pyRevit
#
# Rules:
# 1. Only real Model categories are offered.
# 2. Candidate pairs must have actual solid intersection.
#    Bounding-box overlap is only a fast pre-filter.
# 3. Non-intersecting / distant objects are skipped completely.
# 4. Every JoinGeometry operation is verified with
#    JoinGeometryUtils.AreElementsJoined().
# 5. Join priority: position 1 = highest priority / cutting.
# 6. If already joined, only priority is checked and switched.
# ============================================================

TOL_VOL = 1e-9
TOL_BBOX = 1e-6

# Categories that should never participate in this tool.
EXCLUDED_CATEGORY_NAMES = set([
    "<Sketch>",
    "Sketch",
    "Sketches",
    "Area Based Load Type",
    "HVAC Zones",
    "Internal Origin",
    "Legend Components",
    "Material Assets",
    "Materials",
    "Pipe Segments",
    "Primary Contours",
    "Project Base Point",
    "Project Information",
    "Sheets",
    "Sun Path",
    "Survey Point",
    "Levels",
    "Grids",
    "Scope Boxes",
    "Rooms",
    "Areas",
    "Spaces",
])

# Common categories that are not useful for Join Geometry.
EXCLUDED_BUILTIN = set([
    DB.BuiltInCategory.OST_Levels,
    DB.BuiltInCategory.OST_Grids,
    DB.BuiltInCategory.OST_Views,
    DB.BuiltInCategory.OST_Sheets,
    DB.BuiltInCategory.OST_Cameras,
    DB.BuiltInCategory.OST_RvtLinks,
    DB.BuiltInCategory.OST_ImportObjectStyles,
])

def safe_name(cat):
    try:
        return cat.Name
    except:
        return ""

def is_model_category(cat):
    if cat is None:
        return False
    try:
        if cat.CategoryType != DB.CategoryType.Model:
            return False
    except:
        return False

    name = safe_name(cat)
    if name in EXCLUDED_CATEGORY_NAMES:
        return False

    # Revit special/internal categories such as <Sketch> are not
    # real model categories and must never appear in Autojoin.
    if name.startswith("<") and name.endswith(">"):
        return False
    if name.lower() in ("sketch", "<sketch>", "sketches"):
        return False

    try:
        if cat.Id.IntegerValue in [int(x) for x in EXCLUDED_BUILTIN]:
            return False
    except:
        pass

    return True

def has_real_geometry(e):
    try:
        if e.ViewSpecific:
            return False
    except:
        pass

    try:
        if e.Category is None or not is_model_category(e.Category):
            return False
    except:
        return False

    # Import / link instances are not Join Geometry targets.
    try:
        if isinstance(e, DB.ImportInstance):
            return False
    except:
        pass

    return True

def bbox(e):
    try:
        return e.get_BoundingBox(None)
    except:
        return None

def bbox_intersects(a, b, tol=TOL_BBOX):
    ba = bbox(a)
    bb = bbox(b)
    if ba is None or bb is None:
        return False

    try:
        return (
            ba.Min.X <= bb.Max.X + tol and ba.Max.X + tol >= bb.Min.X and
            ba.Min.Y <= bb.Max.Y + tol and ba.Max.Y + tol >= bb.Min.Y and
            ba.Min.Z <= bb.Max.Z + tol and ba.Max.Z + tol >= bb.Min.Z
        )
    except:
        return False

def get_solids(e):
    solids = []
    try:
        opt = DB.Options()
        opt.ComputeReferences = False
        opt.IncludeNonVisibleObjects = False
        opt.DetailLevel = DB.ViewDetailLevel.Fine

        ge = e.get_Geometry(opt)
        if ge is None:
            return solids

        def walk(geom):
            for g in geom:
                if isinstance(g, DB.Solid):
                    try:
                        if g.Volume > TOL_VOL:
                            solids.append(g)
                    except:
                        pass
                elif isinstance(g, DB.GeometryInstance):
                    try:
                        walk(g.GetInstanceGeometry())
                    except:
                        pass

        walk(ge)
    except:
        pass
    return solids

def solid_intersects(e1, e2):
    """
    True only when the actual solids intersect with non-zero volume.
    Bounding-box overlap alone is NOT enough.
    """
    s1 = get_solids(e1)
    s2 = get_solids(e2)

    if not s1 or not s2:
        return False

    for a in s1:
        for b in s2:
            try:
                inter = DB.BooleanOperationsUtils.ExecuteBooleanOperation(
                    a, b, DB.BooleanOperationsType.Intersect
                )
                if inter is not None and inter.Volume > TOL_VOL:
                    return True
            except:
                # Some Revit solids cannot be booleaned directly.
                # Do not treat this as an intersection.
                continue
    return False

def actual_intersection(e1, e2):
    # Fast reject first.
    if not bbox_intersects(e1, e2):
        return False
    # Only actual solid intersection becomes a Join candidate.
    return solid_intersects(e1, e2)

def visible_model_ids(view_id):
    ids = set()
    try:
        fec = DB.FilteredElementCollector(doc, view_id).WhereElementIsNotElementType()
        for e in fec:
            if has_real_geometry(e):
                ids.add(e.Id.IntegerValue)
    except:
        pass
    return ids

def collect_scope(view_id, current_view):
    """
    Return elements that actually belong to the requested scope.

    Current View:
      Uses FilteredElementCollector(view_id), which is view-scoped.
      For 3D views with an active Section Box, an additional bounding-box
      test is applied against the Section Box so categories/elements
      outside the clipped volume are not counted.

    Entire Project:
      Returns project-wide model elements.
    """
    all_elems = []

    try:
        if current_view:
            view = doc.GetElement(view_id)
            fec = DB.FilteredElementCollector(doc, view_id) \
                .WhereElementIsNotElementType()

            section_box = None
            if isinstance(view, DB.View3D):
                try:
                    if view.IsSectionBoxActive:
                        section_box = view.GetSectionBox()
                except:
                    section_box = None

            for e in fec:
                if not has_real_geometry(e):
                    continue

                # Respect view visibility returned by the view collector.
                try:
                    if e.IsHidden(view):
                        continue
                except:
                    pass

                # Explicit Section Box filtering for 3D views.
                if section_box is not None:
                    eb = bbox(e)
                    if eb is None:
                        continue

                    try:
                        inv = section_box.Transform.Inverse

                        # Transform all 8 bbox corners into section-box
                        # local coordinates, then test against the box.
                        pts = [
                            eb.Min,
                            eb.Max,
                            DB.XYZ(eb.Min.X, eb.Min.Y, eb.Max.Z),
                            DB.XYZ(eb.Min.X, eb.Max.Y, eb.Min.Z),
                            DB.XYZ(eb.Min.X, eb.Max.Y, eb.Max.Z),
                            DB.XYZ(eb.Max.X, eb.Min.Y, eb.Min.Z),
                            DB.XYZ(eb.Max.X, eb.Min.Y, eb.Max.Z),
                            DB.XYZ(eb.Max.X, eb.Max.Y, eb.Min.Z),
                        ]

                        local_pts = [inv.OfPoint(p) for p in pts]

                        minx = min(p.X for p in local_pts)
                        maxx = max(p.X for p in local_pts)
                        miny = min(p.Y for p in local_pts)
                        maxy = max(p.Y for p in local_pts)
                        minz = min(p.Z for p in local_pts)
                        maxz = max(p.Z for p in local_pts)

                        sbmin = section_box.Min
                        sbmax = section_box.Max

                        if (
                            maxx < sbmin.X or minx > sbmax.X or
                            maxy < sbmin.Y or miny > sbmax.Y or
                            maxz < sbmin.Z or minz > sbmax.Z
                        ):
                            continue
                    except:
                        # If explicit section-box test fails, keep the
                        # view collector result rather than dropping it.
                        pass

                all_elems.append(e)

        else:
            fec = DB.FilteredElementCollector(doc) \
                .WhereElementIsNotElementType()

            for e in fec:
                if has_real_geometry(e):
                    all_elems.append(e)

    except:
        pass

    return all_elems

def collect_model_categories_from_scope(scope_elements):
    """
    Build the Category list ONLY from elements that are actually present
    in the selected scope.

    Important:
    - Entire Project: scope_elements contains project model elements.
    - Current View: scope_elements contains only elements returned for
      the active view, so categories existing elsewhere in the project
      are NOT shown.
    """
    cats = {}

    for e in scope_elements:
        try:
            if not has_real_geometry(e):
                continue
            cat = e.Category
            if cat is None:
                continue
            if not is_model_category(cat):
                continue
            cats[cat.Name] = cat
        except:
            continue

    return cats

def category_elements(elements, cat_name):
    return [e for e in elements
            if e.Category is not None and safe_name(e.Category) == cat_name]

def pair_key(a, b):
    x = a.Id.IntegerValue
    y = b.Id.IntegerValue
    return (x, y) if x < y else (y, x)

def are_joined(a, b):
    try:
        return DB.JoinGeometryUtils.AreElementsJoined(doc, a, b)
    except:
        return False

def is_cutting(a, b):
    try:
        return DB.JoinGeometryUtils.IsCuttingElementInJoin(doc, a, b)
    except:
        return False

def enforce_pair(priority, other):
    """
    Returns:
      NEW_JOIN
      SWITCHED
      ALREADY_CORRECT
      NOT_JOINED
      WRONG_PRIORITY
      FAILED
    """
    try:
        if are_joined(priority, other):
            if is_cutting(priority, other):
                return "ALREADY_CORRECT"
            try:
                DB.JoinGeometryUtils.SwitchJoinOrder(doc, priority, other)
                doc.Regenerate()
            except:
                return "WRONG_PRIORITY"

            if are_joined(priority, other) and is_cutting(priority, other):
                return "SWITCHED"
            return "WRONG_PRIORITY"

        # Not joined yet.
        DB.JoinGeometryUtils.JoinGeometry(doc, priority, other)
        doc.Regenerate()

        # Critical verification: Join must really exist.
        if not are_joined(priority, other):
            return "NOT_JOINED"

        if is_cutting(priority, other):
            return "NEW_JOIN"

        # Join exists but wrong order.
        try:
            DB.JoinGeometryUtils.SwitchJoinOrder(doc, priority, other)
            doc.Regenerate()
        except:
            return "WRONG_PRIORITY"

        if are_joined(priority, other) and is_cutting(priority, other):
            return "SWITCHED"

        return "WRONG_PRIORITY"

    except:
        return "FAILED"

def find_actual_pairs(elements_a, elements_b, same_category=False):
    """
    Returns only pairs whose ACTUAL SOLIDS intersect.
    Distant elements and bbox-only overlaps are not candidates.
    """
    result = []
    seen = set()

    for i, a in enumerate(elements_a):
        start = i + 1 if same_category else 0
        for j in range(start, len(elements_b)):
            b = elements_b[j]

            if a.Id.IntegerValue == b.Id.IntegerValue:
                continue

            key = pair_key(a, b)
            if key in seen:
                continue
            seen.add(key)

            # Fast filter
            if not bbox_intersects(a, b):
                continue

            # Real geometry check
            if not solid_intersects(a, b):
                continue

            result.append((a, b))

    return result

def build_priority_order(categories):
    # Default structural order.
    preferred = [
        "Structural Foundations",
        "Structural Columns",
        "Structural Framing",
        "Floors",
        "Walls",
    ]
    return [x for x in preferred if x in categories]

def choose_custom_order(categories):
    names = sorted(categories.keys(), key=lambda x: x.lower())
    remaining = list(names)
    chosen = []

    while remaining:
        opts = []
        for n in remaining:
            opts.append(n)

        picked = forms.SelectFromList.show(
            opts,
            title="Chọn Category ưu tiên - chỉ Category đang hiện hữu trong phạm vi đã chọn",
            multiselect=False,
            button_name="Chọn",
            width=500,
            height=600
        )
        if not picked:
            return None

        chosen.append(picked)
        remaining.remove(picked)

        if not remaining:
            break

        more = forms.alert(
            "Đã chọn vị trí %d:\n\n%s\n\n"
            "Có muốn chọn thêm Category không?" %
            (len(chosen), "\n".join(
                ["%d. %s" % (i + 1, x) for i, x in enumerate(chosen)]
            )),
            yes=True, no=True
        )
        if not more:
            break

    return chosen


def family_key(element):
    try:
        if isinstance(element, DB.FamilyInstance):
            return element.Symbol.Family.Name
    except:
        pass
    return None


def family_display(element):
    try:
        if isinstance(element, DB.FamilyInstance):
            fam = element.Symbol.Family.Name
            cat = element.Category.Name if element.Category else ""
            return "%s | %s" % (cat, fam)
    except:
        pass
    return None


def get_family_map(elements):
    result = {}
    for element in elements:
        name = family_key(element)
        display = family_display(element)
        if not name or not display:
            continue
        if display not in result:
            result[display] = {
                "family": name,
                "category": safe_name(element.Category),
                "elements": []
            }
        result[display]["elements"].append(element)
    return result


def make_family_pairs(elements_a, elements_b, same_family=False):
    pairs = []
    seen = set()

    for i, a in enumerate(elements_a):
        start = i + 1 if same_family else 0
        for j in range(start, len(elements_b)):
            b = elements_b[j]

            if a.Id.IntegerValue == b.Id.IntegerValue:
                continue

            key = pair_key(a, b)
            if key in seen:
                continue
            seen.add(key)

            if not bbox_intersects(a, b):
                continue
            if not solid_intersects(a, b):
                continue

            pairs.append((a, b))

    return pairs


def build_family_pairs(family_map, order):
    pairs = []
    seen = set()

    for i in range(len(order)):
        a = family_map[order[i]]["elements"]

        same_pairs = make_family_pairs(a, a, same_family=True)
        for a1, b1 in same_pairs:
            key = pair_key(a1, b1)
            if key not in seen:
                seen.add(key)
                pairs.append((i, i, a1, b1))

        for j in range(i + 1, len(order)):
            b = family_map[order[j]]["elements"]
            cross_pairs = make_family_pairs(a, b)
            for a1, b1 in cross_pairs:
                key = pair_key(a1, b1)
                if key not in seen:
                    seen.add(key)
                    pairs.append((i, j, a1, b1))

    return pairs


def run_family_autojoin(order, current_view):
    elements = collect_scope(doc.ActiveView.Id, current_view)
    family_map = get_family_map(elements)

    if not family_map:
        forms.alert(
            "Không tìm thấy Family Instance có hình học trong phạm vi đã chọn.",
            title="Join by Family"
        )
        return

    order = [x for x in order if x in family_map]
    if not order:
        return

    pairs = build_family_pairs(family_map, order)
    scope_name = "Current View" if current_view else "Entire Project"

    if not show_confirmation(
        order,
        scope_name,
        {"__family_total__": len(pairs)}
    ):
        return

    with revit.Transaction("Join by Family"):
        for i, j, a, b in pairs:
            if i <= j:
                enforce_pair(a, b)
            else:
                enforce_pair(b, a)

        try:
            doc.Regenerate()
        except:
            pass

    try:
        doc.Regenerate()
    except:
        pass

    try:
        revit.uidoc.RefreshActiveView()
    except:
        pass

    show_success_result(scope_name, len(pairs))
    return


def show_confirmation(order, scope_name, pair_counts):
    total = sum(pair_counts.values())
    message = (
        "Phạm vi : %s\n"
        "\n"
        "Tổng số đối tượng join : %d\n"
        "\n"
        "Xác nhận chạy Autojoin?"
        % (scope_name, total)
    )
    return forms.alert(
        message,
        title="Xác nhận Autojoin",
        yes=True,
        no=True
    )


class AutojoinSuccessWindow(forms.WPFWindow):
    def __init__(self, scope_name, total):
        xaml_path = os.path.join(
            os.path.dirname(__file__),
            "success.xaml"
        )
        forms.WPFWindow.__init__(self, xaml_path)
        self.ScopeText.Text = "Phạm vi : %s" % scope_name
        self.CountText.Text = "Tổng số đối tượng join : %d" % total
        self.OkButton.Click += self.close_window

    def close_window(self, sender, args):
        self.Close()


def show_success_result(scope_name, total):
    win = AutojoinSuccessWindow(scope_name, total)
    win.ShowDialog()


# ============================================================
# V12 - SINGLE SETTINGS TABLE
# One dialog for:
#   - Current View / Entire Project
#   - Category selection
#   - Priority selection
# No multi-step SelectFromList dialogs.
# ============================================================

from pyrevit import forms
import os
from System import Array
from System.Windows import Thickness
from System.Windows.Controls import (
    CheckBox, ComboBox, ComboBoxItem, StackPanel, Grid,
    TextBlock, Button, Border, Orientation, ColumnDefinition
)
from System.Windows import GridLength, GridUnitType
from System.Windows import HorizontalAlignment, VerticalAlignment
from System.Windows.Media import Brushes



class AutojoinWindow(forms.WPFWindow):
    """
    V15 UI:
    - One window.
    - Selected categories are shown in the TOP table.
    - Unselected categories are shown in the BOTTOM table.
    - When a category is checked, it moves to TOP.
    - When unchecked, it moves to BOTTOM.
    - Priority determines TOP position automatically.
      Priority 1 = first, Priority 2 = second, etc.
    """
    def __init__(self):
        self.category_data = {}  # name -> {"checked": bool, "priority": int}
        self.current_view = True
        self.result = None
        self._building = False

        forms.WPFWindow.__init__(
            self,
            os.path.join(os.path.dirname(__file__), "ui.xaml")
        )

        self.CurrentViewRadio.Checked += self.scope_changed
        self.EntireProjectRadio.Checked += self.scope_changed
        self.RefreshButton.Click += self.refresh_clicked
        self.SelectAllButton.Click += self.select_all
        self.ClearAllButton.Click += self.clear_all
        self.RunButton.Click += self.run_clicked
        self.CancelButton.Click += self.cancel_clicked

        self.refresh_categories()

        self.family_data = {}
        self.family_current_view = True
        self.FamilyCurrentViewRadio.Checked += self.family_scope_changed
        self.FamilyEntireProjectRadio.Checked += self.family_scope_changed
        self.FamilyRunButton.Click += self.family_run_clicked
        self.refresh_families()

    def scope_changed(self, sender, args):
        if self._building:
            return
        self.current_view = bool(self.CurrentViewRadio.IsChecked)
        self.refresh_categories()

    def refresh_clicked(self, sender, args):
        self.current_view = bool(self.CurrentViewRadio.IsChecked)
        self.refresh_categories()

    def get_scope_elements(self):
        return collect_scope(doc.ActiveView.Id, self.current_view)

    def refresh_categories(self):
        self._building = True
        try:
            elems = self.get_scope_elements()
            cats = collect_model_categories_from_scope(elems)
            names = sorted(cats.keys(), key=lambda x: x.lower())

            # Preserve existing selections/priorities when refreshing
            old = self.category_data
            self.category_data = {}
            for name in names:
                if name in old:
                    self.category_data[name] = {
                        "checked": old[name]["checked"],
                        "priority": old[name]["priority"]
                    }
                else:
                    self.category_data[name] = {
                        "checked": False,
                        "priority": None
                    }

            self.rebuild_tables()
        finally:
            self._building = False

    def rebuild_tables(self):
        self._building = True
        try:
            selected_panel = self.SelectedCategoryPanel
            available_panel = self.AvailableCategoryPanel
            selected_panel.Children.Clear()
            available_panel.Children.Clear()

            selected = []
            available = []

            for name, data in self.category_data.items():
                if data["checked"]:
                    selected.append((name, data["priority"]))
                else:
                    available.append(name)

            # Repair invalid/duplicate priorities.
            used = set()
            clean_selected = []
            for name, p in selected:
                try:
                    p = int(p)
                except:
                    p = None
                if p is not None and p > 0 and p not in used:
                    used.add(p)
                    clean_selected.append((name, p))
                else:
                    self.category_data[name]["priority"] = None

            # Selected list is sorted by priority.
            clean_selected.sort(key=lambda x: x[1])

            # Reassign priorities if gaps/duplicates exist, preserving order.
            for idx, (name, oldp) in enumerate(clean_selected):
                newp = idx + 1
                self.category_data[name]["priority"] = newp

            clean_selected = [
                (name, self.category_data[name]["priority"])
                for name, p in clean_selected
            ]

            # Sort available alphabetically.
            available.sort(key=lambda x: x.lower())

            self.SelectedCountText.Text = "Đã chọn: %d" % len(clean_selected)
            self.AvailableCountText.Text = "Chưa chọn: %d" % len(available)

            for idx, (name, priority) in enumerate(clean_selected):
                self.add_selected_row(selected_panel, idx + 1, name, priority)

            for idx, name in enumerate(available):
                self.add_available_row(available_panel, idx + 1, name)

        finally:
            self._building = False

    def add_selected_row(self, panel, index, name, priority):
        row = Grid()
        row.Height = 36
        row.Margin = Thickness(0, 0, 0, 1)

        row.ColumnDefinitions.Add(ColumnDefinition(Width=GridLength(45)))
        row.ColumnDefinitions.Add(ColumnDefinition(Width=GridLength(55)))
        row.ColumnDefinitions.Add(ColumnDefinition(Width=GridLength(1, GridUnitType.Star)))
        row.ColumnDefinitions.Add(ColumnDefinition(Width=GridLength(120)))
        row.ColumnDefinitions.Add(ColumnDefinition(Width=GridLength(80)))

        num = TextBlock()
        num.Text = str(index)
        num.HorizontalAlignment = HorizontalAlignment.Center
        num.VerticalAlignment = VerticalAlignment.Center
        row.Children.Add(num)
        Grid.SetColumn(num, 0)

        cb = CheckBox()
        cb.IsChecked = True
        cb.HorizontalAlignment = HorizontalAlignment.Center
        cb.VerticalAlignment = VerticalAlignment.Center
        cb.Tag = name
        cb.Checked += self.category_checked
        cb.Unchecked += self.category_unchecked
        row.Children.Add(cb)
        Grid.SetColumn(cb, 1)

        label = TextBlock()
        label.Text = name
        label.VerticalAlignment = VerticalAlignment.Center
        label.Margin = Thickness(8, 0, 0, 0)
        row.Children.Add(label)
        Grid.SetColumn(label, 2)

        combo = ComboBox()
        combo.Width = 90
        combo.Height = 25
        combo.HorizontalAlignment = HorizontalAlignment.Center
        for p in range(1, max(2, len(self.category_data)) + 1):
            item = ComboBoxItem()
            item.Content = str(p)
            combo.Items.Add(item)
        combo.SelectedIndex = max(0, int(priority) - 1)
        combo.Tag = name
        combo.SelectionChanged += self.priority_changed
        row.Children.Add(combo)
        Grid.SetColumn(combo, 3)

        up = Button()
        up.Content = "▲"
        up.Width = 55
        up.Height = 25
        up.Tag = name
        up.Click += self.move_up
        row.Children.Add(up)
        Grid.SetColumn(up, 4)

        panel.Children.Add(row)

    def add_available_row(self, panel, index, name):
        row = Grid()
        row.Height = 36
        row.Margin = Thickness(0, 0, 0, 1)

        row.ColumnDefinitions.Add(ColumnDefinition(Width=GridLength(45)))
        row.ColumnDefinitions.Add(ColumnDefinition(Width=GridLength(55)))
        row.ColumnDefinitions.Add(ColumnDefinition(Width=GridLength(1, GridUnitType.Star)))
        row.ColumnDefinitions.Add(ColumnDefinition(Width=GridLength(120)))

        num = TextBlock()
        num.Text = str(index)
        num.HorizontalAlignment = HorizontalAlignment.Center
        num.VerticalAlignment = VerticalAlignment.Center
        row.Children.Add(num)
        Grid.SetColumn(num, 0)

        cb = CheckBox()
        cb.IsChecked = False
        cb.HorizontalAlignment = HorizontalAlignment.Center
        cb.VerticalAlignment = VerticalAlignment.Center
        cb.Tag = name
        cb.Checked += self.category_checked
        cb.Unchecked += self.category_unchecked
        row.Children.Add(cb)
        Grid.SetColumn(cb, 1)

        label = TextBlock()
        label.Text = name
        label.VerticalAlignment = VerticalAlignment.Center
        label.Margin = Thickness(8, 0, 0, 0)
        row.Children.Add(label)
        Grid.SetColumn(label, 2)

        hint = TextBlock()
        hint.Text = "Tích để chọn"
        hint.HorizontalAlignment = HorizontalAlignment.Center
        hint.VerticalAlignment = VerticalAlignment.Center
        hint.Foreground = Brushes.Gray
        row.Children.Add(hint)
        Grid.SetColumn(hint, 3)

        panel.Children.Add(row)

    def category_checked(self, sender, args):
        if self._building:
            return
        name = sender.Tag
        if name not in self.category_data:
            return

        self.category_data[name]["checked"] = True

        # Put newly selected category at the end of the selected list.
        selected = []
        for n, data in self.category_data.items():
            if data["checked"]:
                p = data["priority"]
                try:
                    p = int(p)
                except:
                    p = None
                if p is not None:
                    selected.append((p, n))

        if not selected:
            self.category_data[name]["priority"] = 1
        else:
            maxp = max([p for p, n in selected if p is not None] or [0])
            self.category_data[name]["priority"] = maxp + 1

        self.rebuild_tables()

    def category_unchecked(self, sender, args):
        if self._building:
            return
        name = sender.Tag
        if name not in self.category_data:
            return
        self.category_data[name]["checked"] = False
        self.category_data[name]["priority"] = None
        self.rebuild_tables()

    def priority_changed(self, sender, args):
        if self._building:
            return
        name = sender.Tag
        if name not in self.category_data or not self.category_data[name]["checked"]:
            return

        try:
            newp = int(sender.SelectedItem.Content)
        except:
            return

        # If another selected category already owns this priority,
        # swap their priorities. This makes selecting "1" immediately
        # move that category to position 1.
        other_name = None
        for n, data in self.category_data.items():
            if n == name or not data["checked"]:
                continue
            try:
                p = int(data["priority"])
            except:
                p = None
            if p == newp:
                other_name = n
                break

        oldp = self.category_data[name]["priority"]

        if other_name:
            self.category_data[other_name]["priority"] = oldp
        self.category_data[name]["priority"] = newp

        self.rebuild_tables()

    def move_up(self, sender, args):
        if self._building:
            return
        name = sender.Tag
        selected = []
        for n, data in self.category_data.items():
            if data["checked"]:
                try:
                    p = int(data["priority"])
                except:
                    p = 999999
                selected.append((p, n))
        selected.sort()

        pos = [n for p, n in selected].index(name)
        if pos <= 0:
            return

        prev_name = selected[pos - 1][1]
        p1 = self.category_data[name]["priority"]
        p2 = self.category_data[prev_name]["priority"]
        self.category_data[name]["priority"] = p2
        self.category_data[prev_name]["priority"] = p1
        self.rebuild_tables()

    def select_all(self, sender, args):
        if self._building:
            return
        selected_count = 0
        for name in sorted(self.category_data.keys(), key=lambda x: x.lower()):
            self.category_data[name]["checked"] = True
            selected_count += 1
            self.category_data[name]["priority"] = selected_count
        self.rebuild_tables()

    def clear_all(self, sender, args):
        if self._building:
            return
        for name in self.category_data:
            self.category_data[name]["checked"] = False
            self.category_data[name]["priority"] = None
        self.rebuild_tables()

    def get_selected_order(self):
        selected = []
        for name, data in self.category_data.items():
            if data["checked"]:
                try:
                    p = int(data["priority"])
                except:
                    p = None
                if p is not None:
                    selected.append((p, name))

        if not selected:
            forms.alert("Hãy tích chọn ít nhất 1 Category.")
            return None

        selected.sort(key=lambda x: x[0])

        # Normalize to 1..N, preserving current priority order.
        order = [name for p, name in selected]
        for i, name in enumerate(order):
            self.category_data[name]["priority"] = i + 1

        return order

    def run_clicked(self, sender, args):
        order = self.get_selected_order()
        if not order:
            return

        self.result = {
            "current_view": bool(self.CurrentViewRadio.IsChecked),
            "order": order
        }
        self.Close()

    def family_scope_changed(self, sender, args):
        if self._building:
            return
        self.family_current_view = bool(self.FamilyCurrentViewRadio.IsChecked)
        self.refresh_families()

    def refresh_families(self):
        self._building = True
        try:
            elements = collect_scope(
                doc.ActiveView.Id,
                self.family_current_view
            )
            fmap = get_family_map(elements)
            names = sorted(fmap.keys(), key=lambda x: x.lower())

            old = self.family_data
            self.family_data = {}
            for name in names:
                if name in old:
                    self.family_data[name] = {
                        "checked": bool(old[name].get("checked", False)),
                        "priority": old[name].get("priority", None)
                    }
                else:
                    self.family_data[name] = {
                        "checked": False,
                        "priority": None
                    }

            self.rebuild_family_tables()
        finally:
            self._building = False

    def rebuild_family_tables(self):
        self.FamilySelectedPanel.Children.Clear()
        self.FamilyAvailablePanel.Children.Clear()

        selected = [
            (name, data)
            for name, data in self.family_data.items()
            if data.get("checked")
        ]
        selected.sort(
            key=lambda x: (
                x[1].get("priority") if x[1].get("priority") is not None else 9999,
                x[0].lower()
            )
        )

        available = sorted(
            [
                name for name, data in self.family_data.items()
                if not data.get("checked")
            ],
            key=lambda x: x.lower()
        )

        for idx, (name, data) in enumerate(selected, 1):
            self.add_family_selected_row(idx, name, data)

        for idx, name in enumerate(available, 1):
            self.add_family_available_row(idx, name)

        self.FamilyAvailableCountText.Text = "Chưa chọn: %d" % len(available)
        self.FamilySelectedCountText.Text = "Đã chọn: %d" % len(selected)

    def add_family_selected_row(self, idx, name, data):
        grid = Grid()
        grid.Margin = Thickness(0, 1, 0, 1)
        grid.Height = 32

        for width in [45, 55, "*", 105, 100]:
            col = ColumnDefinition()
            if width == "*":
                col.Width = GridLength(1, GridUnitType.Star)
            else:
                col.Width = GridLength(float(width))
            grid.ColumnDefinitions.Add(col)

        stt = TextBlock()
        stt.Text = str(idx)
        stt.HorizontalAlignment = HorizontalAlignment.Center
        stt.VerticalAlignment = VerticalAlignment.Center
        Grid.SetColumn(stt, 0)
        grid.Children.Add(stt)

        cb = CheckBox()
        cb.IsChecked = True
        cb.Tag = name
        cb.HorizontalAlignment = HorizontalAlignment.Center
        cb.VerticalAlignment = VerticalAlignment.Center
        cb.Click += self.family_clicked
        Grid.SetColumn(cb, 1)
        grid.Children.Add(cb)

        txt = TextBlock()
        txt.Text = name
        txt.VerticalAlignment = VerticalAlignment.Center
        txt.Margin = Thickness(8, 0, 0, 0)
        Grid.SetColumn(txt, 2)
        grid.Children.Add(txt)

        combo = ComboBox()
        combo.Width = 85
        for i in range(1, len(self.family_data) + 1):
            combo.Items.Add(i)
        if data.get("priority"):
            combo.SelectedItem = data.get("priority")
        combo.Tag = name
        combo.SelectionChanged += self.family_priority_changed
        Grid.SetColumn(combo, 3)
        grid.Children.Add(combo)

        up = Button()
        up.Content = "▲\n▼"
        up.Width = 55
        up.Height = 28
        up.Tag = name
        up.Click += self.family_move
        Grid.SetColumn(up, 4)
        grid.Children.Add(up)

        self.FamilySelectedPanel.Children.Add(grid)

    def add_family_available_row(self, idx, name):
        grid = Grid()
        grid.Margin = Thickness(0, 1, 0, 1)
        grid.Height = 32

        for width in [45, 55, "*"]:
            col = ColumnDefinition()
            if width == "*":
                col.Width = GridLength(1, GridUnitType.Star)
            else:
                col.Width = GridLength(float(width))
            grid.ColumnDefinitions.Add(col)

        stt = TextBlock()
        stt.Text = str(idx)
        stt.HorizontalAlignment = HorizontalAlignment.Center
        stt.VerticalAlignment = VerticalAlignment.Center
        Grid.SetColumn(stt, 0)
        grid.Children.Add(stt)

        cb = CheckBox()
        cb.IsChecked = False
        cb.Tag = name
        cb.HorizontalAlignment = HorizontalAlignment.Center
        cb.VerticalAlignment = VerticalAlignment.Center
        cb.Click += self.family_clicked
        Grid.SetColumn(cb, 1)
        grid.Children.Add(cb)

        txt = TextBlock()
        txt.Text = name
        txt.VerticalAlignment = VerticalAlignment.Center
        txt.Margin = Thickness(8, 0, 0, 0)
        Grid.SetColumn(txt, 2)
        grid.Children.Add(txt)

        self.FamilyAvailablePanel.Children.Add(grid)

    def family_clicked(self, sender, args):
        if self._building:
            return

        name = sender.Tag
        if name not in self.family_data:
            return

        if bool(sender.IsChecked):
            maxp = 0
            for n, d in self.family_data.items():
                if n == name or not d.get("checked"):
                    continue
                try:
                    maxp = max(maxp, int(d.get("priority") or 0))
                except:
                    pass
            self.family_data[name]["checked"] = True
            self.family_data[name]["priority"] = maxp + 1
        else:
            self.family_data[name]["checked"] = False
            self.family_data[name]["priority"] = None

        self.rebuild_family_tables()

    def family_priority_changed(self, sender, args):
        if self._building:
            return
        name = sender.Tag
        if name not in self.family_data or sender.SelectedItem is None:
            return

        newp = int(sender.SelectedItem)
        oldp = self.family_data[name].get("priority")
        if oldp == newp:
            return

        for n, d in self.family_data.items():
            if n == name or not d.get("checked"):
                continue
            p = d.get("priority")
            if p is None:
                continue
            if oldp is not None and newp < oldp and newp <= p < oldp:
                d["priority"] = p + 1
            elif oldp is not None and oldp < newp and oldp < p <= newp:
                d["priority"] = p - 1

        self.family_data[name]["priority"] = newp
        self.rebuild_family_tables()

    def family_move(self, sender, args):
        name = sender.Tag
        if name not in self.family_data:
            return

        # One click moves one position upward/downward based on where the
        # pointer lands in the two-line button.
        pos = getattr(args, "MouseButton", None)
        # WPF Button with two-line content is ambiguous in IronPython, so
        # use mouse Y when available; top half = up, bottom half = down.
        try:
            from System.Windows.Input import Mouse
            p = Mouse.GetPosition(sender)
            move_up = p.Y < (sender.ActualHeight / 2.0)
        except:
            move_up = True

        selected = sorted(
            [
                (n, d)
                for n, d in self.family_data.items()
                if d.get("checked")
            ],
            key=lambda x: (
                x[1].get("priority") if x[1].get("priority") is not None else 9999,
                x[0].lower()
            )
        )
        names = [x[0] for x in selected]
        if name not in names:
            return

        i = names.index(name)
        j = i - 1 if move_up else i + 1
        if j < 0 or j >= len(names):
            return

        names[i], names[j] = names[j], names[i]
        for k, n in enumerate(names, 1):
            self.family_data[n]["priority"] = k

        self.rebuild_family_tables()

    def family_run_clicked(self, sender, args):
        order = [
            name for name, data in sorted(
                self.family_data.items(),
                key=lambda x: (
                    x[1].get("priority") if x[1].get("priority") is not None else 9999,
                    x[0].lower()
                )
            )
            if data.get("checked")
        ]

        if not order:
            forms.alert(
                "Hãy chọn ít nhất một Family.",
                title="Join by Family"
            )
            return

        current_view = bool(self.FamilyCurrentViewRadio.IsChecked)
        # Close settings window before executing the transaction so Revit
        # can fully process the join and show the result dialog afterward.
        self.Close()
        run_family_autojoin(order, current_view)

    def cancel_clicked(self, sender, args):
        self.result = None
        self.Close()

def run_autojoin(order, current_view):
    scope_name = "Current View" if current_view else "Entire Project"

    elems = collect_scope(doc.ActiveView.Id, current_view)
    by_cat = {}
    for name in order:
        by_cat[name] = category_elements(elems, name)

    pair_list = []
    pair_seen = set()

    for i, name_a in enumerate(order):
        A = by_cat.get(name_a, [])
        if not A:
            continue

        same_pairs = find_actual_pairs(A, A, same_category=True)
        for a, b in same_pairs:
            key = pair_key(a, b)
            if key not in pair_seen:
                pair_seen.add(key)
                pair_list.append((name_a, name_a, a, b))

        for j in range(i + 1, len(order)):
            name_b = order[j]
            B = by_cat.get(name_b, [])
            if not B:
                continue

            cross_pairs = find_actual_pairs(A, B, same_category=False)
            for a, b in cross_pairs:
                key = pair_key(a, b)
                if key not in pair_seen:
                    pair_seen.add(key)
                    pair_list.append((name_a, name_b, a, b))

    pair_counts = {}
    for ca, cb, a, b in pair_list:
        key = "%s ↔ %s" % (ca, cb)
        pair_counts[key] = pair_counts.get(key, 0) + 1

    if not show_confirmation(order, scope_name, pair_counts):
        return

    result_counts = {
        "NEW_JOIN": 0,
        "SWITCHED": 0,
        "ALREADY_CORRECT": 0,
        "NOT_JOINED": 0,
        "WRONG_PRIORITY": 0,
        "FAILED": 0,
    }

    failed_examples = []

    with revit.Transaction("Autojoin/Unjoin"):
        order_index = dict((name, i) for i, name in enumerate(order))

        for ca, cb, a, b in pair_list:
            if order_index[ca] <= order_index[cb]:
                priority = a
                other = b
            else:
                priority = b
                other = a

            status = enforce_pair(priority, other)
            result_counts[status] += 1

            if status in ["NOT_JOINED", "WRONG_PRIORITY", "FAILED"]:
                if len(failed_examples) < 50:
                    failed_examples.append(
                        "%s ID %d ↔ %s ID %d : %s" %
                        (ca, a.Id.IntegerValue, cb, b.Id.IntegerValue, status)
                    )

    # The Transaction context has now committed completely.
    # Force one final regeneration and active-view refresh BEFORE showing
    # the success dialog, so the user only sees the result after Revit has
    # finished applying the Join/Unjoin changes.
    try:
        doc.Regenerate()
    except:
        pass

    try:
        revit.uidoc.RefreshActiveView()
    except:
        try:
            uidoc.RefreshActiveView()
        except:
            pass

    total_join = len(pair_list)
    show_success_result(scope_name, total_join)


def main():
    win = AutojoinWindow()
    win.ShowDialog()

    if not win.result:
        return

    current_view = win.result["current_view"]
    order = win.result["order"]

    run_autojoin(order, current_view)

if __name__ == "__main__":
    main()
