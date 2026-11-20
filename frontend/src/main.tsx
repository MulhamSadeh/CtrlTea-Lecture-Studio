import React, { useState, useEffect, useRef, useCallback, useContext } from "react";
import { createRoot } from "react-dom/client";
import {
  BookOpen,
  Files,
  PenLine,
  Layers,
  FileOutput,
  Plus,
  ArrowLeft,
  Download,
  Upload,
  Trash2,
  ChevronDown,
  ChevronUp,
  Check,
  Clock,
  AlertCircle,
  Settings,
  History,
  Save,
  Leaf,
  ExternalLink,
  RefreshCw,
  X,
  Search,
  PanelLeftClose,
  Eye,
  Undo2,
  Redo2,
} from "lucide-react";
import katex from "katex";
import "katex/dist/katex.min.css";
import "./style.css";
import { api, apiRaw, apiURL, download, ApiError, ValidationIssue } from "./api";
import { ControlDiagramEditor, initialControl } from "./ControlDiagramEditor";
import { AccountRoot } from "./Accounts";
import { WorkspaceStorage } from "./workspaceStorage";
import {FileDrop} from "./FileDrop";
import {Transfers} from "./Transfers";
import {
  Block,
  Course,
  Lecture,
  LectureDoc,
  Source,
  Section,
  Job,
  Export,
  id,
  labels,
  Design,
  LectureTheme,
  ThemeName,
  newBlock,
  Page,
  FigureSpec,
  LayoutOptions,
} from "./types";

function MathText({
  value,
  display = false,
}: {
  value: string;
  display?: boolean;
}) {
  if (display) {
    try {
      return (
        <div
          className="math"
          dir="ltr"
          dangerouslySetInnerHTML={{
            __html: katex.renderToString(value, {
              throwOnError: true,
              displayMode: true,
            }),
          }}
        />
      );
    } catch {
      return (
        <div className="inline-error">
          صيغة غير مدعومة في المعاينة: <bdi>{value}</bdi>
        </div>
      );
    }
  }
  return (
    <>
      {value.split(/(\\\([\s\S]*?\\\)|\$(?!\$)[^\n$]+\$)/g).map((part, i) => {
        if (
          (part.startsWith("\\(") && part.endsWith("\\)")) ||
          (part.startsWith("$") && part.endsWith("$"))
        ) {
          const v = part.startsWith("$")
            ? part.slice(1, -1)
            : part.slice(2, -2);
          try {
            return (
              <span
                key={i}
                dir="ltr"
                className="inline-math"
                dangerouslySetInnerHTML={{
                  __html: katex.renderToString(v, { throwOnError: true }),
                }}
              />
            );
          } catch {
            return (
              <bdi key={i} className="inline-error">
                {v}
              </bdi>
            );
          }
        }
        return <React.Fragment key={i}>{part}</React.Fragment>;
      })}
    </>
  );
}
function Field({
  label,
  value,
  onChange,
  area = false,
  dir,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (s: string) => void;
  area?: boolean;
  dir?: string;
  placeholder?: string;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {area ? (
        <textarea
          aria-label={label}
          dir={dir}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
        />
      ) : (
        <input
          aria-label={label}
          dir={dir}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
        />
      )}
    </label>
  );
}
function Empty({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <BookOpen size={28} />
      </div>
      <h2>{title}</h2>
      <p>{description}</p>
      {children}
    </div>
  );
}
function themeStyle(theme?: LectureTheme): React.CSSProperties {
  return theme
    ? ({
        "--accent": theme.dark,
        "--medium": theme.medium,
        "--tint": theme.light,
      } as React.CSSProperties)
    : {};
}

