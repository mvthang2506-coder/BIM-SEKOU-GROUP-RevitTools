# -*- coding: utf-8 -*-
from pyrevit import revit, DB, forms, script
import math

doc = revit.doc
uidoc = revit.uidoc
view = doc.ActiveView
out = script.get_output()

TOL = 1e-8
MM = 1.0 / 304.8

# ============================================================
# DIM TÂM - GỘP DẦM + CỘT
# 1 button -> chọn DẦM hoặc CỘT
# Sau đó chọn phạm vi + phương X/Y.
#
# DẦM: Grid -> tâm dầm
# CỘT: Grid -> tâm cột
# Không tạo helper line.
# Hỗ trợ DIM = 0 khi tâm trùng Grid.
# ============================================================

def get_point(e):
    try:
        if isinstance(e.Location, DB.LocationPoint):
            return e.Location.Point
    except:
        pass
    try:
        return e.GetTransform().Origin
    except:
        return None


def get_beam_point(e):
    try:
        loc = e.Location
        if isinstance(loc, DB.LocationCurve):
            return loc.Curve.Evaluate(0.5, True)
    except:
        pass
    return get_point(e)


def get_selected(kind):
    result = []
    for eid in uidoc.Selection.GetElementIds():
        e = doc.GetElement(eid)
        if not e or not e.Category:
            continue

        cid = e.Category.Id.IntegerValue

        if kind == "BEAM" and cid == int(DB.BuiltInCategory.OST_StructuralFraming):
            if isinstance(e, DB.FamilyInstance):
                p = get_beam_point(e)
                if p:
                    result.append((e, p))

        elif kind == "COLUMN" and cid == int(DB.BuiltInCategory.OST_StructuralColumns):
            if isinstance(e, DB.FamilyInstance):
                p = get_point(e)
                if p:
                    result.append((e, p))

    return result


def get_all(kind):
    bic = (DB.BuiltInCategory.OST_StructuralFraming
           if kind == "BEAM"
           else DB.BuiltInCategory.OST_StructuralColumns)

    result = []
    elems = (DB.FilteredElementCollector(doc, view.Id)
             .OfCategory(bic)
             .WhereElementIsNotElementType()
             .ToElements())

    for e in elems:
        if isinstance(e, DB.FamilyInstance):
            p = get_beam_point(e) if kind == "BEAM" else get_point(e)
            if p:
                result.append((e, p))

    return result


def get_grids():
    result = []

    for g in (DB.FilteredElementCollector(doc)
              .OfClass(DB.Grid)
              .WhereElementIsNotElementType()
              .ToElements()):
        try:
            c = g.Curve
            p0 = c.GetEndPoint(0)
            p1 = c.GetEndPoint(1)

            dx = p1.X - p0.X
            dy = p1.Y - p0.Y
            length = math.hypot(dx, dy)

            if length < TOL:
                continue

            if abs(dy) >= 0.95 * length:
                ori = "VERTICAL"
            elif abs(dx) >= 0.95 * length:
                ori = "HORIZONTAL"
            else:
                ori = "OTHER"

            if ori != "OTHER":
                result.append((g, c, ori))

        except:
            pass

    return result


def project_to_grid(curve, p):
    a = curve.GetEndPoint(0)
    b = curve.GetEndPoint(1)

    vx = b.X - a.X
    vy = b.Y - a.Y
    den = vx * vx + vy * vy

    if den < TOL:
        return None

    t = ((p.X - a.X) * vx + (p.Y - a.Y) * vy) / den
    t = max(0.0, min(1.0, t))

    return DB.XYZ(
        a.X + t * vx,
        a.Y + t * vy,
        p.Z
    )


def nearest_grid(p, grids, orientation):
    best = None
    best_dist = 1e100

    for g, c, ori in grids:
        if ori != orientation:
            continue

        q = project_to_grid(c, p)
        if q is None:
            continue

        d = abs(p.X - q.X) if orientation == "VERTICAL" else abs(p.Y - q.Y)

        if d < best_dist:
            best_dist = d
            best = (g, c, q, d)

    return best


def get_center_ref(instance, direction):
    """
    Lấy Center Reference thật của FamilyInstance.
    Không tạo DetailLine/ModelLine.
    """

    try:
        tr = instance.GetTransform()

        bx = DB.XYZ(tr.BasisX.X, tr.BasisX.Y, 0.0)
        by = DB.XYZ(tr.BasisY.X, tr.BasisY.Y, 0.0)

        if bx.GetLength() > TOL:
            bx = bx.Normalize()
        if by.GetLength() > TOL:
            by = by.Normalize()

        target = DB.XYZ.BasisX if direction == "X" else DB.XYZ.BasisY

        pairs = [
            (DB.FamilyInstanceReferenceType.CenterLeftRight, bx),
            (DB.FamilyInstanceReferenceType.CenterFrontBack, by)
        ]

        scored = []

        for ref_type, normal in pairs:
            try:
                score = abs(normal.DotProduct(target))
                refs = instance.GetReferences(ref_type)

                for r in refs:
                    scored.append((score, r))
            except:
                pass

        if scored:
            scored.sort(key=lambda x: x[0], reverse=True)
            return scored[0][1]

    except:
        pass

    try:
        ref_type = (
            DB.FamilyInstanceReferenceType.CenterLeftRight
            if direction == "X"
            else DB.FamilyInstanceReferenceType.CenterFrontBack
        )

        refs = instance.GetReferences(ref_type)

        if refs:
            return refs[0]

    except:
        pass

    return None


