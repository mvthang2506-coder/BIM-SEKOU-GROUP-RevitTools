# -*- coding: utf-8 -*-
from pyrevit import revit, DB, forms, script
import math

doc=revit.doc
uidoc=revit.uidoc
out=script.get_output()

FT_MM=304.8
MM_FT=1.0/FT_MM
TOL_MM=0.01
NUDGE_MM=10.0

def get_center(e,kind):
    try:
        loc=e.Location
        if kind=="Dầm" and isinstance(loc,DB.LocationCurve):
            return loc.Curve.Evaluate(0.5,True)
        if kind=="Cột" and isinstance(loc,DB.LocationPoint):
            return loc.Point
    except: pass
    try: return e.GetTransform().Origin
    except: return None

def selected():
    r=[]
    for eid in uidoc.Selection.GetElementIds():
        e=doc.GetElement(eid)
        if not e or not e.Category: continue
        cid=e.Category.Id.IntegerValue
        if cid==int(DB.BuiltInCategory.OST_StructuralFraming) and isinstance(e,DB.FamilyInstance):
            p=get_center(e,"Dầm")
            if p:r.append(("Dầm",e,p))
        elif cid==int(DB.BuiltInCategory.OST_StructuralColumns) and isinstance(e,DB.FamilyInstance):
            p=get_center(e,"Cột")
            if p:r.append(("Cột",e,p))
    return r

def grids():
    r=[]
    for g in DB.FilteredElementCollector(doc).OfClass(DB.Grid).WhereElementIsNotElementType():
        try:
            c=g.Curve;a=c.GetEndPoint(0);b=c.GetEndPoint(1)
            dx=b.X-a.X;dy=b.Y-a.Y;L=math.hypot(dx,dy)
            if L<1e-9:continue
            ori="V" if abs(dy)>=.95*L else ("H" if abs(dx)>=.95*L else "O")
            if ori!="O":r.append((g,c,ori))
        except:pass
    return r

def project(c,p):
    a=c.GetEndPoint(0);b=c.GetEndPoint(1)
    vx=b.X-a.X;vy=b.Y-a.Y;den=vx*vx+vy*vy
    if den<1e-12:return None
    t=((p.X-a.X)*vx+(p.Y-a.Y)*vy)/den
    return DB.XYZ(a.X+t*vx,a.Y+t*vy,p.Z)

def nearest(p,gs,ori):
    best=None;bd=1e100
    for g,c,o in gs:
        if o!=ori:continue
        q=project(c,p)
        if q is None:continue
        d=abs(p.X-q.X) if ori=="V" else abs(p.Y-q.Y)
        if d<bd:bd=d;best=(g,c,q,d)
    return best

def move(e,v):
    loc=e.Location
    try:
        if isinstance(loc,(DB.LocationCurve,DB.LocationPoint)):
            loc.Move(v)
        else:
            DB.ElementTransformUtils.MoveElement(doc,e.Id,v)
    except:
        DB.ElementTransformUtils.MoveElement(doc,e.Id,v)

def target_point(center,gi,ori):
    g,c,q,dist=gi
    dist_mm=dist*FT_MM
    rounded_mm=round(dist_mm)
    if abs(dist_mm-rounded_mm)>TOL_MM:
        return None,dist_mm,rounded_mm

    target=DB.XYZ(center.X,center.Y,center.Z)
    d=rounded_mm*MM_FT

    if ori=="V":
        target=DB.XYZ(q.X + (d if center.X>=q.X else -d),center.Y,center.Z)
    else:
        target=DB.XYZ(center.X,q.Y + (d if center.Y>=q.Y else -d),center.Z)

    return target,dist_mm,rounded_mm

