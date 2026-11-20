from __future__ import annotations

from typing import Literal
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field, model_validator


def uid() -> str:
    return uuid4().hex


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Reference(Model):
    source_id: str
    page: int = Field(default=1, ge=1)
    quote: str = ""


class Series(Model):
    label: str = ""
    expression: str = ""
    x: list[float] = Field(default_factory=list, max_length=10000)
    y: list[float] = Field(default_factory=list, max_length=10000)
    style: Literal["solid", "dashed", "dotted", "dashdot"] = "solid"


class Node(Model):
    id: str
    label: str
    x: float = Field(ge=0, le=1000)
    y: float = Field(ge=0, le=1000)


class Edge(Model):
    start: str
    end: str
    label: str = ""
    kind: Literal["wire", "resistor", "capacitor", "inductor", "voltage", "arrow"] = (
        "arrow"
    )


class ControlPoint(Model):
    x: float = Field(ge=0, le=1000)
    y: float = Field(ge=0, le=1000)


ControlPort = Literal["left", "right", "top", "bottom", "lower_left", "lower_right"]


class ControlNode(ControlPoint):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    kind: Literal["input", "output", "block", "sum", "branch"]
    label: str = Field(default="", max_length=160)
    math: str = Field(default="", max_length=160)
    tag: str = Field(default="", max_length=32)
    width: float = Field(default=100, ge=50, le=250)
    height: float = Field(default=80, ge=40, le=160)

    @model_validator(mode="after")
    def valid_label(self):
        if self.label and self.math:
            raise ValueError("اختر label أو math للتسمية")
        if self.kind in ("sum", "branch") and (self.label or self.math):
            raise ValueError("الجامع والتفرع رمزان؛ ضع التفسير في التعليق")
        if self.kind in ("input", "output", "block") and not (self.label.strip() or self.math.strip()):
            raise ValueError("تسمية العقدة مطلوبة")
        if self.math:
            from matplotlib.mathtext import MathTextParser
            if "$" in self.math:
                raise ValueError("math لا يقبل محددات الدولار")
            MathTextParser("path").parse("$"+self.math+"$")
        return self

    def port(self, side):
        if side.startswith("lower_"):
            if self.kind != "sum":
                raise ValueError("المنافذ السفلية المزدوجة للجامع فقط")
            return (self.x + (-10.8 if side == "lower_left" else 10.8), self.y + 14.4)
        dx, dy = {"left": (-1, 0), "right": (1, 0), "top": (0, -1), "bottom": (0, 1)}[side]
        rx, ry = (self.width/2, self.height/2) if self.kind == "block" else ((18,18) if self.kind == "sum" else (0,0))
        return self.x + dx*rx, self.y + dy*ry


class ControlEdge(Model):
    start: str
    end: str
    start_port: ControlPort = "right"
    end_port: ControlPort = "left"
    sign: Literal["+", "-", ""] = ""
    bends: list[ControlPoint] = Field(default_factory=list, max_length=12)


