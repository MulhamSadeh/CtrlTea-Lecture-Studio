export type ControlSpec = {
  nodes: {id:string;kind:"input"|"output"|"block"|"sum"|"branch";x:number;y:number;label?:string;math?:string;tag?:string;width?:number;height?:number}[];
  edges: {start:string;end:string;start_port:string;end_port:string;sign?:"+"|"-"|"";bends?:{x:number;y:number}[]}[];
};
export type Ref = { source_id: string; page: number; quote: string };
export type FigureSpec = {
  kind: string;
  caption: string;
  xlabel: string;
  ylabel: string;
  xmin: number;
  xmax: number;
  series: {
    label: string;
    expression: string;
    x: number[];
    y: number[];
    style: string;
  }[];
  labels: string[];
  values: number[];
  bins: number;
  nodes: { id: string; label: string; x: number; y: number }[];
  edges: { start: string; end: string; label: string; kind: string }[];
  crop: number[] | null;
  control?: ControlSpec | null;
};
export type Block = {
  id: string;
  kind: string;
  title: string;
  text: string;
  latex: string;
  items?: string[];
  ordered?: boolean;
  headers: string[];
  rows: string[][];
  figure: FigureSpec | null;
  problem: string;
  givens: string;
  steps: string[];
  result: string;
  verbatim: boolean;
  origin: string;
  refs: Ref[];
  issue: string;
  correction: string;
  issue_resolved: boolean;
};
export type Section = {
  id: string;
  title: string;
  palette: string;
  blocks: Block[];
  complete: boolean;
};
export type LayoutOptions = {
  page_before?: boolean;
  keep_together?: "auto" | "keep" | "split";
  keep_with_next?: boolean;
  direction?: "auto" | "rtl" | "ltr";
};
export type LectureDoc = {
  schema_version: 1;
  title: string;
  course: string;
  number: string;
  doctor: string;
  settings: {
    font_size: number;
    line_spacing: number;
    margin_mm: number;
    end_marker: boolean;
    math_mode?: "native" | "portable";
    embed_fonts?: boolean;
    toc_pages?: boolean;
    layout?: Record<string, LayoutOptions>;
  };
  sections: Section[];
};
export type Course = {
  id: string;
  name: string;
  doctor: string;
  lecture_count?: number;
};
export type Lecture = {
  id: string;
  course_id: string;
  title: string;
  revision: number;
  updated: string;
  theme: ThemeName;
  document: LectureDoc;
};
export type ThemeName = "cinnamon" | "honey" | "olive";
export type LectureTheme = {
  id: ThemeName;
  name: string;
  label: string;
  dark: string;
  medium: string;
  light: string;
};
export type Design = {
  default_theme: ThemeName;
  themes: LectureTheme[];
  fonts: Record<string, string>;
};
export type Source = {
  id: string;
  name: string;
  kind: string;
  priority: number;
  role: string;
  linked_id: string | null;
  page_count: number;
};
export type Page = {
  source_id: string;
  number: number;
  raw: string;
  corrected: string | null;
  excluded: number;
  method: string;
};
export type Job = {
  id: string;
  kind: string;
  status: string;
  progress: number;
  error: string | null;
  result: string | null;
};
export type Export = {
  export_id: string;
  revision: number;
  theme?: ThemeName;
  pages: number;
  equations: number;
  math_mode?: "native" | "portable";
  figures: number;
  created: string;
  draft: boolean;
  visual_review: string;
  checks: { issues: { message: string }[] };
};
export const id = () => crypto.randomUUID().replaceAll("-", "");
export const labels: Record<string, string> = {
  definition: "تعريف",
  rule: "قاعدة أو قانون",
  explanation: "شرح",
  list: "قائمة",
  example: "مثال",
  exercise: "مسألة محلولة",
  equation: "معادلة",
  figure: "رسم علمي",
  table: "جدول",
  note: "ملاحظة",
  warning: "تنبيه",
};
export function newBlock(kind: string, source?: Source): Block {
  return {
    id: id(),
    kind,
    title: "",
    text: "",
    latex: kind === "equation" ? "x = y" : "",
    items: kind === "list" ? ["عنصر من المصدر"] : [],
    ordered: false,
    headers: kind === "table" ? ["العمود الأول", "العمود الثاني"] : [],
    rows: kind === "table" ? [["", ""]] : [],
    figure:
      kind === "figure"
        ? {
            kind: "step",
            caption: "",
            xlabel: "t",
            ylabel: "",
            xmin: -2,
            xmax: 4,
            series: [],
            labels: [],
            values: [],
            bins: 10,
            nodes: [],
            edges: [],
            crop: null,
          }
        : null,
    problem: kind === "exercise" ? "أدخل نص المسألة من المصدر" : "",
    givens: "",
    steps: [],
    result: "",
    verbatim: false,
    origin: "source",
    refs: source ? [{ source_id: source.id, page: 1, quote: "" }] : [],
    issue: "",
    correction: "",
    issue_resolved: false,
  };
}