def snap_one(kind,e,ori,gs):
    center=get_center(e,kind)
    if center is None:return ("skip",0,0)

    gi=nearest(center,gs,ori)
    if gi is None:return ("nogrid",0,0)

    target,oldmm,newmm=target_point(center,gi,ori)
    if target is None:return ("outside",oldmm,newmm)

    dx=target.X-center.X
    dy=target.Y-center.Y
    delta=DB.XYZ(dx,dy,0)

    # Revit can ignore a microscopic move. Force a real move first,
    # then recompute the center and move exactly to the target.
    if delta.GetLength()<0.5*MM_FT:
        if ori=="V":
            nudge=DB.XYZ(NUDGE_MM*MM_FT,0,0)
        else:
            nudge=DB.XYZ(0,NUDGE_MM*MM_FT,0)
        move(e,nudge)
        center2=get_center(e,kind)
        if center2 is None:return ("error",0,0)
        delta=DB.XYZ(target.X-center2.X,target.Y-center2.Y,0)

    if delta.GetLength()>1e-12:
        move(e,delta)

    # Verify with a fresh center/grid calculation.
    center3=get_center(e,kind)
    gi3=nearest(center3,gs,ori) if center3 else None
    if gi3:
        remain=abs(center3.X-gi3[2].X)*FT_MM if ori=="V" else abs(center3.Y-gi3[2].Y)*FT_MM
    else:
        remain=999999

    return ("moved",oldmm,newmm,remain)

els=selected()
if not els:
    forms.alert("Hãy chọn Dầm hoặc Cột trước khi chạy.",title="Căn tròn vị trí",exitscript=True)

direction=forms.CommandSwitchWindow.show(
    ["CẢ HAI PHƯƠNG X + Y","CHỈ X (Grid đứng)","CHỈ Y (Grid ngang)"],
    message="Chọn phương cần căn tròn"
)
if not direction:script.exit()

do_x=direction.startswith("CẢ HAI") or direction.startswith("CHỈ X")
do_y=direction.startswith("CẢ HAI") or direction.startswith("CHỈ Y")
gs=grids()

moved=0;outside=0;nogrid=0;errors=[];remain_bad=[]
tx=DB.Transaction(doc,"Can tron vi tri V2")
tx.Start()
try:
    for kind,e,p in els:
        if do_x:
            try:
                r=snap_one(kind,e,"V",gs)
                if r[0]=="moved":
                    moved+=1
                    if len(r)>3 and r[3]>0.01:remain_bad.append("{} {} X còn {:.9f} mm".format(kind,e.Id.IntegerValue,r[3]))
                elif r[0]=="outside":outside+=1
                elif r[0]=="nogrid":nogrid+=1
            except Exception as ex:errors.append("{} {} X: {}".format(kind,e.Id.IntegerValue,ex))
        if do_y:
            try:
                r=snap_one(kind,e,"H",gs)
                if r[0]=="moved":
                    moved+=1
                    if len(r)>3 and r[3]>0.01:remain_bad.append("{} {} Y còn {:.9f} mm".format(kind,e.Id.IntegerValue,r[3]))
                elif r[0]=="outside":outside+=1
                elif r[0]=="nogrid":nogrid+=1
            except Exception as ex:errors.append("{} {} Y: {}".format(kind,e.Id.IntegerValue,ex))
    tx.Commit()
except Exception as ex:
    try:tx.RollBack()
    except:pass
    forms.alert("Lỗi Transaction:\n\n{}".format(ex),title="Căn tròn vị trí",exitscript=True)

out.print_md("# Căn tròn vị trí V2")
out.print_md("Đối tượng: {}".format(len(els)))
out.print_md("Đã căn: {}".format(moved))
out.print_md("Ngoài ngưỡng {:.3f} mm: {}".format(TOL_MM,outside))
out.print_md("Không có Grid: {}".format(nogrid))
out.print_md("Lỗi: {}".format(len(errors)))
if remain_bad:
    out.print_md("## Còn sai số sau khi căn")
    for x in remain_bad[:30]:out.print_md("- "+x)
if errors:
    out.print_md("## Lỗi")
    for x in errors[:30]:out.print_md("- "+x)

forms.alert(
    "Căn tròn vị trí V2 hoàn tất.\n\nĐã căn: {}\nNgoài ngưỡng: {}\nKhông có Grid: {}\nLỗi: {}\nCòn sai số >0.01mm: {}".format(
        moved,outside,nogrid,len(errors),len(remain_bad)),
    title="Căn tròn vị trí"
)