class ControlDiagram(Model):
    nodes: list[ControlNode] = Field(min_length=2, max_length=60)
    edges: list[ControlEdge] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def valid_graph(self):
        nodes = {n.id: n for n in self.nodes}
        if len(nodes) != len(self.nodes):
            raise ValueError("معرفات العقد مكررة")
        incoming = {k: [] for k in nodes}; outgoing = {k: [] for k in nodes}
        ports = set()
        for e in self.edges:
            if e.start not in nodes or e.end not in nodes or e.start == e.end:
                raise ValueError("مرجع عقدة غير صالح")
            a, b = nodes[e.start], nodes[e.end]
            if bool(e.sign) != (b.kind == "sum"):
                raise ValueError("كل مدخل جامع يحتاج إشارة مستقلة؛ الإشارات للجوامع فقط")
            for node, port in [(a,e.start_port),(b,e.end_port)]:
                if (node.id,port) in ports:
                    raise ValueError("المنفذ مشغول؛ استعمل عقدة branch صريحة للتفرع")
                ports.add((node.id,port))
            points=[a.port(e.start_port)]+[(p.x,p.y) for p in e.bends]+[b.port(e.end_port)]
            for (x,y),(xx,yy) in zip(points,points[1:]):
                if (abs(x-xx)>1e-6 and abs(y-yy)>1e-6) or (x==xx and y==yy):
                    raise ValueError("المسار يجب أن يكون متعامدًا دون مقاطع صفرية")
            for side, origin, adjacent in [(e.start_port,points[0],points[1]),(e.end_port,points[-1],points[-2])]:
                dx,dy=adjacent[0]-origin[0], adjacent[1]-origin[1]
                valid = {"left":dx<0 and abs(dy)<1e-6,"right":dx>0 and abs(dy)<1e-6,"top":dy<0 and abs(dx)<1e-6,"bottom":dy>0 and abs(dx)<1e-6,"lower_left":dy>0 and abs(dx)<1e-6,"lower_right":dy>0 and abs(dx)<1e-6}
                if not valid[side]:
                    raise ValueError("المسار يدخل المنفذ من جهة غير صحيحة")
            incoming[e.end].append(e); outgoing[e.start].append(e)
        for k,n in nodes.items():
            i,o=len(incoming[k]),len(outgoing[k])
            valid={"input":i==0 and o==1,"output":i==1 and o==0,"block":i==1 and o==1,"sum":2<=i<=3 and o==1,"branch":i==1 and 2<=o<=3}
            if not valid[n.kind]:
                raise ValueError("عدد توصيلات غير صالح للعقدة " + k)
        if sum(n.kind=="input" for n in self.nodes)!=1 or sum(n.kind=="output" for n in self.nodes)!=1:
            raise ValueError("مخطط التحكم يدعم دخلًا وخرجًا خارجيين فقط")
        reachable={next(n.id for n in self.nodes if n.kind=="input")}
        while True:
            expanded=reachable|{e.end for e in self.edges if e.start in reachable}
            if expanded==reachable: break
            reachable=expanded
        if reachable!=set(nodes):
            raise ValueError("توجد عقد منفصلة عن الدخل")
        from .control_geometry import check_geometry
        check_geometry(self)
        return self


class Figure(Model):
    kind: Literal[
        "plot",
        "step",
        "ramp",
        "impulse",
        "bar",
        "histogram",
        "scatter",
        "block_diagram",
        "circuit",
        "source_crop",
        "control_diagram",
    ]
    caption: str = ""
    xlabel: str = "t"
    ylabel: str = ""
    xmin: float = -2
    xmax: float = 4
    series: list[Series] = Field(default_factory=list, max_length=8)
    labels: list[str] = Field(default_factory=list, max_length=200)
    values: list[float] = Field(default_factory=list, max_length=10000)
    bins: int = Field(default=10, ge=1, le=100)
    nodes: list[Node] = Field(default_factory=list, max_length=100)
    edges: list[Edge] = Field(default_factory=list, max_length=200)
    control: ControlDiagram | None = None
    crop: list[float] | None = Field(default=None, min_length=4, max_length=4)

    @model_validator(mode="after")
    def valid_figure(self):
        if (self.kind == "control_diagram") != (self.control is not None):
            raise ValueError("control مطلوب فقط لنوع control_diagram")
        if self.xmax <= self.xmin:
            raise ValueError("الحد الأعلى للمحور يجب أن يتجاوز الحد الأدنى")
        if self.kind in ("plot", "scatter"):
            if not self.series:
                raise ValueError("الرسم يحتاج دالة أو بيانات من المصدر")
            for s in self.series:
                if self.kind == "scatter" and s.expression:
                    raise ValueError("المخطط المبعثر يحتاج بيانات فعلية")
                if not s.expression and (not s.x or len(s.x) != len(s.y)):
                    raise ValueError("بيانات المحورين غير مكتملة")
        if self.kind in ("bar", "histogram") and not self.values:
            raise ValueError("لا توجد بيانات للرسم الإحصائي")
        if self.kind == "bar" and len(self.values) != len(self.labels):
            raise ValueError("عدد التسميات لا يطابق عدد القيم")
        if self.kind in ("block_diagram", "circuit"):
            ids = {n.id for n in self.nodes}
            if not ids or len(ids) != len(self.nodes):
                raise ValueError("عُقد الرسم مفقودة أو مكررة")
            if any(
                e.start not in ids or e.end not in ids or e.start == e.end
                for e in self.edges
            ):
                raise ValueError("توصيلات الرسم تشير إلى عقد غير صالحة")
        if self.crop and not (
            0 <= self.crop[0] < self.crop[2] <= 1
            and 0 <= self.crop[1] < self.crop[3] <= 1
        ):
            raise ValueError("منطقة القص يجب أن تكون نسبًا بين صفر وواحد")
        return self