function ThemePicker({
  themes,
  value,
  onChange,
  disabled = false,
}: {
  themes: LectureTheme[];
  value: ThemeName;
  onChange: (value: ThemeName) => void;
  disabled?: boolean;
}) {
  return (
    <fieldset className="theme-picker" disabled={disabled}>
      <legend>لون المحاضرة — Lecture Theme</legend>
      <div
        className="theme-options"
        role="radiogroup"
        aria-label="لون المحاضرة"
      >
        {themes.map((theme) => (
          <label
            key={theme.id}
            className={"theme-option " + (value === theme.id ? "selected" : "")}
            style={themeStyle(theme)}
          >
            <input
              type="radio"
              name="lecture-theme"
              value={theme.id}
              aria-label={theme.name}
              checked={value === theme.id}
              onChange={() => onChange(theme.id)}
            />
            <span className="theme-option-label">
              <span>
                <b dir="ltr">{theme.name}</b>
                <small>{theme.label}</small>
              </span>
              <i className="theme-swatch" />
              {value === theme.id && <Check size={15} />}
            </span>
            <span className="theme-sample" aria-hidden="true">
              <span className="theme-sample-box">
                تعريف <span>محتوى المحاضرة</span>
              </span>
              <span className="theme-sample-footer">
                <b>2</b>
                <span>Ctrl+Tea</span>
              </span>
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function App() {
  const storage = useContext(WorkspaceStorage);
  const [transferOpen,setTransferOpen]=useState(false);
  useEffect(()=>{
    const preventFileNavigation=(event:DragEvent)=>{if(event.dataTransfer?.types.includes("Files"))event.preventDefault();};
    window.addEventListener("dragover",preventFileNavigation);
    window.addEventListener("drop",preventFileNavigation);
    return ()=>{window.removeEventListener("dragover",preventFileNavigation);window.removeEventListener("drop",preventFileNavigation);};
  },[]);
  const [design, setDesign] = useState<Design | null>(null),
    [themeId, setThemeId] = useState<ThemeName>("cinnamon"),
    [newTheme, setNewTheme] = useState<ThemeName>("cinnamon"),
    [themeSaving, setThemeSaving] = useState(false);
  const lectureTheme = design?.themes.find((t) => t.id === themeId);
  const [courses, setCourses] = useState<Course[]>([]),
    [cid, setCid] = useState(storage.getItem("ct-course") || ""),
    [lectures, setLectures] = useState<Lecture[]>([]),
    [lid, setLid] = useState(storage.getItem("ct-lecture") || "");
  const [doc, setDoc] = useState<LectureDoc | null>(null),
    [tab, setTab] = useState(storage.getItem("ct-tab") || "courses"),
    [sources, setSources] = useState<Source[]>([]),
    [jobs, setJobs] = useState<Job[]>([]),
    [exports, setExports] = useState<Export[]>([]);
  const [message, setMessage] = useState(""),
    [error, setError] = useState(""),
    [dirty, setDirty] = useState(false),
    [saving, setSaving] = useState(false),
    [modal, setModal] = useState(""),
    [courseName, setCourseName] = useState(""),
    [doctor, setDoctor] = useState(""),
    [lectureTitle, setLectureTitle] = useState(""),
    [lectureNumber, setLectureNumber] = useState("01"),
    [query, setQuery] = useState(""),
    [refresh, setRefresh] = useState(0),
    [stashed, setStashed] = useState<any>(null);
  const undoStack = useRef<LectureDoc[]>([]),
    redoStack = useRef<LectureDoc[]>([]);
  const docRef = useRef<LectureDoc | null>(null),
    revision = useRef(0),
    dirtyRef = useRef(false),
    savePromise = useRef<Promise<boolean> | null>(null),
    lidRef = useRef(lid),
    lastJob = useRef("");
  const notify = (m: string) => {
    setMessage(m);
    setTimeout(() => setMessage(""), 6000);
  };
  const act = async (fn: () => Promise<any>) => {
    try {
      return await fn();
    } catch (e) {
      setError((e as Error).message);
      return null;
    }
  };
  const loadCourses = async () => setCourses(await api("/courses"));
  const loadLecture = async (target: string) => {
    if (!target) {
      setDoc(null);
      docRef.current = null;
      return;
    }
    const row = await api<Lecture>("/lectures/" + target);
    if (target !== lidRef.current) return;
    setThemeId(row.theme);
    revision.current = row.revision;
    undoStack.current = [];
    redoStack.current = [];
    let incoming = row.document;
    let restored = false;
    try {
      const draft = JSON.parse(
        storage.getItem("ct-draft-" + target) || "null",
      );
      if (draft) {
        if (draft.revision === row.revision) {
          incoming = draft.document;
          restored = true;
          notify("استُعيدت تعديلاتك المحلية غير المحفوظة.");
        } else setStashed(draft);
      }
    } catch {}
    docRef.current = incoming;
    setDoc(incoming);
    setDirty(restored);
    dirtyRef.current = restored;
  };
  const reload = async () => {
    if (!lidRef.current) return;
    const target = lidRef.current;
    const [s, j, e] = await Promise.all([
      api<Source[]>("/lectures/" + target + "/sources"),
      api<Job[]>("/lectures/" + target + "/jobs"),
      api<Export[]>("/lectures/" + target + "/exports"),
    ]);
    if (target !== lidRef.current) return;
    setSources(s);
    setJobs(j);
    setExports(e);
  };
  useEffect(() => {
    act(loadCourses);
    act(async () => setDesign(await api<Design>("/design")));
  }, []);
  useEffect(() => {
    storage.setItem("ct-course", cid);
    if (cid)
      act(async () => setLectures(await api("/courses/" + cid + "/lectures")));
    else setLectures([]);
  }, [cid, refresh]);
  useEffect(() => {
    lidRef.current = lid;
    storage.setItem("ct-lecture", lid);
    setStashed(null);
    setSources([]);
    setJobs([]);
    setExports([]);
    act(() => loadLecture(lid));
    if (lid) act(reload);
  }, [lid]);
  useEffect(() => {
    storage.setItem("ct-tab", tab);
  }, [tab]);
  useEffect(() => {
    if (!lid) return;
    const t = setInterval(() => {
      act(async () => {
        const j = await api<Job[]>("/lectures/" + lid + "/jobs");
        setJobs(j);
        const signature = j.map((x) => x.id + x.status).join();
        if (signature !== lastJob.current) {
          lastJob.current = signature;
          await reload();
          setRefresh((v) => v + 1);
        }
      });
    }, 1800);
    return () => clearInterval(t);
  }, [lid]);
  const change = (next: LectureDoc | ((d: LectureDoc) => void)) => {
    if (!docRef.current) return;
    undoStack.current.push(structuredClone(docRef.current));
    if (undoStack.current.length > 70) undoStack.current.shift();
    redoStack.current = [];
    const copy = structuredClone(docRef.current);
    const value = typeof next === "function" ? (next(copy), copy) : next;
    docRef.current = value;
    setDoc(value);
    dirtyRef.current = true;
    setDirty(true);
    storage.setItem(
      "ct-draft-" + lidRef.current,
      JSON.stringify({ revision: revision.current, document: value }),
    );
  };
  const saveNow = useCallback(async (): Promise<boolean> => {
    if (savePromise.current) return savePromise.current;
    if (!dirtyRef.current || !docRef.current || !lidRef.current) return true;
    const target = lidRef.current;
    const work = (async () => {
      setSaving(true);
      try {
        while (dirtyRef.current && target === lidRef.current) {
          const snapshot = JSON.stringify(docRef.current);
          const row = await api<Lecture>("/lectures/" + target, {
            method: "PUT",
            body: JSON.stringify({
              document: JSON.parse(snapshot),
              revision: revision.current,
            }),
          });
          revision.current = row.revision;
          if (snapshot === JSON.stringify(docRef.current)) {
            dirtyRef.current = false;
            setDirty(false);
            storage.removeItem("ct-draft-" + target);
          } else
            storage.setItem(
              "ct-draft-" + target,
              JSON.stringify({
                revision: revision.current,
                document: docRef.current,
              }),
            );
        }
        return true;
      } catch (e) {
        setError((e as Error).message);
        return false;
      } finally {
        setSaving(false);
        savePromise.current = null;
      }
    })();
    savePromise.current = work;
    return work;
  }, []);
  useEffect(() => {
    if (!dirty) return;
    const timer = setTimeout(() => {
      saveNow();
    }, 900);
    return () => clearTimeout(timer);
  }, [doc, dirty, saveNow]);
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (dirtyRef.current) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, []);
  const switchLecture = async (target: string) => {
    if (!(await saveNow())) return;
    setLid(target);
    setTab("sources");
  };
  const changeTheme = async (value: ThemeName) => {
    if (themeSaving || value === themeId) return;
    const target = lidRef.current;
    const previous = themeId;
    setThemeSaving(true);
    setThemeId(value);
    try {
      await api("/lectures/" + target + "/theme", {
        method: "PUT",
        body: JSON.stringify({ theme: value }),
      });
      if (target === lidRef.current) {
        setThemeId(value);
        setRefresh((v) => v + 1);
        notify("حُفظ لون المحاضرة. جهّز تصديرًا جديدًا لتحديث المستند.");
      }
    } catch (e) {
      if (target === lidRef.current) setThemeId(previous);
      setError((e as Error).message);
    } finally {
      setThemeSaving(false);
    }
  };
  const travel = (back: boolean) => {
    if (!docRef.current) return;
    const from = back ? undoStack : redoStack;
    const to = back ? redoStack : undoStack;
    const target = from.current.pop();
    if (!target) return;
    to.current.push(structuredClone(docRef.current));
    docRef.current = target;
    setDoc(target);
    dirtyRef.current = true;
    setDirty(true);
    storage.setItem(
      "ct-draft-" + lidRef.current,
      JSON.stringify({ revision: revision.current, document: target }),
    );
  };
  const currentCourse = courses.find((c) => c.id === cid);
  const selectedCourse =
    currentCourse ||
    courses.find((c) => c.id === lectures.find((l) => l.id === lid)?.course_id);
  const nav = [
    ["courses", "المقررات", BookOpen],
    ["sources", "المصادر", Files],
    ["authoring", "التأليف", PenLine],
    ["editor", "المحرر", Layers],
    ["export", "المعاينة والتصدير", FileOutput],
  ] as const;
  const stats = doc
    ? {
        sections: doc.sections.length,
        blocks: doc.sections.reduce((a, s) => a + s.blocks.length, 0),
        complete: doc.sections.filter((s) => s.complete).length,
      }
    : null;
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setTab("courses");
          }}
        >
          <img src="/ct-logo.png" />
          <div>
            <strong dir="ltr">
              Ctrl+Tea<span>LECTURE STUDIO</span>
            </strong>
            <small>مساحة لصناعة المعرفة</small>
          </div>
        </a>
        <div className="nav-caption">مساحة العمل</div>
        <nav>
          {nav.map(([key, label, Icon], i) => (
            <button
              key={key}
              className={"nav-item " + (tab === key ? "active" : "")}
              disabled={!doc && key !== "courses"}
              onClick={() => setTab(key)}
            >
              <Icon size={19} />
              <span>{label}</span>
              <small>{String(i + 1).padStart(2, "0")}</small>
            </button>
          ))}
        </nav>
        <div className="sidebar-project">
          <span className="eyebrow">المقرر الحالي</span>
          <strong>{selectedCourse?.name || "لم يتم اختيار مقرر"}</strong>
          {doc && (
            <>
              <span>{doc.title}</span>
              <button className="text-button" onClick={() => setTab("courses")}>
                تغيير المحاضرة <ArrowLeft size={14} />
              </button>
            </>
          )}
        </div>
        <div className="sidebar-bottom">
          <span className="online-dot" />
          محلي · محفوظ على جهازك <span className="version">AQ-06</span>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <div className="breadcrumb">
            استوديو المحاضرات <span>/</span>{" "}
            {nav.find((x) => x[0] === tab)?.[1]}
          </div>
          <div className="top-actions">
            {doc && (
              <>
                <span className={"save-status " + (dirty ? "pending" : "")}>
                  <span className="online-dot" />
                  {saving
                    ? "جارٍ الحفظ…"
                    : dirty
                      ? "تعديلات غير محفوظة"
                      : "كل التعديلات محفوظة"}
                </span>
                <button
                  className="icon-button"
                  title="تراجع"
                  disabled={!undoStack.current.length}
                  onClick={() => travel(true)}
                >
                  <Undo2 size={17} />
                </button>
                <button
                  className="icon-button"
                  title="إعادة التعديل"
                  disabled={!redoStack.current.length}
                  onClick={() => travel(false)}
                >
                  <Redo2 size={17} />
                </button>
                <button
                  className="icon-button"
                  title="حفظ الآن"
                  onClick={() => saveNow()}
                >
                  <Save size={18} />
                </button>
                <button
                  className="icon-button"
                  title="سجل النسخ"
                  onClick={() => setModal("history")}
                >
                  <History size={18} />
                </button>
                <button
                  className="icon-button"
                  title="إعدادات المحاضرة"
                  onClick={() => setModal("settings")}
                >
                  <Settings size={18} />
                </button>
              </>
            )}
          </div>
        </header>
        {message && (
          <div role="status" className="toast success">
            <Check size={17} />
            {message}
            <button onClick={() => setMessage("")}>
              <X size={15} />
            </button>
          </div>
        )}
        {error && (
          <div role="alert" className="toast error">
            <AlertCircle size={18} />
            <div>{error}</div>
            <button aria-label="إغلاق الخطأ" onClick={() => setError("")}>
              <X size={16} />
            </button>
          </div>
        )}
        {stashed && (
          <div className="banner">
            توجد تعديلات محلية أقدم من النسخة الحالية.
            <button
              onClick={() => {
                if (
                  confirm(
                    "استبدال المحتوى الحالي بالنسخة المحلية؟ ستبقى النسخة الحالية في سجل النسخ.",
                  )
                ) {
                  change(stashed.document);
                  setStashed(null);
                }
              }}
            >
              استعادة التعديلات المحلية
            </button>
            <button onClick={() => setStashed(null)}>تجاهل</button>
          </div>
        )}
        <div className="content">
          {transferOpen && <Transfers courses={courses} currentCourse={cid} saveNow={saveNow} act={act}
            onClose={()=>setTransferOpen(false)} onDone={async result=>{
              await loadCourses();setCid(result.course_id);setRefresh(value=>value+1);
              if(result.mode==="append_sections" && result.lecture_ids[0]===lidRef.current)await loadLecture(lidRef.current);
              else if(result.lecture_ids?.length)setLid(result.lecture_ids[0]);
              notify(result.mode==="append_sections"?"أضيفت الأقسام ومصادرها، مع الاحتفاظ بالمحتوى السابق.":"أضيفت المحاضرات المحددة بمصادرها وسجلها.");
            }}/>}
          {tab === "courses" ? (
            <>
              <div className="page-heading">
                <div>
                  <span className="eyebrow">مكتبة Ctrl+Tea</span>
                  <h1>من الفكرة إلى ملزمة تستحق القراءة.</h1>
                  <p>مصادرك، ملاحظاتك، ومحاضراتك — في مكان واحد.</p>
                </div>
                <div className="actions">
                  <button className="button secondary" onClick={()=>setTransferOpen(true)}>
                    <Upload size={16}/>استيراد / تصدير البيانات
                  </button>
                  <button
                    className="button primary"
                    onClick={() => {
                      setCourseName("");
                      setDoctor("");
                      setModal("course");
                    }}
                  >
                    <Plus size={17} />
                    مقرر جديد
                  </button>
                </div>
              </div>
              <div className="library-layout">
                <section>
                  <div className="section-label">
                    <h2>المقررات</h2>
                    <span>{courses.length} مقرر</span>
                  </div>
                  <div className="courses-grid">
                    {courses.map((c, i) => (
                      <button
                        key={c.id}
                        className={
                          "course-card " + (cid === c.id ? "selected" : "")
                        }
                        onClick={async () => {
                          if (await saveNow()) setCid(c.id);
                        }}
                        style={
                          {
                            ...themeStyle(design?.themes[i % 3]),
                          } as React.CSSProperties
                        }
                      >
                        <span className="course-symbol">
                          <BookOpen size={22} />
                        </span>
                        <h3>{c.name}</h3>
                        <p>{c.doctor || "بيانات الدكتور غير مضافة"}</p>
                        <footer>
                          <span>{c.lecture_count || 0} محاضرة</span>
                          <ArrowLeft size={17} />
                        </footer>
                      </button>
                    ))}
                  </div>
                  {!courses.length && (
                    <Empty
                      title="ابدأ بمقرر واحد"
                      description="أنشئ المقرر، ثم أضف محاضرتك ومصادرها."
                    />
                  )}
                </section>
                {currentCourse && (
                  <section className="lecture-list panel">
                    <div className="section-label">
                      <h2>{currentCourse.name}</h2>
                      <div className="actions">
                        <button
                          className="icon-button"
                          title="تعديل المقرر"
                          onClick={() => {
                            setCourseName(currentCourse.name);
                            setDoctor(currentCourse.doctor);
                            setModal("edit-course");
                          }}
                        >
                          <PenLine size={16} />
                        </button>
                        <button
                          className="icon-button"
                          title="تصدير بيانات المادة كاملة"
                          onClick={() =>
                            act(async () => {
                              if (await saveNow())
                                await download(
                                  "/courses/" + cid + "/bundle",
                                  "CtrlTea_Project.zip",
                                );
                            })
                          }
                        >
                          <Download size={17} />
                        </button>
                        <button
                          className="icon-button danger"
                          title="حذف المقرر"
                          onClick={() =>
                            act(async () => {
                              if (
                                !confirm(
                                  "حذف المقرر ومحاضراته؟ صدّر نسخة مشروع أولًا إذا احتجتها.",
                                )
                              )
                                return;
                              await api("/courses/" + cid, {
                                method: "DELETE",
                              });
                              setCid("");
                              setLid("");
                              await loadCourses();
                            })
                          }
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </div>
                    <button
                      className="button secondary full"
                      onClick={() => {
                        setLectureTitle("");
                        setNewTheme(design?.default_theme || "cinnamon");
                        setLectureNumber(
                          String(lectures.length + 1).padStart(2, "0"),
                        );
                        setModal("lecture");
                      }}
                    >
                      <Plus size={16} />
                      محاضرة جديدة
                    </button>
                    <div className="search">
                      <Search size={16} />
                      <input
                        placeholder="ابحث في المحاضرات"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                      />
                    </div>
                    {lectures
                      .filter((l) => l.title.includes(query))
                      .map((l) => (
                        <div
                          key={l.id}
                          className={
                            "lecture-row " + (l.id === lid ? "current" : "")
                          }
                        >
                          <button
                            className="lecture-open"
                            onClick={() => switchLecture(l.id)}
                          >
                            <BookOpen size={18} />
                            <div>
                              <strong>{l.title}</strong>
                              <small>
                                {new Date(l.updated).toLocaleDateString("ar")}
                              </small>
                            </div>
                            <ArrowLeft size={16} />
                          </button>
                          <button className="icon-button" title="تصدير بيانات هذه المحاضرة" onClick={()=>act(async()=>{
                            if(await saveNow())await download("/lectures/"+l.id+"/bundle","CtrlTea_Lecture_Data.zip");
                          })}><Download size={15}/></button>
                          <button
                            className="icon-button danger"
                            title="حذف المحاضرة"
                            onClick={() =>
                              act(async () => {
                                if (!confirm("حذف المحاضرة؟")) return;
                                await api("/lectures/" + l.id, {
                                  method: "DELETE",
                                });
                                if (l.id === lid) setLid("");
                                setRefresh((v) => v + 1);
                                await loadCourses();
                              })
                            }
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      ))}
                  </section>
                )}
              </div>
              <div className="workflow-note">
                <Leaf size={20} />
                <div>
                  <strong>المعنى أولًا. التنسيق يتكفّل بالباقي.</strong>
                  <p>
                    ابدأ بمصادر موثوقة، راجع المحتوى، ثم صدّر نسخة جاهزة للطلاب.
                  </p>
                </div>
                <div className="palette-dots">
                  {design?.themes.map((c) => (
                    <i key={c.id} style={{ background: c.dark }} />
                  ))}
                </div>
              </div>
            </>
          ) : !doc ? (
            <Empty
              title="اختر محاضرة للمتابعة"
              description="يمكنك فتح محاضرة أو إنشاء واحدة من قسم المقررات."
            />
          ) : (
            <>
              <div className="page-heading compact">
                <div>
                  <span className="eyebrow">
                    {doc.course}{" "}
                    <span className="muted">/ المحاضرة {doc.number}</span>
                  </span>
                  <h1>{doc.title}</h1>
                  {lectureTheme && (
                    <button
                      className="lecture-theme-badge"
                      style={themeStyle(lectureTheme)}
                      onClick={() => setModal("settings")}
                    >
                      <i />
                      {lectureTheme.label}
                    </button>
                  )}
                </div>
                <div className="lecture-stats">
                  <span>
                    <b>{stats?.sections}</b> أقسام
                  </span>
                  <span>
                    <b>{sources.length}</b> مصادر
                  </span>
                  <span>
                    <b>{stats?.blocks}</b> عنصر
                  </span>
                </div>
              </div>
              {tab === "sources" && (
                <Sources
                  sources={sources}
                  jobs={jobs}
                  lid={lid}
                  refresh={refresh}
                  act={act}
                  reload={reload}
                  notify={notify}
                />
              )}
              {tab === "authoring" && (
                <Authoring
                  doc={doc}
                  lid={lid}
                  saveNow={saveNow}
                  revision={() => revision.current}
                  onImported={async () => {
                    storage.removeItem("ct-draft-" + lid);
                    await loadLecture(lid);
                    notify("استُورد المحتوى وأُضيفت نسخة إلى السجل.");
                    setTab("editor");
                  }}
                  act={act}
                />
              )}
              {tab === "editor" && (
                <Editor
                  key={lid}
                  theme={lectureTheme}
                  doc={doc}
                  sources={sources}
                  lid={lid}
                  change={change}
                  act={act}
                  notify={notify}
                />
              )}
              {tab === "export" && (
                <Exports
                  key={lid}
                  theme={lectureTheme}
                  themeSaving={themeSaving}
                  fonts={design?.fonts}
                  doc={doc}
                  lid={lid}
                  jobs={jobs}
                  exports={exports}
                  revision={revision.current}
                  saveNow={saveNow}
                  reload={reload}
                  act={act}
                />
              )}
            </>
          )}
        </div>
      </main>
      {modal && (
        <div className="modal-backdrop" onMouseDown={() => setModal("")}>
          <div
            className={
              "modal " +
              (["settings", "history", "lecture"].includes(modal) ? "wide" : "")
            }
            onMouseDown={(e) => e.stopPropagation()}
          >
            <button
              className="modal-close icon-button"
              onClick={() => setModal("")}
              aria-label="إغلاق"
            >
              <X size={20} />
            </button>
            {(modal === "course" || modal === "edit-course") && (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  act(async () => {
                    if (modal === "course") {
                      const c = await api<Course>("/courses", {
                        method: "POST",
                        body: JSON.stringify({ name: courseName, doctor }),
                      });
                      setCid(c.id);
                    } else
                      await api("/courses/" + cid, {
                        method: "PUT",
                        body: JSON.stringify({ name: courseName, doctor }),
                      });
                    await loadCourses();
                    setModal("");
                  });
                }}
              >
                <span className="eyebrow">مكتبة المعرفة</span>
                <h2>{modal === "course" ? "مقرر جديد" : "تعديل المقرر"}</h2>
                <Field
                  label="اسم المقرر"
                  value={courseName}
                  onChange={setCourseName}
                />
                <Field
                  label="اسم الدكتور"
                  value={doctor}
                  onChange={setDoctor}
                />
                <button
                  className="button primary full"
                  disabled={!courseName.trim()}
                >
                  حفظ المقرر
                </button>
              </form>
            )}
            {modal === "lecture" && (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  act(async () => {
                    const l = await api<Lecture>(
                      "/courses/" + cid + "/lectures",
                      {
                        method: "POST",
                        body: JSON.stringify({
                          title: lectureTitle,
                          number: lectureNumber,
                          theme: newTheme,
                        }),
                      },
                    );
                    setLid(l.id);
                    setTab("sources");
                    setRefresh((v) => v + 1);
                    await loadCourses();
                    setModal("");
                  });
                }}
              >
                <span className="eyebrow">خطوة جديدة</span>
                <h2>محاضرة جديدة</h2>
                <Field
                  label="عنوان المحاضرة"
                  value={lectureTitle}
                  onChange={setLectureTitle}
                />
                <Field
                  label="رقم المحاضرة"
                  value={lectureNumber}
                  onChange={setLectureNumber}
                />
                {design && (
                  <ThemePicker
                    themes={design.themes}
                    value={newTheme}
                    onChange={setNewTheme}
                  />
                )}
                <button
                  className="button primary full"
                  disabled={!lectureTitle.trim() || !design}
                >
                  إنشاء المحاضرة
                </button>
              </form>
            )}
            {modal === "settings" && doc && (
              <>
                <span className="eyebrow">تفاصيل وهوية المحاضرة</span>
                <h2>إعدادات المحاضرة</h2>
                {design && (
                  <ThemePicker
                    themes={design.themes}
                    value={themeId}
                    onChange={changeTheme}
                    disabled={themeSaving}
                  />
                )}
                <p className="hint" role="status">
                  {themeSaving
                    ? "جارٍ حفظ لون المحاضرة…"
                    : "اللون محفوظ مستقلًا عن المحتوى. يُطبّق على المستند عند إعادة التصدير."}
                </p>
                <div className="form-grid">
                  <Field
                    label="العنوان"
                    value={doc.title}
                    onChange={(s) =>
                      change((d) => {
                        d.title = s;
                      })
                    }
                  />
                  <Field
                    label="المقرر"
                    value={doc.course}
                    onChange={(s) =>
                      change((d) => {
                        d.course = s;
                      })
                    }
                  />
                  <Field
                    label="اسم الدكتور"
                    value={doc.doctor}
                    onChange={(s) =>
                      change((d) => {
                        d.doctor = s;
                      })
                    }
                  />
                  <Field
                    label="رقم المحاضرة"
                    value={doc.number}
                    onChange={(s) =>
                      change((d) => {
                        d.number = s;
                      })
                    }
                  />
                  <label className="field">
                    <span>حجم الخط: {doc.settings.font_size} pt</span>
                    <input
                      type="range"
                      min="11"
                      max="20"
                      step="0.5"
                      value={doc.settings.font_size}
                      onChange={(e) =>
                        change((d) => {
                          d.settings.font_size = +e.target.value;
                        })
                      }
                    />
                  </label>
                  <label className="field">
                    <span>تباعد الأسطر: {doc.settings.line_spacing}</span>
                    <input
                      type="range"
                      min="1"
                      max="2"
                      step="0.05"
                      value={doc.settings.line_spacing}
                      onChange={(e) =>
                        change((d) => {
                          d.settings.line_spacing = +e.target.value;
                        })
                      }
                    />
                  </label>
                  <label className="field">
                    <span>الهوامش بالميليمتر</span>
                    <input
                      type="number"
                      min="12"
                      max="28"
                      value={doc.settings.margin_mm}
                      onChange={(e) =>
                        change((d) => {
                          d.settings.margin_mm = +e.target.value;
                        })
                      }
                    />
                  </label>
                  <label className="field"><span>طريقة تصدير المعادلات</span>
                    <select value={doc.settings.math_mode || "native"} onChange={e=>change(d=>{d.settings.math_mode=e.target.value as "native"|"portable";})}>
                      <option value="portable">عرض ثابت كصور عالية الدقة</option>
                      <option value="native">معادلات Word أصلية قابلة للتحرير</option>
                    </select><small>الصور تبقى قابلة للتعديل بصيغة LaTeX من الداشبورد. لتعديل المعادلات داخل Word اختر المعادلات الأصلية.</small>
                  </label>
                  <label className="checkbox"><input type="checkbox" checked={doc.settings.embed_fonts !== false}
                    onChange={e=>change(d=>{d.settings.embed_fonts=e.target.checked;})}/>تضمين الخطوط داخل ملف Word</label>
                  <label className="checkbox">
                    <input
                      type="checkbox"
                      checked={doc.settings.end_marker}
                      onChange={(e) =>
                        change((d) => {
                          d.settings.end_marker = e.target.checked;
                        })
                      }
                    />
                    إظهار «انتهت المحاضرة»
                  </label>
                </div>
                <p className="hint">
                  ثيم واحد لجميع الأقسام والفوتر والرسومات المنشأة. يحتفظ الغلاف
                  بشريط ألوانه الأصلي.
                </p>
                <button
                  className="button primary"
                  disabled={themeSaving}
                  onClick={async () => {
                    if (await saveNow()) setModal("");
                  }}
                >
                  حفظ الإعدادات
                </button>
              </>
            )}
            {modal === "history" && doc && (
              <HistoryPanel
                lid={lid}
                revision={() => revision.current}
                saveNow={saveNow}
                act={act}
                restored={async () => {
                  await loadLecture(lid);
                  setModal("");
                  notify("تمت استعادة النسخة.");
                }}
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

type Act = (fn: () => Promise<any>) => Promise<any>;
function Sources({
  sources,
  jobs,
  lid,
  refresh,
  act,
  reload,
  notify,
}: {
  sources: Source[];
  jobs: Job[];
  lid: string;
  refresh: number;
  act: Act;
  reload: () => Promise<any>;
  notify: (s: string) => void;
}) {
  const storage = useContext(WorkspaceStorage);
  const [sid, setSid] = useState(""),
    [pages, setPages] = useState<Page[]>([]),
    [number, setNumber] = useState(1),
    [content, setContent] = useState(""),
    [excluded, setExcluded] = useState(false),
    [pending, setPending] = useState(false),
    [role, setRole] = useState("primary"),
    [linked, setLinked] = useState(""),
    [busy, setBusy] = useState(false),
    [showRaw, setShowRaw] = useState(false);
  const area = useRef<HTMLTextAreaElement>(null);
  const source = sources.find((s) => s.id === sid);
  const active = pages.find((p) => p.number === number);
  const fetchPages = async () => {
    if (!sid) return;
    setPages(await api("/sources/" + sid + "/pages"));
  };
  useEffect(() => {
    if (!sid && sources.length) setSid(sources[0].id);
  }, [sources]);
  useEffect(() => {
    setNumber(1);
    setPending(false);
    act(fetchPages);
  }, [sid]);
  useEffect(() => {
    if (!pending) act(fetchPages);
  }, [refresh]);
  useEffect(() => {
    if (active) {
      const saved = storage.getItem("ct-source-" + sid + "-" + number);
      if (saved) {
        try {
          const d = JSON.parse(saved);
          setContent(d.content);
          setExcluded(d.excluded);
          setPending(true);
          return;
        } catch {}
      }
      setContent(active.corrected ?? active.raw);
      setExcluded(!!active.excluded);
      setPending(false);
    }
  }, [active?.raw, active?.corrected, number, sid]);
  const persist = async () => {
    if (!sid || !active) return;
    await api("/sources/" + sid + "/pages/" + number, {
      method: "PUT",
      body: JSON.stringify({ corrected: content, excluded }),
    });
    storage.removeItem("ct-source-" + sid + "-" + number);
    setPending(false);
    await fetchPages();
  };
  useEffect(() => {
    if (!pending || !sid) return;
    storage.setItem(
      "ct-source-" + sid + "-" + number,
      JSON.stringify({ content, excluded }),
    );
    const timer = setTimeout(() => {
      act(persist);
    }, 1200);
    return () => clearTimeout(timer);
  }, [content, excluded, pending, sid, number]);
  const move = async (newSid: string, newPage = 1) => {
    if (pending) await persist();
    setSid(newSid);
    setNumber(newPage);
  };
  return (
    <>
      <div className="step-intro">
        <div>
          <h2>المصادر التي نبني عليها</h2>
          <p>
            حدّد المصدر الأساسي، وصحّح التفريغ مع الرجوع إلى الصفحة الأصلية.
          </p>
        </div>
        <span className="pill">
          <Files size={14} />
          {sources.length} مصادر
        </span>
      </div>
      <div className="source-layout">
        <aside className="panel source-list">
          <FileDrop accept=".pdf,.txt,.md,.docx" multiple disabled={busy}
            title={busy?"جارٍ رفع المصادر…":"أسقط مصادر المحاضرة هنا"}
            hint="PDF · TXT · Markdown · DOCX — حتى 120 MB لكل ملف، أو انقر للاختيار"
            onFiles={files=>act(async()=>{
              setBusy(true);
              try {
                for(const file of files){
                  const data=new FormData();data.append("file",file);data.append("role",role);
                  data.append("priority",role==="primary"?"0":"1");data.append("linked_id",linked);
                  const result=await api("/lectures/"+lid+"/sources",{method:"POST",body:data});setSid(result.source.id);
                }
                notify("رُفعت المصادر. يبدأ الاستخراج تلقائيًا.");
              }finally{try{await reload();}finally{setBusy(false);}}
            })}/>

          <label className="field">
            <span>نوع الملف المرفوع</span>
            <select value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="primary">مصدر أساسي</option>
              <option value="transcript">تفريغ خارجي</option>
              <option value="support">كتاب داعم</option>
              <option value="previous">محاضرة سابقة</option>
            </select>
          </label>
          <label className="field">
            <span>ربط التفريغ بالأصل</span>
            <select value={linked} onChange={(e) => setLinked(e.target.value)}>
              <option value="">بدون ربط</option>
              {sources
                .filter((s) => s.kind === "pdf")
                .map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
            </select>
          </label>
          <div className="source-items">
            {sources.map((s) => (
              <button
                key={s.id}
                className={"source-item " + (sid === s.id ? "active" : "")}
                onClick={() => act(() => move(s.id))}
              >
                <span className="file-type">{s.kind.toUpperCase()}</span>
                <div>
                  <strong>{s.name}</strong>
                  <small>
                    {s.page_count} صفحة ·{" "}
                    {s.role === "primary"
                      ? "أساسي"
                      : s.role === "transcript"
                        ? "تفريغ"
                        : "داعم"}
                  </small>
                </div>
              </button>
            ))}
          </div>
        </aside>
        {!source ? (
          <Empty
            title="أضف أول مصدر"
            description="ارفع التفريغ الأساسي، ثم الكتب أو المحاضرات الداعمة."
          />
        ) : (
          <section className="panel source-workbench">
            <div className="source-toolbar">
              <div>
                <h3>{source.name}</h3>
                <div className="actions">
                  <label className="small-label">
                    الأولوية{" "}
                    <input
                      aria-label="أولوية المصدر"
                      type="number"
                      min="0"
                      max="999"
                      value={source.priority}
                      onChange={(e) =>
                        act(async () => {
                          await api("/sources/" + sid, {
                            method: "PUT",
                            body: JSON.stringify({
                              priority: +e.target.value,
                              role: source.role,
                              linked_id: source.linked_id,
                            }),
                          });
                          await reload();
                        })
                      }
                    />
                  </label>
                  <select
                    aria-label="دور المصدر"
                    value={source.role}
                    onChange={(e) =>
                      act(async () => {
                        await api("/sources/" + sid, {
                          method: "PUT",
                          body: JSON.stringify({
                            priority: source.priority,
                            role: e.target.value,
                            linked_id: source.linked_id,
                          }),
                        });
                        await reload();
                      })
                    }
                  >
                    <option value="primary">أساسي</option>
                    <option value="support">داعم</option>
                    <option value="transcript">تفريغ</option>
                    <option value="previous">محاضرة سابقة</option>
                  </select>
                </div>
              </div>
              <div className="actions">
                <a
                  className="icon-button"
                  href={apiURL("/api/sources/" + sid + "/file")}
                  target="_blank"
                  title="فتح الأصل"
                >
                  <ExternalLink size={17} />
                </a>
                <button
                  title="استكمال الاستخراج"
                  className="icon-button"
                  onClick={() =>
                    act(async () => {
                      await api("/sources/" + sid + "/extract", {
                        method: "POST",
                      });
                      await reload();
                    })
                  }
                >
                  <RefreshCw size={17} />
                </button>
                <button
                  title="حذف المصدر"
                  className="icon-button danger"
                  onClick={() =>
                    act(async () => {
                      if (!confirm("حذف المصدر؟")) return;
                      await api("/sources/" + sid, { method: "DELETE" });
                      setSid("");
                      setPages([]);
                      await reload();
                    })
                  }
                >
                  <Trash2 size={17} />
                </button>
              </div>
            </div>
            {source.kind !== "pdf" && (
              <label className="field source-link">
                <span>ملف PDF الأصلي المرتبط</span>
                <select
                  value={source.linked_id || ""}
                  onChange={(e) =>
                    act(async () => {
                      await api("/sources/" + sid, {
                        method: "PUT",
                        body: JSON.stringify({
                          priority: source.priority,
                          role: source.role,
                          linked_id: e.target.value || null,
                        }),
                      });
                      await reload();
                    })
                  }
                >
                  <option value="">بدون ربط</option>
                  {sources
                    .filter((s) => s.kind === "pdf")
                    .map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name}
                      </option>
                    ))}
                </select>
              </label>
            )}
            <div className="page-controls">
              {source.kind !== "pdf" && (
                <button
                  className="text-button"
                  onClick={() =>
                    act(async () => {
                      const n = prompt("رقم الصفحة المطابقة في PDF الأصلي");
                      if (!n) return;
                      if (pending) await persist();
                      await api("/sources/" + sid + "/pages", {
                        method: "POST",
                        body: JSON.stringify({ number: +n, corrected: "" }),
                      });
                      await fetchPages();
                      setNumber(+n);
                      await reload();
                    })
                  }
                >
                  <Plus size={13} />
                  ربط صفحة تفريغ
                </button>
              )}
              <label>
                الصفحة{" "}
                <select
                  aria-label="صفحة المصدر"
                  value={number}
                  onChange={(e) => act(() => move(sid, +e.target.value))}
                >
                  {pages.map((p) => (
                    <option key={p.number} value={p.number}>
                      {p.number}
                      {p.corrected !== null ? " · مصححة" : ""}
                      {p.excluded ? " · مستبعدة" : ""}
                    </option>
                  ))}
                </select>
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={excluded}
                  onChange={(e) => {
                    setExcluded(e.target.checked);
                    setPending(true);
                  }}
                />
                استبعاد هذه الصفحة من التأليف
              </label>
              <span className="muted">
                {active?.corrected !== null
                  ? "نص مصحح"
                  : active?.method === "tesseract"
                    ? "OCR يحتاج مراجعة"
                    : "نص مستخرج يحتاج مراجعة"}
              </span>
            </div>
            <div
              className={
                "source-compare " +
                (source.kind === "pdf" || source.linked_id ? "" : "text-only")
              }
            >
              {(source.kind === "pdf" || source.linked_id) && (
                <div className="original-page">
                  <span className="eyebrow">الأصل للمطابقة</span>
                  {source.kind === "pdf" ? (
                    <img
                      src={apiURL(
                        "/api/sources/" + sid + "/pages/" + number + "/image"
                      )}
                      alt={"الصفحة الأصلية " + number}
                    />
                  ) : (
                    <iframe
                      title="المصدر الأصلي المرتبط"
                      src={apiURL(
                        "/api/sources/" +
                        source.linked_id +
                        "/file#page=" +
                        number
                      )}
                    />
                  )}
                </div>
              )}
              <div className="transcript">
                <div className="section-label">
                  <strong>النص المعتمد للتأليف</strong>
                  <span className="hint">
                    {pending ? "تعديلات غير محفوظة" : "محفوظ"}
                  </span>
                  <button
                    className="text-button"
                    onClick={() => setShowRaw(!showRaw)}
                  >
                    {showRaw ? "إخفاء الاستخراج" : "عرض الاستخراج الأصلي"}
                  </button>
                </div>
                {showRaw && (
                  <pre className="raw-text">
                    {active?.raw || "لم يكتمل الاستخراج بعد."}
                  </pre>
                )}
                <textarea
                  ref={area}
                  aria-label="النص المصحح"
                  value={content}
                  onChange={(e) => {
                    setContent(e.target.value);
                    setPending(true);
                  }}
                  placeholder="صحّح النص هنا، أو الصق التفريغ الخارجي…"
                />
                <div className="actions">
                  <button
                    className="button primary"
                    disabled={!pending}
                    onClick={() => act(persist)}
                  >
                    <Save size={16} />
                    حفظ التصحيح
                  </button>
                  <button
                    className="button secondary"
                    onClick={() => {
                      const a = area.current;
                      if (!a || a.selectionStart === a.selectionEnd) return;
                      setContent(
                        content.slice(0, a.selectionStart) +
                          content.slice(a.selectionEnd),
                      );
                      setPending(true);
                    }}
                  >
                    استبعاد النص المحدد
                  </button>
                </div>
                <p className="hint">
                  يمكن استبعاد الكلام غير التعليمي من النص المصحح؛ يظل الأصل
                  محفوظًا للمقارنة.
                </p>
              </div>
            </div>
          </section>
        )}
      </div>
      <JobList jobs={jobs.filter((j) => j.kind === "extract")} act={act} />
    </>
  );
}
function JobList({ jobs, act }: { jobs: Job[]; act: Act }) {
  const items = jobs.filter((j) => j.status !== "done");
  if (!items.length) return null;
  return (
    <div className="job-list">
      {items.map((j) => {
        const error = j.error ? JSON.parse(j.error) : null;
        return (
          <div key={j.id} className={"job panel " + j.status}>
            <div className="actions">
              {j.status === "failed" ? (
                <AlertCircle size={18} />
              ) : (
                <Clock size={18} />
              )}
              <strong>
                {j.kind === "extract" ? "استخراج المصدر" : "تجهيز Word وPDF"}
              </strong>
              <span>
                {j.status === "failed"
                  ? "تعذرت المهمة"
                  : j.status === "queued"
                    ? "بانتظار التنفيذ"
                    : `${j.progress}%`}
              </span>
            </div>
            {j.status === "running" && (
              <progress max="100" value={j.progress} />
            )}
            {error && (
              <>
                <p>{error.message}</p>
                <div className="actions">
                  <button
                    className="button secondary small"
                    onClick={() =>
                      act(() =>
                        api("/jobs/" + j.id + "/retry", { method: "POST" }),
                      )
                    }
                  >
                    إعادة المحاولة
                  </button>
                  <details>
                    <summary>التشخيص</summary>
                    <pre dir="ltr">{error.diagnostic}</pre>
                  </details>
                </div>
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}
function Authoring({
  doc,
  lid,
  saveNow,
  revision,
  onImported,
  act,
}: {
  doc: LectureDoc;
  lid: string;
  saveNow: () => Promise<boolean>;
  revision: () => number;
  onImported: () => Promise<any>;
  act: Act;
}) {
  const [result, setResult] = useState<any>(null),
    [preview, setPreview] = useState<any>(null),
    [runs, setRuns] = useState<any[]>([]),
    [selected, setSelected] = useState<string[]>([]),
    [busy, setBusy] = useState(false),
    [overwrite, setOverwrite] = useState(false),
    [validationErrors, setValidationErrors] = useState<ValidationIssue[]>([]);
  useEffect(() => {
    act(async () => setRuns(await api("/lectures/" + lid + "/authoring/runs")));
  }, [lid]);
  const inspect = async (payload: any) => {
    setPreview(null);
    setResult(null);
    setValidationErrors([]);
    if (!(await saveNow())) return;
    try {
      const p = await api("/lectures/" + lid + "/authoring/preview", {
        method: "POST",
        body: JSON.stringify({ result: payload }),
      });
      setResult(payload);
      setPreview(p);
      setOverwrite(false);
    } catch (error) {
      if (error instanceof ApiError && error.errors.length)
        setValidationErrors(error.errors);
      else throw error;
    }
  };
  return (
    <>
      <div className="step-intro">
        <div>
          <h2>تأليف أكاديمي، بخطوات قابلة للاستكمال</h2>
          <p>
            جهّز الحزمة، شغّل مؤلفك الخارجي، ثم راجع النتيجة قبل إدخالها
            للمحاضرة.
          </p>
        </div>
      </div>
      <div className="author-grid">
        <section className="panel author-card">
          <span className="step-number">01</span>
          <h2>جهّز حزمة التأليف</h2>
          <p>
            تحتوي المصادر الأصلية والنصوص المعتمدة والأولويات وSchema وتعليمات
            واحدة موجزة.
          </p>
          {doc.sections.length > 0 && (
            <div className="task-sections">
              {doc.sections.map((s) => (
                <label key={s.id} className="checkbox">
                  <input
                    type="checkbox"
                    checked={selected.includes(s.id)}
                    onChange={(e) =>
                      setSelected((x) =>
                        e.target.checked
                          ? [...x, s.id]
                          : x.filter((v) => v !== s.id),
                      )
                    }
                  />
                  {s.title}
                  <span className={"pill " + (s.complete ? "green" : "")}>
                    {s.complete ? "مكتمل" : "بانتظار التأليف"}
                  </span>
                </label>
              ))}
            </div>
          )}
          <button
            className="button primary"
            disabled={busy}
            onClick={() =>
              act(async () => {
                if (!(await saveNow())) return;
                setBusy(true);
                try {
                  await download(
                    "/lectures/" + lid + "/authoring/packet",
                    "CtrlTea_Authoring.zip",
                    selected.length ? { section_ids: selected } : {},
                  );
                  setRuns(await api("/lectures/" + lid + "/authoring/runs"));
                } finally {
                  setBusy(false);
                }
              })
            }
          >
            <Download size={17} />
            {busy ? "جارٍ التجهيز…" : "تنزيل حزمة التأليف"}
          </button>
          <p className="hint">
            دون تحديد: تُجهّز الأقسام غير المكتملة فقط. يمكنك استيراد كل قسم عند
            انتهائه.
          </p>
        </section>
        <section className="panel author-card">
          <span className="step-number">02</span>
          <h2>شغّل المؤلف الذي تختاره</h2>
          <p>
            افتح الحزمة في OpenCode أو نموذج آخر، واطلب اتباع instructions.txt
            وmanifest.json وإخراج النتيجة وفق schema.json.
          </p>
          <div className="instruction">
            أنجز مهمة واحدة في كل مرة. احتفظ بمعرّفات الأقسام ومراجع المصادر.
            افحص النتيجة بواسطة validate_result.py قبل تسليم ملف JSON.
          </div>
          <a
            href={apiURL("/api/authoring/schema")}
            target="_blank"
            className="text-button"
          >
            عرض Schema التأليف <ExternalLink size={14} />
          </a>
        </section>
        <section className="panel author-card">
          <span className="step-number">03</span>
          <h2>استورد وراجع</h2>
          <p>افحص النتيجة، ومراجعها، وأثر استبدالها على التعديلات الحالية.</p>
          <FileDrop accept=".json" title="أسقط ملف نتيجة التأليف هنا" hint="result.json — أو انقر لاختياره"
            onFiles={files=>act(async()=>{
              let payload;
              try {payload=JSON.parse(await files[0].text());}
              catch {setPreview(null);setResult(null);setValidationErrors([{location:"الملف",message:"تعذر قراءة JSON. تحقق من الأقواس والفواصل وإزالة Markdown من الملف."}]);return;}
              await inspect(payload);
            })}/>

        </section>
      </div>
      {validationErrors.length > 0 && (
        <section
          className="panel validation-errors"
          role="alert"
          aria-label="أخطاء نتيجة التأليف"
        >
          <h3>صحّح نتيجة التأليف قبل الاستيراد</h3>
          <p>
            لم يُغيَّر محتوى المحاضرة. أعد هذه الملاحظات إلى المؤلف ثم افحص
            الملف مجددًا.
          </p>
          <ul>
            {validationErrors.map((e, i) => (
              <li key={i}>
                <strong>{e.location}</strong>
                <span>{e.message}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {preview && (
        <section className="panel import-preview">
          <div className="section-label">
            <h2>مراجعة الاستيراد</h2>
            <span className="pill">{preview.section_count} أقسام</span>
          </div>
          {preview.conflicts.length > 0 && (
            <div className="banner warning">
              <AlertCircle size={18} />
              <div>
                النتيجة ستستبدل محتوى موجودًا أو عُدّل بعد تجهيز الحزمة.
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={overwrite}
                    onChange={(e) => setOverwrite(e.target.checked)}
                  />
                  راجعت التغييرات وأوافق على الاستبدال مع الاحتفاظ بالنسخة
                  السابقة.
                </label>
              </div>
            </div>
          )}
          <div className="compare-docs">
            <div>
              <h3>الحالي</h3>
              {doc.sections.map((s) => (
                <div key={s.id}>
                  <strong>{s.title}</strong>
                  <p>
                    {s.blocks.length} عناصر ·{" "}
                    {s.blocks.find((b) => b.text)?.text.slice(0, 180)}
                  </p>
                </div>
              ))}
            </div>
            <div>
              <h3>بعد الاستيراد</h3>
              {preview.document.sections.map((s: Section) => (
                <div key={s.id}>
                  <strong>{s.title}</strong>
                  <p>
                    {s.blocks.length} عناصر ·{" "}
                    {s.blocks.find((b) => b.text)?.text.slice(0, 180)}
                  </p>
                </div>
              ))}
            </div>
          </div>
          {preview.checks.issues.length > 0 && (
            <details open>
              <summary>{preview.checks.issues.length} ملاحظات للمراجعة</summary>
              <ul>
                {preview.checks.issues.map((x: any, i: number) => (
                  <li key={i}>{x.message}</li>
                ))}
              </ul>
            </details>
          )}
          <div className="actions">
            <button
              className="button primary"
              disabled={preview.conflicts.length > 0 && !overwrite}
              onClick={() =>
                act(async () => {
                  if (!(await saveNow())) return;
                  await api("/lectures/" + lid + "/authoring/import", {
                    method: "POST",
                    body: JSON.stringify({
                      result,
                      revision: revision(),
                      allow_conflicts: overwrite,
                    }),
                  });
                  await onImported();
                })
              }
            >
              <Check size={17} />
              اعتماد الاستيراد في المحرر
            </button>
            <button
              className="button secondary"
              onClick={() => setPreview(null)}
            >
              إلغاء
            </button>
          </div>
        </section>
      )}
      {runs.length > 0 && (
        <section className="panel run-history">
          <h3>سجل التأليف</h3>
          {runs.map((r) => (
            <div className="run-row" key={r.id}>
              <span>{new Date(r.created).toLocaleString("ar")}</span>
              <span>
                {r.tasks.filter((t: any) => t.status === "imported").length} /{" "}
                {r.tasks.length} مهام مستوردة
              </span>
              <span className="pill">
                {r.status === "complete"
                  ? "مكتمل"
                  : r.status === "partial"
                    ? "مستكمل جزئيًا"
                    : "بانتظار النتيجة"}
              </span>
            </div>
          ))}
        </section>
      )}
    </>
  );
}
function HistoryPanel({
  lid,
  revision,
  saveNow,
  act,
  restored,
}: {
  lid: string;
  revision: () => number;
  saveNow: () => Promise<boolean>;
  act: Act;
  restored: () => Promise<any>;
}) {
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => {
    act(async () => setRows(await api("/lectures/" + lid + "/revisions")));
  }, [lid]);
  return (
    <>
      <h2>نسخ محفوظة، يمكنك الرجوع إليها</h2>
      <p className="muted">استعادة نسخة تحفظ الحالة الحالية في السجل أولًا.</p>
      {rows.map((r) => (
        <div className="revision-row" key={r.id}>
          <div>
            <strong>{r.reason}</strong>
            <small>{new Date(r.created).toLocaleString("ar")}</small>
          </div>
          <button
            className="button secondary small"
            onClick={() =>
              act(async () => {
                if (!confirm("استعادة هذه النسخة؟") || !(await saveNow()))
                  return;
                await api(
                  "/lectures/" + lid + "/revisions/" + r.id + "/restore",
                  {
                    method: "POST",
                    body: JSON.stringify({ revision: revision() }),
                  },
                );
                await restored();
              })
            }
          >
            استعادة
          </button>
        </div>
      ))}
      {!rows.length && <p>سيظهر سجل النسخ بعد أول تعديل محفوظ.</p>}
    </>
  );
}

function LayoutControls({ value = {}, onChange }: {
  value?: LayoutOptions; onChange: (value: LayoutOptions) => void;
}) {
  return <details className="layout-controls">
    <summary>اتجاه العنصر وتوزيعه على الصفحات</summary>
    <div className="layout-options">
      <label className="checkbox"><input type="checkbox" checked={!!value.page_before}
        onChange={e => onChange({...value, page_before:e.target.checked})}/>بدء صفحة جديدة قبله</label>
      <label className="checkbox"><input type="checkbox" checked={!!value.keep_with_next}
        onChange={e => onChange({...value, keep_with_next:e.target.checked})}/>إبقاؤه مع العنصر التالي</label>
      <label className="field"><span>تقسيم العنصر</span><select value={value.keep_together || "auto"}
        onChange={e => onChange({...value, keep_together:e.target.value as LayoutOptions["keep_together"]})}>
        <option value="auto">تلقائي بحسب الحجم</option><option value="keep">إبقاؤه كاملًا إذا اتسع بصفحة</option>
        <option value="split">السماح بامتداده إلى الصفحة التالية</option></select></label>
      <label className="field"><span>اتجاه النص</span><select value={value.direction || "auto"}
        onChange={e => onChange({...value, direction:e.target.value as LayoutOptions["direction"]})}>
        <option value="auto">تلقائي</option><option value="rtl">عربي RTL</option><option value="ltr">إنجليزي LTR</option>
      </select></label>
    </div>
    <p className="hint">تظهر النتيجة النهائية بعد إعادة تجهيز PDF. العنصر الأطول من صفحة يحتاج إلى التقسيم.</p>
  </details>;
}

function WordImport({lid, act, onImport}: {lid:string; act:Act; onImport:(sections:Section[])=>void}) {
  const [pending,setPending] = useState<{sections:Section[]; warnings:string[]}|null>(null);
  const [loading,setLoading] = useState(false);
  return <div className="word-import">
    <FileDrop accept=".docx" disabled={loading} title={loading?"جارٍ قراءة Word…":"أسقط ملف Word لتحرير محتواه"}
      hint="DOCX — أو انقر لاختيار الملف" onFiles={files=>act(async()=>{
        setLoading(true);try{const data=new FormData();data.append("file",files[0]);
          setPending(await api("/lectures/"+lid+"/word/preview",{method:"POST",body:data}));
        }finally{setLoading(false);}
      })}/>

    {pending && <div className="panel import-preview">
      <h3>مراجعة محتوى Word قبل الإضافة</h3>
      <p>ستضاف {pending.sections.length} أقسام، تضم {pending.sections.reduce((n,s)=>n+s.blocks.length,0)} عناصر. يحتفظ التطبيق بالملف الأصلي ضمن المصادر، وتطبّق العناصر تصميم المحاضرة.</p>
      <p className="hint">استيراد النصوص والقوائم والجداول ومعادلات Word الأصلية. الصور والتخطيطات الخاصة تحتاج مراجعة؛ لا يعيد الاستيراد تصميم Word حرفيًا.</p>
      {pending.warnings.map((warning,i)=><p className="inline-error" key={i}>{warning}</p>)}
      <details><summary>المحتوى المستورد</summary>{pending.sections.map(section=><div key={section.id}><strong>{section.title}</strong>
        {section.blocks.map(block=><p key={block.id}>{labels[block.kind]}: {(block.text||block.latex||block.items?.join(" · ")||block.headers.join(" · ")).slice(0,260)}</p>)}</div>)}</details>
      <div className="actions"><button className="button primary small" onClick={()=>{onImport(pending.sections);setPending(null);}}>إضافة إلى المحاضرة</button>
      <button className="button secondary small" onClick={()=>setPending(null)}>إغلاق المعاينة</button></div>
    </div>}
  </div>;
}

function Editor({
  doc,
  theme,
  sources,
  lid,
  change,
  act,
  notify,
}: {
  doc: LectureDoc;
  theme?: LectureTheme;
  sources: Source[];
  lid: string;
  change: (x: LectureDoc | ((d: LectureDoc) => void)) => void;
  act: Act;
  notify: (s: string) => void;
}) {
  const [selected, setSelected] = useState(doc.sections[0]?.id || ""),
    [sourceOpen, setSourceOpen] = useState(false),
    [sourceId, setSourceId] = useState(sources[0]?.id || ""),
    [sourcePage, setSourcePage] = useState(1),
    [preview, setPreview] = useState(false),
    [kind, setKind] = useState("explanation");
  useEffect(() => {
    if (!doc.sections.some((s) => s.id === selected))
      setSelected(doc.sections[0]?.id || "");
  }, [doc.sections, selected]);
  const section = doc.sections.find((s) => s.id === selected);
  const patch = (fn: (s: Section) => void) =>
    change((d) => {
      const s = d.sections.find((s) => s.id === selected);
      if (s) fn(s);
    });
  const addSection = () => {
    const sid = id();
    change((d) => {
      d.sections.push({
        id: sid,
        title: "قسم جديد",
        palette: "cinnamon", // legacy scientific schema field; rendering uses lecture metadata
        complete: false,
        blocks: [],
      });
    });
    setSelected(sid);
  };
  return (
    <>
      <WordImport lid={lid} act={act} onImport={sections=>{
        change(d=>{d.sections.push(...sections);});setSelected(sections[0]?.id||selected);
        notify("أضيف محتوى Word؛ راجع العناصر قبل اعتبار الأقسام مكتملة.");
      }}/>
      <div className="editor-toolbar">
        <div className="segmented">
          <button
            className={!preview ? "active" : ""}
            onClick={() => setPreview(false)}
          >
            <PenLine size={16} />
            تحرير المحتوى
          </button>
          <button
            className={preview ? "active" : ""}
            onClick={() => setPreview(true)}
          >
            <Eye size={16} />
            قراءة سريعة
          </button>
        </div>
        <div className="actions">
          <span className="hint">توزيع الصفحات النهائي في معاينة PDF</span>
          <button
            className="button secondary small"
            onClick={() => setSourceOpen(!sourceOpen)}
          >
            <PanelLeftClose size={16} />
            {sourceOpen ? "إخفاء المصدر" : "عرض المصدر"}
          </button>
        </div>
      </div>
      <div
        className={
          "editor-layout " +
          (sourceOpen ? "with-source " : "") +
          (preview ? "reading-mode" : "")
        }
        style={themeStyle(theme)}
      >
        <aside className="outline panel">
          <div className="section-label">
            <h3>محتوى المحاضرة</h3>
            <button
              title="إضافة قسم"
              className="icon-button"
              onClick={addSection}
            >
              <Plus size={18} />
            </button>
          </div>
          {doc.sections.map((s, i) => (
            <button
              key={s.id}
              className={"outline-item " + (s.id === selected ? "active" : "")}
              onClick={() => setSelected(s.id)}
            >
              <span style={{ color: theme?.dark }}>
                {String(i + 1).padStart(2, "0")}
              </span>
              <div>
                {s.title}
                <small>{s.blocks.length} عناصر</small>
              </div>
              {s.complete && <Check size={14} />}
            </button>
          ))}
          <button className="text-button" onClick={addSection}>
            <Plus size={15} />
            إضافة قسم
          </button>
        </aside>
        <section className="editor-canvas">
          {!section ? (
            <Empty
              title="ابدأ بتقسيم المحاضرة"
              description="أضف قسمًا أو استورد نتيجة المؤلف الخارجي."
            >
              <button className="button primary" onClick={addSection}>
                <Plus size={16} />
                قسم جديد
              </button>
            </Empty>
          ) : (
            <>
              <div className="section-editor-heading" style={themeStyle(theme)}>
                <input
                  aria-label="عنوان القسم"
                  value={section.title}
                  onChange={(e) =>
                    patch((s) => {
                      s.title = e.target.value;
                    })
                  }
                />
                <div className="section-controls">
                  <span className="small-label">
                    لون المحاضرة: {theme?.label}
                  </span>
                  <label className="checkbox">
                    <input
                      type="checkbox"
                      checked={section.complete}
                      onChange={(e) =>
                        patch((s) => {
                          s.complete = e.target.checked;
                        })
                      }
                    />
                    اكتمل المحتوى
                  </label>
                  <label className="checkbox"><input type="checkbox"
                    checked={!!doc.settings.layout?.[section.id]?.page_before}
                    onChange={e=>change(d=>{d.settings.layout ||= {};d.settings.layout[section.id]={...d.settings.layout[section.id],page_before:e.target.checked};})}/>
                    بدء القسم بصفحة جديدة</label>
                  <div className="actions">
                    <button
                      title="تقديم القسم"
                      className="icon-button"
                      disabled={doc.sections[0].id === selected}
                      onClick={() =>
                        change((d) => {
                          const i = d.sections.findIndex(
                            (s) => s.id === selected,
                          );
                          [d.sections[i - 1], d.sections[i]] = [
                            d.sections[i],
                            d.sections[i - 1],
                          ];
                        })
                      }
                    >
                      <ChevronUp size={16} />
                    </button>
                    <button
                      title="تأخير القسم"
                      className="icon-button"
                      disabled={doc.sections.at(-1)?.id === selected}
                      onClick={() =>
                        change((d) => {
                          const i = d.sections.findIndex(
                            (s) => s.id === selected,
                          );
                          [d.sections[i + 1], d.sections[i]] = [
                            d.sections[i],
                            d.sections[i + 1],
                          ];
                        })
                      }
                    >
                      <ChevronDown size={16} />
                    </button>
                    <button
                      title="حذف القسم"
                      className="icon-button danger"
                      onClick={() => {
                        if (confirm("حذف القسم وعناصره؟"))
                          change((d) => {
                            d.sections = d.sections.filter(
                              (s) => s.id !== selected,
                            );
                          });
                      }}
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
              </div>
              <div className="blocks">
                {section.blocks.map((b, i) => (
                  <div
                    key={b.id}
                    className={"block " + b.kind}
                    style={themeStyle(theme)}
                  >
                    <div className="block-toolbar">
                      <span className="block-type">{labels[b.kind]}</span>
                      <span className="block-order">
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <div className="actions">
                        <button
                          title="تحريك العنصر للأعلى"
                          className="icon-button"
                          disabled={i === 0}
                          onClick={() =>
                            patch((s) => {
                              [s.blocks[i - 1], s.blocks[i]] = [
                                s.blocks[i],
                                s.blocks[i - 1],
                              ];
                            })
                          }
                        >
                          <ChevronUp size={15} />
                        </button>
                        <button
                          title="تحريك العنصر للأسفل"
                          className="icon-button"
                          disabled={i === section.blocks.length - 1}
                          onClick={() =>
                            patch((s) => {
                              [s.blocks[i + 1], s.blocks[i]] = [
                                s.blocks[i],
                                s.blocks[i + 1],
                              ];
                            })
                          }
                        >
                          <ChevronDown size={15} />
                        </button>
                        <button title="نسخ العنصر" className="text-button" onClick={()=>patch(s=>{
                          const duplicate=structuredClone(b);duplicate.id=id();s.blocks.splice(i+1,0,duplicate);
                        })}>نسخ</button>
                        <select aria-label="نقل العنصر إلى قسم" value="" onChange={e=>{
                          const target=e.target.value;if(!target)return;
                          change(d=>{const from=d.sections.find(s=>s.id===selected);const to=d.sections.find(s=>s.id===target);
                            if(from&&to){const [block]=from.blocks.splice(i,1);to.blocks.push(block);}});
                        }}><option value="">نقل إلى قسم…</option>{doc.sections.filter(s=>s.id!==selected).map(s=><option key={s.id} value={s.id}>{s.title}</option>)}</select>
                        <button
                          title="حذف العنصر"
                          className="icon-button danger"
                          onClick={() => {
                            if (confirm("حذف هذا العنصر؟"))
                              patch((s) => {
                                s.blocks.splice(i, 1);
                              });
                          }}
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                    </div>
                    {!preview && <LayoutControls value={doc.settings.layout?.[b.id]} onChange={value=>change(d=>{
                      d.settings.layout ||= {};d.settings.layout[b.id]=value;
                    })}/>}
                    {preview ? (
                      <BlockReader
                        b={b}
                        lid={lid}
                        theme={theme?.id || "cinnamon"}
                      />
                    ) : (
                      <BlockEditor
                        b={b}
                        sources={sources}
                        palette={theme?.id || "cinnamon"}
                        onChange={(next) =>
                          patch((s) => {
                            s.blocks[i] = next;
                          })
                        }
                        act={act}
                        notify={notify}
                      />
                    )}
                  </div>
                ))}
              </div>
              {!preview && (
                <div className="add-block">
                  <select
                    aria-label="نوع العنصر الجديد"
                    value={kind}
                    onChange={(e) => setKind(e.target.value)}
                  >
                    {Object.entries(labels).map(([k, v]) => (
                      <option key={k} value={k}>
                        {v}
                      </option>
                    ))}
                  </select>
                  <button
                    className="button secondary"
                    disabled={kind === "figure" && !sources.length}
                    onClick={() =>
                      patch((s) => {
                        s.blocks.push(newBlock(kind, sources[0]));
                      })
                    }
                  >
                    <Plus size={17} />
                    إضافة عنصر
                  </button>
                </div>
              )}
            </>
          )}
        </section>
        {sourceOpen && (
          <aside className="editor-source panel">
            <div className="section-label">
              <h3>مرجعك بجانبك</h3>
              <button
                title="إخفاء المصدر"
                className="icon-button"
                onClick={() => setSourceOpen(false)}
              >
                <X size={17} />
              </button>
            </div>
            <select
              aria-label="مصدر المقارنة"
              value={sourceId}
              onChange={(e) => {
                setSourceId(e.target.value);
                setSourcePage(1);
              }}
            >
              <option value="">اختر مصدرًا</option>
              {sources.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
            <label className="small-label">
              الصفحة{" "}
              <input
                type="number"
                min="1"
                value={sourcePage}
                onChange={(e) => setSourcePage(+e.target.value)}
              />
            </label>
            {sourceId && (
              <SourcePeek
                source={sources.find((s) => s.id === sourceId)!}
                number={sourcePage}
                act={act}
              />
            )}
          </aside>
        )}
      </div>
    </>
  );
}
function SourcePeek({
  source,
  number,
  act,
}: {
  source: Source;
  number: number;
  act: Act;
}) {
  const [txt, setTxt] = useState("");
  useEffect(() => {
    if (source)
      act(async () => {
        const rows = await api<Page[]>("/sources/" + source.id + "/pages");
        const p = rows.find((p) => p.number === number);
        setTxt(p ? (p.corrected ?? p.raw) : "الصفحة غير موجودة");
      });
  }, [source?.id, number]);
  return (
    <>
      {source?.kind === "pdf" && (
        <img
          className="source-peek-image"
          src={apiURL("/api/sources/" + source.id + "/pages/" + number + "/image")}
          alt="صفحة المصدر"
        />
      )}
      <div className="source-peek-text">{txt}</div>
    </>
  );
}
function ProseReader({ value }: { value: string }) {
  const paragraphs: React.ReactNode[] = [];
  for (const [index, chunk] of value.split(/\n\s*\n/).entries()) {
    const lines = chunk.split("\n");
    const first = lines.findIndex((x) => /^\s*[-*•]\s+/.test(x));
    if (
      first >= 0 &&
      lines.length - first >= 2 &&
      lines.slice(first).every((x) => /^\s*[-*•]\s+/.test(x))
    ) {
      if (first)
        paragraphs.push(
          <p key={index + "p"}>
            <MathText value={lines.slice(0, first).join("\n")} />
          </p>,
        );
      paragraphs.push(
        <ul key={index}>
          {lines.slice(first).map((x, i) => (
            <li key={i}>
              <MathText value={x.replace(/^\s*[-*•]\s+/, "")} />
            </li>
          ))}
        </ul>,
      );
    } else if (chunk.trim())
      paragraphs.push(
        <p key={index}>
          <MathText value={chunk} />
        </p>,
      );
  }
  return <>{paragraphs}</>;
}
function visibleBlockTitle(block: Block) {
  if (!["definition", "rule"].includes(block.kind)) return block.title;
  const title = block.title.replace(/^(?:(?:التعريف|تعريف|القاعدة|قاعدة|قانون|نظرية)\s*[:：—–-]\s*)+/, "").trim();
  return ["التعريف", "تعريف", "القاعدة", "قاعدة", "قانون", "نظرية"].includes(title) ? "" : title;
}
function BlockReader({
  b,
  lid,
  theme,
}: {
  b: Block;
  lid: string;
  theme: ThemeName;
}) {
  return (
    <div className={"block-reader " + b.kind}>
      {visibleBlockTitle(b) && <h3>{visibleBlockTitle(b)}</h3>}
      {["figure", "table", "exercise"].includes(b.kind) && b.text && (
        <ProseReader value={b.text} />
      )}
      {b.kind === "equation" ? (
        <>
          <MathText value={b.latex} display />
          {b.text && <ProseReader value={b.text} />}
        </>
      ) : b.kind === "figure" ? (
        <>
          <img
            src={apiURL(
              "/api/lectures/" + lid + "/figures/" + b.id + "?theme=" + theme
            )}
            alt={b.figure?.caption || "رسم علمي"}
          />
          <small>{b.figure?.caption}</small>
        </>
      ) : b.kind === "table" ? (
        <table>
          <thead>
            <tr>
              {b.headers.map((x, i) => (
                <th key={i}>
                  <span
                    className={
                      /\\\([\s\S]*?\\\)|\$(?!\$)[^\n$]+\$/.test(x)
                        ? "math-header-inset"
                        : undefined
                    }
                  >
                    <MathText value={x} />
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {b.rows.map((row, i) => (
              <tr key={i}>
                {row.map((v, j) => (
                  <td key={j}>
                    <MathText value={v} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      ) : b.kind === "list" ? (
        <>
          {b.text && <ProseReader value={b.text} />}
          {b.ordered ? (
            <ol>
              {(b.items || []).map((v, i) => (
                <li key={i}>
                  <MathText value={v} />
                </li>
              ))}
            </ol>
          ) : (
            <ul>
              {(b.items || []).map((v, i) => (
                <li key={i}>
                  <MathText value={v} />
                </li>
              ))}
            </ul>
          )}
        </>
      ) : b.kind === "exercise" ? (
        <>
          <p>
            <MathText value={b.problem} />
          </p>
          {b.givens && (
            <p>
              <b>المعطيات: </b>
              <MathText value={b.givens} />
            </p>
          )}
          <ol>
            {b.steps.map((s, i) => (
              <li key={i}>
                <MathText value={s} />
              </li>
            ))}
          </ol>
          <strong>
            <MathText value={b.result} />
          </strong>
        </>
      ) : (
        <ProseReader value={b.text} />
      )}
    </div>
  );
}
function BlockEditor({
  b,
  sources,
  palette,
  onChange,
  act,
  notify,
}: {
  b: Block;
  sources: Source[];
  palette: string;
  onChange: (b: Block) => void;
  act: Act;
  notify: (m: string) => void;
}) {
  const [figureUrl, setFigureUrl] = useState("");
  const [pastedTable, setPastedTable] = useState("");
  useEffect(() => {
    setFigureUrl("");
  }, [palette]);
  useEffect(
    () => () => {
      if (figureUrl) URL.revokeObjectURL(figureUrl);
    },
    [figureUrl],
  );
  const set = (key: keyof Block, value: any) =>
    onChange({ ...b, [key]: value });
  return (
    <div className="block-form">
      <Field
        label="عنوان اختياري"
        value={b.title}
        onChange={(s) => set("title", s)}
      />
      {b.kind === "equation" ? (
        <>
          <Field
            label="المعادلة بصيغة LaTeX"
            dir="ltr"
            area
            value={b.latex}
            onChange={(s) => set("latex", s)}
          />
          <MathText value={b.latex} display />
          <button
            className="text-button"
            onClick={() =>
              act(async () => {
                await api("/math/check", {
                  method: "POST",
                  body: JSON.stringify({ latex: b.latex }),
                });
                notify("نجح إنشاء المعادلة الأصلية لـWord.");
              })
            }
          >
            فحص التوافق مع Word
          </button>
          <Field
            label="شرح الرموز والوحدات"
            area
            value={b.text}
            onChange={(s) => set("text", s)}
          />
        </>
      ) : b.kind === "list" ? (
        <>
          <Field
            label="تمهيد اختياري للقائمة"
            area
            value={b.text}
            onChange={(v) => set("text", v)}
          />
          <label className="checkbox">
            <input
              type="checkbox"
              checked={!!b.ordered}
              onChange={(e) => set("ordered", e.target.checked)}
            />
            قائمة مرقّمة
          </label>
          {(b.items || []).map((item, i) => (
            <div className="step-edit" key={i}>
              <span>{i + 1}</span>
              <textarea
                aria-label={"عنصر القائمة " + (i + 1)}
                value={item}
                onChange={(e) =>
                  set(
                    "items",
                    (b.items || []).map((v, j) =>
                      j === i ? e.target.value : v,
                    ),
                  )
                }
              />
              <button
                className="icon-button"
                title="حذف العنصر"
                onClick={() =>
                  set(
                    "items",
                    (b.items || []).filter((_, j) => j !== i),
                  )
                }
              >
                <X size={15} />
              </button>
            </div>
          ))}
          <button
            className="text-button"
            onClick={() => set("items", [...(b.items || []), ""])}
          >
            <Plus size={14} />
            عنصر قائمة
          </button>
        </>
      ) : b.kind === "exercise" ? (
        <>
          <Field
            label="نص المسألة"
            area
            value={b.problem}
            onChange={(s) => set("problem", s)}
          />
          <Field
            label="المعطيات"
            area
            value={b.givens}
            onChange={(s) => set("givens", s)}
          />
          <label className="field">
            <span>خطوات الحل</span>
          </label>
          {b.steps.map((step, i) => (
            <div className="step-edit" key={i}>
              <span>{i + 1}</span>
              <textarea
                aria-label={"خطوة الحل " + (i + 1)}
                value={step}
                onChange={(e) =>
                  set(
                    "steps",
                    b.steps.map((s, j) => (j === i ? e.target.value : s)),
                  )
                }
              />
              <button
                title="حذف الخطوة"
                className="icon-button"
                onClick={() =>
                  set(
                    "steps",
                    b.steps.filter((_, j) => j !== i),
                  )
                }
              >
                <X size={15} />
              </button>
            </div>
          ))}
          <button
            className="text-button"
            onClick={() => set("steps", [...b.steps, ""])}
          >
            <Plus size={14} />
            خطوة حل
          </button>
          <Field
            label="النتيجة"
            value={b.result}
            onChange={(s) => set("result", s)}
          />
          <label className="checkbox">
            <input
              type="checkbox"
              checked={b.verbatim}
              onChange={(e) => set("verbatim", e.target.checked)}
            />
            نص السؤال حرفي من الكتاب؛ يحتاج مقتطفًا مطابقًا في المرجع
          </label>
        </>
      ) : b.kind === "table" ? (
        <>
          <details className="paste-table"><summary>لصق جدول من Word أو Excel</summary>
            <textarea aria-label="بيانات الجدول الملصوق" value={pastedTable} onChange={e=>setPastedTable(e.target.value)} placeholder="انسخ خلايا الجدول والصقها هنا؛ أول صف لعناوين الأعمدة."/>
            <button className="button secondary small" disabled={!pastedTable.trim()} onClick={()=>{
              const rows=pastedTable.trim().split(/\r?\n/).map(line=>line.split("\t"));
              const width=Math.max(...rows.map(row=>row.length));
              const normalized=rows.map(row=>[...row,...Array(width-row.length).fill("")]);
              onChange({...b,headers:normalized[0],rows:normalized.slice(1)});setPastedTable("");
            }}>استخدام البيانات بدل الجدول الحالي</button></details>
          <div className="table-editor">
            <table>
              <thead>
                <tr>
                  {b.headers.map((value, j) => (
                    <th key={j}>
                      <input
                        aria-label={"عنوان العمود " + (j + 1)}
                        value={value}
                        onChange={(e) =>
                          set(
                            "headers",
                            b.headers.map((v, k) =>
                              k === j ? e.target.value : v,
                            ),
                          )
                        }
                      />
                      <button
                        title="حذف العمود"
                        disabled={b.headers.length === 1}
                        onClick={() =>
                          onChange({
                            ...b,
                            headers: b.headers.filter((_, k) => k !== j),
                            rows: b.rows.map((r) =>
                              r.filter((_, k) => k !== j),
                            ),
                          })
                        }
                      >
                        ×
                      </button>
                    </th>
                  ))}
                  <th />
                </tr>
              </thead>
              <tbody>
                {b.rows.map((row, i) => (
                  <tr key={i}>
                    {row.map((value, j) => (
                      <td key={j}>
                        <textarea
                          aria-label={`خلية ${i + 1} ${j + 1}`}
                          value={value}
                          onChange={(e) =>
                            set(
                              "rows",
                              b.rows.map((r, k) =>
                                k === i
                                  ? r.map((v, l) =>
                                      l === j ? e.target.value : v,
                                    )
                                  : r,
                              ),
                            )
                          }
                        />
                      </td>
                    ))}
                    <td>
                      <button
                        title="حذف الصف"
                        className="icon-button"
                        onClick={() =>
                          set(
                            "rows",
                            b.rows.filter((_, k) => k !== i),
                          )
                        }
                      >
                        <X size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="actions">
            <button
              className="text-button"
              onClick={() => set("rows", [...b.rows, b.headers.map(() => "")])}
            >
              <Plus size={14} />
              صف
            </button>
            <button
              className="text-button"
              onClick={() =>
                onChange({
                  ...b,
                  headers: [...b.headers, "عمود جديد"],
                  rows: b.rows.map((r) => [...r, ""]),
                })
              }
            >
              <Plus size={14} />
              عمود
            </button>
          </div>
        </>
      ) : b.kind === "figure" && b.figure ? (
        <>
          <FigureEditor spec={b.figure} onChange={(s) => set("figure", s)} />
          <button
            className="button secondary small"
            onClick={() =>
              act(async () => {
                const r = await apiRaw("/figures/preview", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ block: b, palette }),
                });
                if (!r.ok) {
                  const e = await r.json();
                  throw new Error(e.message || "تعذر رسم الشكل");
                }
                setFigureUrl(URL.createObjectURL(await r.blob()));
              })
            }
          >
            <Eye size={15} />
            توليد الرسم للمراجعة
          </button>
          {figureUrl && (
            <img className="figure-preview" src={figureUrl} alt="معاينة SVG" />
          )}
        </>
      ) : (
        <>
          <Field
            label="المحتوى العلمي"
            area
            value={b.text}
            onChange={(s) => set("text", s)}
            placeholder="اكتب شرحًا مباشرًا. للرياضيات داخل النص استخدم \( ... \)."
          />
          <div className="text-preview">
            <MathText value={b.text} />
          </div>
        </>
      )}
      <details className="block-details">
        <summary>
          المصدر والملاحظات العلمية{" "}
          <span>{b.refs.length ? `${b.refs.length} مراجع` : "بدون مرجع"}</span>
        </summary>
        <label className="field">
          <span>نوع المحتوى</span>
          <select
            value={b.origin}
            onChange={(e) => set("origin", e.target.value)}
          >
            <option value="source">من المصدر</option>
            <option value="instructor_example">مثال الدكتور</option>
            <option value="book_question">سؤال أصلي من الكتاب</option>
            <option value="clarification">توضيح إضافي</option>
            <option value="additional_exercise">تمرين إضافي</option>
          </select>
        </label>
        {b.refs.map((r, i) => (
          <div className="ref-editor" key={i}>
            <div className="form-grid">
              <label className="field">
                <span>المصدر</span>
                <select
                  value={r.source_id}
                  onChange={(e) =>
                    set(
                      "refs",
                      b.refs.map((x, j) =>
                        j === i ? { ...x, source_id: e.target.value } : x,
                      ),
                    )
                  }
                >
                  {sources.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>رقم الصفحة</span>
                <input
                  type="number"
                  min="1"
                  value={r.page}
                  onChange={(e) =>
                    set(
                      "refs",
                      b.refs.map((x, j) =>
                        j === i ? { ...x, page: +e.target.value } : x,
                      ),
                    )
                  }
                />
              </label>
            </div>
            <Field
              label="المقتطف الأصلي"
              area
              value={r.quote}
              onChange={(v) =>
                set(
                  "refs",
                  b.refs.map((x, j) => (j === i ? { ...x, quote: v } : x)),
                )
              }
            />
            <button
              className="text-button danger"
              onClick={() =>
                set(
                  "refs",
                  b.refs.filter((_, j) => j !== i),
                )
              }
            >
              إزالة المرجع
            </button>
          </div>
        ))}
        <button
          className="text-button"
          disabled={!sources.length}
          onClick={() =>
            set("refs", [
              ...b.refs,
              { source_id: sources[0].id, page: 1, quote: "" },
            ])
          }
        >
          <Plus size={14} />
          ربط بمصدر
        </button>
        <Field
          label="مشكلة علمية تحتاج مراجعة"
          area
          value={b.issue}
          onChange={(s) => set("issue", s)}
        />
        <Field
          label="التصحيح المقترح للمراجعة"
          area
          value={b.correction}
          onChange={(s) => set("correction", s)}
        />
        {b.issue && (
          <label className="checkbox">
            <input
              type="checkbox"
              checked={b.issue_resolved}
              onChange={(e) => set("issue_resolved", e.target.checked)}
            />
            راجعت المشكلة وصحّحت المحتوى
          </label>
        )}
      </details>
    </div>
  );
}

function FigureEditor({
  spec,
  onChange,
}: {
  spec: FigureSpec;
  onChange: (s: FigureSpec) => void;
}) {
  const set = (key: keyof FigureSpec, value: any) =>
    onChange({ ...spec, [key]: value });
  const types: Record<string, string> = {
    step: "الخطوة الواحدية",
    ramp: "الخطوة المائلة",
    impulse: "نبضة ديراك الرمزية",
    plot: "منحنى من دالة أو بيانات",
    scatter: "مخطط مبعثر",
    bar: "أعمدة من بيانات",
    histogram: "مدرج تكراري",
    control_diagram: "مخطط تحكم مع جوامع وتفرعات",
    block_diagram: "مخطط كتل",
    circuit: "دارة كهربائية",
    source_crop: "قص من صفحة المصدر",
  };
  return (
    <>
      <div className="form-grid">
        <label className="field">
          <span>نوع الرسم</span>
          <select
            value={spec.kind}
            onChange={(e) => onChange({...spec, kind:e.target.value, control:e.target.value === "control_diagram" ? spec.control ?? initialControl() : null})}
          >
            {Object.entries(types).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <Field
          label="شرح الرسم"
          value={spec.caption}
          onChange={(s) => set("caption", s)}
        />
      </div>
      {spec.kind === "control_diagram" && <ControlDiagramEditor spec={spec.control ?? initialControl()} onChange={control=>set("control",control)}/>}
      {[
        "step",
        "ramp",
        "impulse",
        "plot",
        "scatter",
        "bar",
        "histogram",
      ].includes(spec.kind) && (
        <div className="form-grid">
          <Field
            label="المحور الأفقي"
            dir="ltr"
            value={spec.xlabel}
            onChange={(s) => set("xlabel", s)}
          />
          <Field
            label="المحور العمودي"
            dir="ltr"
            value={spec.ylabel}
            onChange={(s) => set("ylabel", s)}
          />
          {!["bar", "histogram"].includes(spec.kind) && (
            <>
              <label className="field">
                <span>بداية المجال</span>
                <input
                  type="number"
                  value={spec.xmin}
                  onChange={(e) => set("xmin", +e.target.value)}
                />
              </label>
              <label className="field">
                <span>نهاية المجال</span>
                <input
                  type="number"
                  value={spec.xmax}
                  onChange={(e) => set("xmax", +e.target.value)}
                />
              </label>
            </>
          )}
        </div>
      )}
      {["plot", "scatter"].includes(spec.kind) && (
        <>
          {spec.series.map((s, i) => (
            <div className="subpanel" key={i}>
              <div className="form-grid">
                <Field
                  label="اسم المنحنى"
                  value={s.label}
                  onChange={(v) =>
                    set(
                      "series",
                      spec.series.map((x, j) =>
                        j === i ? { ...x, label: v } : x,
                      ),
                    )
                  }
                />
                <label className="field">
                  <span>نمط الخط</span>
                  <select
                    value={s.style}
                    onChange={(e) =>
                      set(
                        "series",
                        spec.series.map((x, j) =>
                          j === i ? { ...x, style: e.target.value } : x,
                        ),
                      )
                    }
                  >
                    {["solid", "dashed", "dotted", "dashdot"].map((v) => (
                      <option key={v}>{v}</option>
                    ))}
                  </select>
                </label>
              </div>
              {spec.kind === "plot" && (
                <Field
                  label="الدالة من المصدر (x أو t)"
                  dir="ltr"
                  value={s.expression}
                  onChange={(v) =>
                    set(
                      "series",
                      spec.series.map((x, j) =>
                        j === i ? { ...x, expression: v } : x,
                      ),
                    )
                  }
                />
              )}
              <div className="form-grid">
                <NumberList
                  label="قيم x عند استخدام بيانات"
                  values={s.x}
                  onChange={(v) =>
                    set(
                      "series",
                      spec.series.map((x, j) => (j === i ? { ...x, x: v } : x)),
                    )
                  }
                />
                <NumberList
                  label="قيم y عند استخدام بيانات"
                  values={s.y}
                  onChange={(v) =>
                    set(
                      "series",
                      spec.series.map((x, j) => (j === i ? { ...x, y: v } : x)),
                    )
                  }
                />
              </div>
              <button
                className="text-button danger"
                onClick={() =>
                  set(
                    "series",
                    spec.series.filter((_, j) => j !== i),
                  )
                }
              >
                إزالة المنحنى
              </button>
            </div>
          ))}
          <button
            className="text-button"
            onClick={() =>
              set("series", [
                ...spec.series,
                {
                  label: "",
                  expression: "",
                  x: [],
                  y: [],
                  style: ["solid", "dashed", "dotted", "dashdot"][
                    spec.series.length % 4
                  ],
                },
              ])
            }
          >
            <Plus size={14} />
            إضافة منحنى من المصدر
          </button>
          <p className="hint" dir="ltr">
            sin · cos · exp · sqrt · log · abs · step · pi. No arbitrary code.
          </p>
        </>
      )}
      {["bar", "histogram"].includes(spec.kind) && (
        <>
          <NumberList
            label="القيم كما وردت في المصدر"
            values={spec.values}
            onChange={(v) => set("values", v)}
          />
          {spec.kind === "bar" ? (
            <StringList
              label="تسميات الفئات — سطر لكل فئة"
              values={spec.labels}
              onChange={(v) => set("labels", v)}
            />
          ) : (
            <label className="field">
              <span>عدد الفئات</span>
              <input
                type="number"
                min="1"
                max="100"
                value={spec.bins}
                onChange={(e) => set("bins", +e.target.value)}
              />
            </label>
          )}
        </>
      )}
      {["block_diagram", "circuit"].includes(spec.kind) && (
        <>
          <p className="hint">
            أدخل العقد والتوصيلات المثبتة في المصدر فقط. الإحداثيات لضبط موضع
            الرسم وليست أبعادًا فيزيائية.
          </p>
          {spec.nodes.map((n, i) => (
            <div className="node-row" key={i}>
              <Field
                label="معرّف العقدة"
                dir="ltr"
                value={n.id}
                onChange={(v) =>
                  set(
                    "nodes",
                    spec.nodes.map((x, j) => (j === i ? { ...x, id: v } : x)),
                  )
                }
              />
              <Field
                label="التسمية"
                value={n.label}
                onChange={(v) =>
                  set(
                    "nodes",
                    spec.nodes.map((x, j) =>
                      j === i ? { ...x, label: v } : x,
                    ),
                  )
                }
              />
              <label className="field">
                <span>x</span>
                <input
                  type="number"
                  min="50"
                  max="1000"
                  value={n.x}
                  onChange={(e) =>
                    set(
                      "nodes",
                      spec.nodes.map((x, j) =>
                        j === i ? { ...x, x: +e.target.value } : x,
                      ),
                    )
                  }
                />
              </label>
              <label className="field">
                <span>y</span>
                <input
                  type="number"
                  min="30"
                  max="1000"
                  value={n.y}
                  onChange={(e) =>
                    set(
                      "nodes",
                      spec.nodes.map((x, j) =>
                        j === i ? { ...x, y: +e.target.value } : x,
                      ),
                    )
                  }
                />
              </label>
              <button
                className="icon-button danger"
                title="حذف العقدة"
                onClick={() =>
                  set(
                    "nodes",
                    spec.nodes.filter((_, j) => j !== i),
                  )
                }
              >
                <X size={15} />
              </button>
            </div>
          ))}
          <button
            className="text-button"
            onClick={() =>
              set("nodes", [
                ...spec.nodes,
                {
                  id: "n" + (spec.nodes.length + 1),
                  label: "",
                  x: 80 + spec.nodes.length * 150,
                  y: 80,
                },
              ])
            }
          >
            <Plus size={14} />
            عقدة
          </button>
          {spec.edges.map((e, i) => (
            <div className="edge-row" key={i}>
              <label className="field">
                <span>من</span>
                <select
                  value={e.start}
                  onChange={(ev) =>
                    set(
                      "edges",
                      spec.edges.map((x, j) =>
                        j === i ? { ...x, start: ev.target.value } : x,
                      ),
                    )
                  }
                >
                  {spec.nodes.map((n) => (
                    <option key={n.id} value={n.id}>
                      {n.label || n.id}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>إلى</span>
                <select
                  value={e.end}
                  onChange={(ev) =>
                    set(
                      "edges",
                      spec.edges.map((x, j) =>
                        j === i ? { ...x, end: ev.target.value } : x,
                      ),
                    )
                  }
                >
                  {spec.nodes.map((n) => (
                    <option key={n.id} value={n.id}>
                      {n.label || n.id}
                    </option>
                  ))}
                </select>
              </label>
              <Field
                label="التسمية أو القيمة من المصدر"
                value={e.label}
                onChange={(v) =>
                  set(
                    "edges",
                    spec.edges.map((x, j) =>
                      j === i ? { ...x, label: v } : x,
                    ),
                  )
                }
              />
              {spec.kind === "circuit" && (
                <label className="field">
                  <span>العنصر</span>
                  <select
                    value={e.kind}
                    onChange={(ev) =>
                      set(
                        "edges",
                        spec.edges.map((x, j) =>
                          j === i ? { ...x, kind: ev.target.value } : x,
                        ),
                      )
                    }
                  >
                    {Object.entries({
                      wire: "سلك",
                      resistor: "مقاومة",
                      capacitor: "مكثف",
                      inductor: "ملف",
                      voltage: "مصدر جهد",
                      arrow: "سهم",
                    }).map(([k, v]) => (
                      <option key={k} value={k}>
                        {v}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <button
                className="icon-button danger"
                title="حذف التوصيل"
                onClick={() =>
                  set(
                    "edges",
                    spec.edges.filter((_, j) => j !== i),
                  )
                }
              >
                <X size={15} />
              </button>
            </div>
          ))}
          <button
            disabled={spec.nodes.length < 2}
            className="text-button"
            onClick={() =>
              set("edges", [
                ...spec.edges,
                {
                  start: spec.nodes[0].id,
                  end: spec.nodes[1].id,
                  label: "",
                  kind: spec.kind === "circuit" ? "wire" : "arrow",
                },
              ])
            }
          >
            <Plus size={14} />
            توصيل
          </button>
        </>
      )}
      {spec.kind === "source_crop" && (
        <>
          <p className="hint">
            يؤخذ القص من أول مرجع في «المصدر والملاحظات». الحدود نسبية: اليسار،
            الأعلى، اليمين، الأسفل.
          </p>
          <div className="form-grid">
            {["اليسار", "الأعلى", "اليمين", "الأسفل"].map((label, i) => (
              <label className="field" key={i}>
                <span>{label}</span>
                <input
                  type="number"
                  min="0"
                  max="1"
                  step=".01"
                  value={(spec.crop || [0, 0, 1, 1])[i]}
                  onChange={(e) => {
                    const c = [...(spec.crop || [0, 0, 1, 1])];
                    c[i] = +e.target.value;
                    set("crop", c);
                  }}
                />
              </label>
            ))}
          </div>
        </>
      )}
    </>
  );
}
function NumberList({
  label,
  values,
  onChange,
}: {
  label: string;
  values: number[];
  onChange: (n: number[]) => void;
}) {
  const [raw, setRaw] = useState(values.join(", "));
  useEffect(() => setRaw(values.join(", ")), [JSON.stringify(values)]);
  return (
    <label className="field">
      <span>{label}</span>
      <textarea
        dir="ltr"
        value={raw}
        onChange={(e) => setRaw(e.target.value)}
        onBlur={() => {
          const list = raw.trim()
            ? raw
                .split(/[,،\s]+/)
                .filter(Boolean)
                .map(Number)
            : [];
          if (list.every(Number.isFinite)) onChange(list);
        }}
      />
    </label>
  );
}
function StringList({
  label,
  values,
  onChange,
}: {
  label: string;
  values: string[];
  onChange: (n: string[]) => void;
}) {
  const [raw, setRaw] = useState(values.join("\n"));
  useEffect(() => setRaw(values.join("\n")), [JSON.stringify(values)]);
  return (
    <label className="field">
      <span>{label}</span>
      <textarea
        value={raw}
        onChange={(e) => setRaw(e.target.value)}
        onBlur={() => onChange(raw.split("\n"))}
      />
    </label>
  );
}
function Exports({
  doc,
  theme,
  themeSaving,
  fonts,
  lid,
  jobs,
  exports,
  revision,
  saveNow,
  reload,
  act,
}: {
  doc: LectureDoc;
  theme?: LectureTheme;
  themeSaving: boolean;
  fonts?: Record<string, string>;
  lid: string;
  jobs: Job[];
  exports: Export[];
  revision: number;
  saveNow: () => Promise<boolean>;
  reload: () => Promise<any>;
  act: Act;
}) {
  const [checks, setChecks] = useState<any>(null),
    [selected, setSelected] = useState(""),
    [page, setPage] = useState(1),
    [draft, setDraft] = useState(false),
    [requesting, setRequesting] = useState(false),
    [scale, setScale] = useState(100);
  const latest = exports.find((e) => e.export_id === selected) || exports[0];
  const busy = jobs.some(
    (j) => j.kind === "export" && ["queued", "running"].includes(j.status),
  );
  useEffect(() => {
    act(async () => {
      if (await saveNow()) setChecks(await api("/lectures/" + lid + "/checks"));
    });
  }, [lid, revision]);
  return (
    <>
      <div className="export-layout">
        <aside className="export-options panel">
          <span className="eyebrow">النسخة التي تصل إلى الطلاب</span>
          <h2>معاينة وتصدير</h2>
          <p>
            PDF مرجع التنسيق والطباعة. يمكن اختيار معادلات Word الأصلية أو عرضها كصور ثابتة من إعدادات المحاضرة؛ يبقى LaTeX قابلًا للتعديل هنا.
          </p>
          <div className="export-summary">
            <span>
              الخط<b>{fonts?.ar_body || ""}</b>
            </span>
            <span>
              لون المحاضرة<b style={{ color: theme?.dark }}>{theme?.label}</b>
            </span>
            <span>
              حجم النص<b>{doc.settings.font_size} pt</b>
            </span>
            <span>
              تباعد الأسطر<b>{doc.settings.line_spacing}</b>
            </span>
          </div>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={draft}
              onChange={(e) => setDraft(e.target.checked)}
            />
            إظهار علامة مسودة للمراجعة
          </label>
          <button
            className="button primary full"
            disabled={busy || requesting || themeSaving}
            onClick={() =>
              act(async () => {
                if (!(await saveNow())) return;
                setRequesting(true);
                try {
                  await api("/lectures/" + lid + "/exports", {
                    method: "POST",
                    body: JSON.stringify({ draft }),
                  });
                  await reload();
                  setSelected("");
                  setPage(1);
                } finally {
                  setRequesting(false);
                }
              })
            }
          >
            <FileOutput size={17} />
            {busy || requesting ? "جارٍ تجهيز المستند…" : "تجهيز Word وPDF"}
          </button>
          {latest && (
            <>
              <div className="download-pair">
                <a
                  className="button secondary"
                  href={apiURL("/api/exports/" + latest.export_id + "/docx")}
                  download
                >
                  <Download size={16} />
                  Word
                </a>
                <a
                  className="button secondary"
                  href={apiURL("/api/exports/" + latest.export_id + "/pdf")}
                  download
                >
                  <Download size={16} />
                  PDF
                </a>
              </div>
              <div className="export-metrics">
                <span>
                  <b>{latest.pages}</b>صفحات
                </span>
                <span>
                  <b>{latest.equations}</b>معادلات
                </span>
                <span>
                  <b>{latest.figures}</b>رسومات
                </span>
              </div>
              {(latest.revision !== revision || latest.theme !== theme?.id) && (
                <p className="inline-error">
                  تغيّر المحتوى أو لون المحاضرة بعد هذا التصدير. جهّز نسخة جديدة
                  لتحديث المعاينة.
                </p>
              )}
              <p className="hint">
                {latest.math_mode === "portable" ? "المعادلات صور ثابتة عالية الدقة؛ تعديلها من الداشبورد." : "المعادلات أصلية وقابلة للتحرير داخل Word."} لم يُختبر فتح هذا الملف في Microsoft Word.
              </p>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={latest.visual_review === "user_reviewed"}
                  onChange={(e) => {
                    if (e.target.checked)
                      act(async () => {
                        await api("/exports/" + latest.export_id + "/review", {
                          method: "POST",
                        });
                        await reload();
                      });
                  }}
                />
                راجعت جميع صفحات هذه النسخة بصريًا
              </label>
            </>
          )}
          {checks && (
            <details className="checks" open={checks.issues.length > 0}>
              <summary>
                مراجعة المحتوى <span>{checks.issues.length} ملاحظات</span>
              </summary>
              <p className="hint">
                {checks.covered_pages} / {checks.source_pages} صفحات لها مراجع.
                هذا لا يثبت وحده اكتمال المحتوى العلمي.
              </p>
              {checks.issues.map((x: any, i: number) => (
                <p className={"check-item " + x.severity} key={i}>
                  <AlertCircle size={14} />
                  {x.message}
                </p>
              ))}
            </details>
          )}
          {exports.length > 0 && (
            <label className="field">
              <span>نسخ التصدير السابقة</span>
              <select
                value={latest?.export_id}
                onChange={(e) => {
                  setSelected(e.target.value);
                  setPage(1);
                }}
              >
                {exports.map((e) => (
                  <option value={e.export_id} key={e.export_id}>
                    {new Date(e.created).toLocaleString("ar")}
                    {" · " + (e.theme ? e.theme : "التصميم السابق")}
                    {e.draft ? " · مسودة" : ""}
                  </option>
                ))}
              </select>
            </label>
          )}
        </aside>
        <section className="pdf-stage">
          {!latest ? (
            <Empty
              title="محاضرتك، كما ستُطبع"
              description="جهّز المستند لتظهر هنا معاينة PDF الفعلية، بما فيها المعادلات والرسومات والفهرس."
            />
          ) : (
            <>
              <div className="pdf-toolbar">
                <div className="actions">
                  <button
                    className="icon-button"
                    title="الصفحة السابقة"
                    disabled={page <= 1}
                    onClick={() => setPage((p) => p - 1)}
                  >
                    <ChevronUp size={18} />
                  </button>
                  <label>
                    صفحة{" "}
                    <select
                      aria-label="صفحة المعاينة"
                      value={page}
                      onChange={(e) => setPage(+e.target.value)}
                    >
                      {Array.from({ length: latest.pages }, (_, i) => (
                        <option key={i} value={i + 1}>
                          {i + 1}
                        </option>
                      ))}
                    </select>{" "}
                    من {latest.pages}
                  </label>
                  <button
                    className="icon-button"
                    title="الصفحة التالية"
                    disabled={page >= latest.pages}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    <ChevronDown size={18} />
                  </button>
                </div>
                <select
                  aria-label="تكبير المعاينة"
                  value={scale}
                  onChange={(e) => setScale(+e.target.value)}
                >
                  {[75, 100, 125, 150].map((s) => (
                    <option key={s} value={s}>
                      {s}%
                    </option>
                  ))}
                </select>
                <a
                  href={apiURL("/api/exports/" + latest.export_id + "/pdf")}
                  target="_blank"
                  className="text-button"
                >
                  فتح PDF <ExternalLink size={14} />
                </a>
              </div>
              <div className="pdf-scroll">
                <img
                  style={{ width: scale + "%" }}
                  src={apiURL("/api/exports/" + latest.export_id + "/pages/" + page)}
                  alt={"معاينة الصفحة " + page}
                />
              </div>
            </>
          )}
        </section>
      </div>
      <JobList jobs={jobs.filter((j) => j.kind === "export")} act={act} />
    </>
  );
}

createRoot(document.getElementById("root")!).render(<AccountRoot Editor={App} />);