def create_dimension(instance, p, grid_info, direction):
    grid, grid_curve, projected, distance = grid_info

    center_ref = get_center_ref(instance, direction)

    if center_ref is None:
        raise Exception(
            "Family không có CenterLeftRight / CenterFrontBack Reference."
        )

    refs = DB.ReferenceArray()
    refs.Append(DB.Reference(grid))
    refs.Append(center_ref)

    # Dimension line phải có chiều dài > 0 kể cả khi DIM = 0.
    offset = 300.0 * MM
    span = 300.0 * MM

    if direction == "X":
        y = p.Y + offset
        a = min(projected.X, p.X)
        b = max(projected.X, p.X)

        line = DB.Line.CreateBound(
            DB.XYZ(a - span, y, p.Z),
            DB.XYZ(b + span, y, p.Z)
        )

    else:
        x = p.X + offset
        a = min(projected.Y, p.Y)
        b = max(projected.Y, p.Y)

        line = DB.Line.CreateBound(
            DB.XYZ(x, a - span, p.Z),
            DB.XYZ(x, b + span, p.Z)
        )

    return doc.Create.NewDimension(view, line, refs)


# ------------------------------------------------------------
# View check
# ------------------------------------------------------------
allowed = [
    DB.ViewType.FloorPlan,
    DB.ViewType.CeilingPlan,
    DB.ViewType.EngineeringPlan,
    DB.ViewType.AreaPlan
]

if view.ViewType not in allowed:
    forms.alert(
        "Hãy chạy tool trong Plan View.",
        title="DIM Tâm",
        exitscript=True
    )


# ------------------------------------------------------------
# 1. Chọn DẦM hoặc CỘT
# ------------------------------------------------------------
kind = forms.CommandSwitchWindow.show(
    [
        "DẦM",
        "CỘT"
    ],
    message="Chọn đối tượng cần DIM tâm"
)

if not kind:
    script.exit()

is_beam = kind == "DẦM"
kind_code = "BEAM" if is_beam else "COLUMN"


# ------------------------------------------------------------
# 2. Chọn phạm vi
# ------------------------------------------------------------
scope = forms.CommandSwitchWindow.show(
    [
        "ĐANG CHỌN (TEST)",
        "TẤT CẢ TRONG VIEW"
    ],
    message="Chọn phạm vi tạo DIM"
)

if not scope:
    script.exit()

if scope.startswith("ĐANG"):
    elements = get_selected(kind_code)

    if not elements:
        forms.alert(
            "Hãy chọn {} trước khi chạy.".format("dầm" if is_beam else "cột"),
            title="DIM Tâm",
            exitscript=True
        )
else:
    elements = get_all(kind_code)


# ------------------------------------------------------------
# 3. Chọn phương
# ------------------------------------------------------------
direction = forms.CommandSwitchWindow.show(
    [
        "CẢ HAI PHƯƠNG X + Y",
        "CHỈ X (Grid đứng → tâm)",
        "CHỈ Y (Grid ngang → tâm)"
    ],
    message="Chọn phương DIM"
)

if not direction:
    script.exit()

do_x = direction.startswith("CẢ HAI") or direction.startswith("CHỈ X")
do_y = direction.startswith("CẢ HAI") or direction.startswith("CHỈ Y")


grids = get_grids()

if not grids:
    forms.alert(
        "Không tìm thấy Grid.",
        title="DIM Tâm",
        exitscript=True
    )


# ------------------------------------------------------------
# 4. Create DIM
# ------------------------------------------------------------
ok_x = 0
ok_y = 0
no_grid_x = 0
no_grid_y = 0
errors = []

tx = DB.Transaction(doc, "DIM Tam - Beam/Column")
tx.Start()

try:

    for instance, p in elements:

        if do_x:
            try:
                gi = nearest_grid(p, grids, "VERTICAL")

                if gi is None:
                    no_grid_x += 1
                else:
                    create_dimension(instance, p, gi, "X")
                    ok_x += 1

            except Exception as ex:
                errors.append(
                    "{} {} / X: {}".format(
                        "Beam" if is_beam else "Column",
                        instance.Id.IntegerValue,
                        ex
                    )
                )

        if do_y:
            try:
                gi = nearest_grid(p, grids, "HORIZONTAL")

                if gi is None:
                    no_grid_y += 1
                else:
                    create_dimension(instance, p, gi, "Y")
                    ok_y += 1

            except Exception as ex:
                errors.append(
                    "{} {} / Y: {}".format(
                        "Beam" if is_beam else "Column",
                        instance.Id.IntegerValue,
                        ex
                    )
                )

    tx.Commit()

except Exception as ex:

    try:
        tx.RollBack()
    except:
        pass

    forms.alert(
        "Lỗi Transaction:\n\n{}".format(ex),
        title="DIM Tâm",
        exitscript=True
    )


# ------------------------------------------------------------
# Report
# ------------------------------------------------------------
out.print_md("# DIM Tâm")
out.print_md("")
out.print_md(
    "**Đối tượng:** {}  \n"
    "**Số lượng:** {}  \n"
    "**DIM X:** {}  \n"
    "**DIM Y:** {}  \n"
    "**Không có Grid:** X={} / Y={}  \n"
    "**Lỗi:** {}".format(
        "Dầm" if is_beam else "Cột",
        len(elements),
        ok_x,
        ok_y,
        no_grid_x,
        no_grid_y,
        len(errors)
    )
)

if errors:
    out.print_md("")
    out.print_md("## Chi tiết lỗi")

    for e in errors[:30]:
        out.print_md("- " + e)


forms.alert(
    "DIM Tâm hoàn tất.\n\n"
    "Đối tượng: {}\n"
    "DIM X: {}\n"
    "DIM Y: {}\n"
    "Lỗi: {}".format(
        "Dầm" if is_beam else "Cột",
        ok_x,
        ok_y,
        len(errors)
    ),
    title="DIM Tâm"
)