KINDS = Literal[
    "definition",
    "rule",
    "explanation",
    "list",
    "example",
    "exercise",
    "equation",
    "figure",
    "table",
    "note",
    "warning",
]


class Block(Model):
    id: str = Field(default_factory=uid)
    kind: KINDS
    title: str = ""
    text: str = ""
    latex: str = ""
    items: list[str] = Field(default_factory=list, max_length=500)
    ordered: bool = False
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    figure: Figure | None = None
    problem: str = ""
    givens: str = ""
    steps: list[str] = Field(default_factory=list)
    result: str = ""
    verbatim: bool = False
    origin: Literal[
        "source",
        "clarification",
        "additional_exercise",
        "instructor_example",
        "book_question",
    ] = "source"
    refs: list[Reference] = Field(default_factory=list)
    issue: str = ""
    correction: str = ""
    issue_resolved: bool = False

    @model_validator(mode="after")
    def content_present(self):
        if (self.items or self.ordered) and self.kind != "list":
            raise ValueError("عناصر القائمة تتطلب نوع list")
        if self.kind == "list" and (
            not self.items or any(not item.strip() for item in self.items)
        ):
            raise ValueError("القائمة تحتاج عناصر غير فارغة")
        if self.latex and self.kind != "equation":
            raise ValueError(
                "ضع LaTeX داخل النص أو في كتلة معادلة؛ الحقل latex مخصص للمعادلات"
            )
        if (
            self.problem or self.givens or self.steps or self.result or self.verbatim
        ) and self.kind != "exercise":
            raise ValueError("حقول المسألة تتطلب نوع exercise")
        if (self.headers or self.rows) and self.kind != "table":
            raise ValueError("صفوف الجدول تتطلب نوع table")
        if self.figure and self.kind != "figure":
            raise ValueError("مواصفات الرسم تتطلب نوع figure")
        if self.kind == "equation" and not self.latex.strip():
            raise ValueError("المعادلة فارغة")
        if self.kind == "figure" and (not self.figure or not self.refs):
            raise ValueError("الرسم يحتاج مواصفات ومرجعًا إلى مصدره")
        if self.kind == "table" and (
            not self.headers or any(len(r) != len(self.headers) for r in self.rows)
        ):
            raise ValueError("أعمدة الجدول وصفوفه غير متطابقة")
        if self.kind == "exercise" and not self.problem.strip():
            raise ValueError("نص المسألة مطلوب")
        if self.verbatim and (
            self.kind != "exercise" or not any(r.quote for r in self.refs)
        ):
            raise ValueError("السؤال الحرفي يحتاج مقتطفًا مرجعيًا للمقارنة")
        return self


class Section(Model):
    id: str = Field(default_factory=uid)
    title: str
    palette: Literal["cinnamon", "honey", "olive"] = "cinnamon"
    blocks: list[Block] = Field(default_factory=list)
    complete: bool = False


class LayoutOptions(Model):
    page_before: bool = False
    keep_together: Literal["auto", "keep", "split"] = "auto"
    keep_with_next: bool = False
    direction: Literal["auto", "rtl", "ltr"] = "auto"


class Settings(Model):
    font_size: float = Field(default=14.5, ge=11, le=20)
    line_spacing: float = Field(default=1.45, ge=1, le=2)
    margin_mm: float = Field(default=19, ge=12, le=28)
    end_marker: bool = True
    math_mode: Literal["native", "portable"] = "native"
    embed_fonts: bool = True
    toc_pages: bool = False  # Legacy field accepted; the index no longer shows page numbers.
    layout: dict[str, LayoutOptions] = Field(default_factory=dict)


class LectureDocument(Model):
    schema_version: Literal[1] = 1
    title: str = "محاضرة جديدة"
    course: str = ""
    number: str = "01"
    doctor: str = ""
    settings: Settings = Field(default_factory=Settings)
    sections: list[Section] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [s.id for s in self.sections] + [
            b.id for s in self.sections for b in s.blocks
        ]
        if len(ids) != len(set(ids)):
            raise ValueError("معرّفات الأقسام والعناصر يجب أن تكون فريدة")
        return self
