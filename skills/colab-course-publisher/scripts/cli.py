#!/usr/bin/env python3
"""CourseViewerPlatform course outline and validation helper."""

from __future__ import annotations

import argparse
import html.parser
import json
import posixpath
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote


ALLOWED_LESSON_TYPES = {"content", "quiz", "section"}
ALLOWED_QUESTION_TYPES = {"MULTIPLE_CHOICE", "MULTIPLE_RESPONSE", "MATCHING"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico"}
VIDEO_EXTS = {".mp4", ".webm"}
AUDIO_EXTS = {".mp3"}
DOCUMENT_EXTS = {".pdf"}
TEXT_ARTIFACT_EXTS = {".html", ".css", ".js"}
SUPPORTED_LOCAL_EXTS = IMAGE_EXTS | VIDEO_EXTS | AUDIO_EXTS | DOCUMENT_EXTS | TEXT_ARTIFACT_EXTS


@dataclass
class Finding:
    severity: str
    path: str
    message: str


class Reporter:
    def __init__(self) -> None:
        self.findings: list[Finding] = []
        self.checked: list[str] = []
        self._validated_widgets: set[Path] = set()

    def add(self, severity: str, path: Path | str, message: str) -> None:
        self.findings.append(Finding(severity, str(path), message))

    def error(self, path: Path | str, message: str) -> None:
        self.add("error", path, message)

    def warn(self, path: Path | str, message: str) -> None:
        self.add("warning", path, message)

    def pass_(self, path: Path | str, message: str) -> None:
        self.add("pass", path, message)

    def record(self, label: str) -> None:
        self.checked.append(label)

    def summary(self) -> dict[str, int]:
        return {
            "passes": sum(1 for f in self.findings if f.severity == "pass"),
            "warnings": sum(1 for f in self.findings if f.severity == "warning"),
            "errors": sum(1 for f in self.findings if f.severity == "error"),
        }

    def to_json(self, strict: bool) -> dict[str, Any]:
        summary = self.summary()
        ok = summary["errors"] == 0 and (not strict or summary["warnings"] == 0)
        return {
            "ok": ok,
            "strict": strict,
            "summary": summary,
            "checked": self.checked,
            "findings": [f.__dict__ for f in self.findings],
        }

    def print_human(self, strict: bool) -> None:
        icons = {"pass": "[OK]", "warning": "[WARN]", "error": "[ERROR]"}
        for finding in self.findings:
            print(f"{icons[finding.severity]} {finding.path}: {finding.message}")
        summary = self.summary()
        print()
        print(
            "Results: "
            f"{summary['passes']} passed, "
            f"{summary['errors']} error(s), "
            f"{summary['warnings']} warning(s)"
        )
        if strict and summary["warnings"]:
            print("Strict mode treats warnings as failures.")


class HtmlReferenceParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.refs: list[tuple[str, str]] = []
        self.has_script = False
        self.has_event_handler = False
        self.has_javascript_url = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "script":
            self.has_script = True
        for name, value in attrs:
            lower_name = name.lower()
            if lower_name.startswith("on"):
                self.has_event_handler = True
            if value is None:
                continue
            if lower_name in {"src", "href", "poster"}:
                self.refs.append((lower_name, value))
            if value.strip().lower().startswith("javascript:"):
                self.has_javascript_url = True


def read_json(path: Path, reporter: Reporter) -> Any | None:
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        reporter.error(path, "file not found")
    except json.JSONDecodeError as exc:
        reporter.error(path, f"invalid JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}")
    except OSError as exc:
        reporter.error(path, f"could not read file: {exc}")
    return None


def is_safe_id(value: Any) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value))


def is_kebab_case(value: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9-]*[a-z0-9]", value))


def is_url(value: str) -> bool:
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", value))


def strip_ref_suffix(value: str) -> str:
    return value.split("#", 1)[0].split("?", 1)[0]


def safe_resolve(base: Path, raw_ref: str) -> Path | None:
    ref = unquote(strip_ref_suffix(raw_ref.strip()))
    if not ref or is_url(ref) or ref.startswith("/"):
        return None
    normalised = posixpath.normpath(ref.replace("\\", "/"))
    if normalised == "." or normalised.startswith("../") or normalised == "..":
        return None
    return (base / Path(*normalised.split("/"))).resolve()


def resolve_relative(base_file: Path, raw_ref: str) -> Path | None:
    ref = unquote(strip_ref_suffix(raw_ref.strip()))
    if not ref or is_url(ref) or ref.startswith("/"):
        return None
    normalised = posixpath.normpath(ref.replace("\\", "/"))
    if normalised == ".":
        return None
    return (base_file.parent / Path(*normalised.split("/"))).resolve()


def ensure_inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def find_content_root(path: Path) -> Path:
    current = path.resolve()
    if current.is_file():
        current = current.parent
    for candidate in [current, *current.parents]:
        if (candidate / "courses").is_dir() or (candidate / "modules").is_dir() or (candidate / "widgets").is_dir():
            return candidate
    return current


def module_dir_for(content_root: Path, module_id: str) -> Path:
    return content_root / "modules" / module_id


def validate_required_string(obj: dict[str, Any], key: str, path: Path, reporter: Reporter) -> bool:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        reporter.error(path, f"missing or invalid string field '{key}'")
        return False
    return True


def validate_cover(course_dir: Path, manifest_path: Path, value: Any, reporter: Reporter) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not value.strip():
        reporter.error(manifest_path, "coverImage must be a non-empty string when present")
        return
    if is_url(value):
        reporter.warn(manifest_path, f"coverImage is external and cannot be validated locally: {value}")
        return
    candidates = []
    if value.startswith("assets/"):
        candidates.append(course_dir / value)
    else:
        candidates.append(course_dir / "assets" / value)
        candidates.append(course_dir / value)
    if not any(candidate.exists() for candidate in candidates):
        reporter.error(manifest_path, f"coverImage not found: {value}")


def validate_course_markdown(path: Path, course_root: Path, reporter: Reporter, widgets_dir: Path | None) -> None:
    if not path.exists():
        reporter.error(path, "markdown file not found")
        return
    validate_markdown(path, course_root, reporter, widgets_dir, lesson_context=False)


def validate_course_json(course_dir: Path, content_root: Path, reporter: Reporter, widgets_dir: Path | None) -> list[str]:
    course_path = course_dir / "course.json"
    data = read_json(course_path, reporter)
    if not isinstance(data, dict):
        return []
    reporter.record(f"course:{course_dir.name}")
    validate_required_string(data, "title", course_path, reporter)
    course_id = data.get("id", course_dir.name)
    if "id" in data:
        if not is_safe_id(course_id):
            reporter.error(course_path, "id must be URL-safe")
        elif course_id != course_dir.name:
            reporter.warn(course_path, f"id '{course_id}' does not match folder name '{course_dir.name}'")
    modules = data.get("modules")
    module_ids: list[str] = []
    if not isinstance(modules, list) or not modules:
        reporter.error(course_path, "modules must be a non-empty array of module ID strings")
    else:
        seen: set[str] = set()
        for module_id in modules:
            if not isinstance(module_id, str):
                reporter.error(course_path, f"module references must be strings, got {type(module_id).__name__}")
                continue
            if module_id in seen:
                reporter.error(course_path, f"duplicate module reference: {module_id}")
            seen.add(module_id)
            module_ids.append(module_id)
            if not module_dir_for(content_root, module_id).is_dir():
                reporter.error(course_path, f"referenced module not found in modules/: {module_id}")
    welcome = data.get("welcomePath")
    if welcome is not None:
        if not isinstance(welcome, str) or not welcome.strip():
            reporter.error(course_path, "welcomePath must be a non-empty string when present")
        else:
            welcome_path = safe_resolve(course_dir, welcome)
            if welcome_path is None or not ensure_inside(welcome_path, course_dir):
                reporter.error(course_path, f"welcomePath must be course-relative: {welcome}")
            elif not welcome_path.exists():
                reporter.error(course_path, f"welcomePath file not found: {welcome}")
            elif welcome_path.suffix.lower() != ".md":
                reporter.warn(course_path, f"welcomePath should point to markdown: {welcome}")
            else:
                validate_course_markdown(welcome_path, course_dir, reporter, widgets_dir)
    validate_cover(course_dir, course_path, data.get("coverImage"), reporter)
    reporter.pass_(course_path, "course.json checked")
    return module_ids


def validate_blueprint(course_dir: Path, content_root: Path, reporter: Reporter, widgets_dir: Path | None) -> list[str]:
    blueprint_path = course_dir / "blueprint.json"
    data = read_json(blueprint_path, reporter)
    if not isinstance(data, dict):
        return []
    reporter.record(f"blueprint:{course_dir.name}")
    validate_required_string(data, "title", blueprint_path, reporter)
    blueprint_id = data.get("id", course_dir.name)
    if "id" in data and blueprint_id != course_dir.name:
        reporter.warn(blueprint_path, f"id '{blueprint_id}' does not match folder name '{course_dir.name}'")
    slot_ids: set[str] = set()
    module_ids: list[str] = []

    def check_slot(slot: Any, label: str) -> None:
        if not isinstance(slot, dict):
            reporter.error(blueprint_path, f"{label} slot must be an object")
            return
        slot_id = slot.get("slotId")
        module_id = slot.get("moduleId")
        if not isinstance(slot_id, str) or not slot_id:
            reporter.error(blueprint_path, f"{label} slot missing slotId")
        elif slot_id in slot_ids:
            reporter.error(blueprint_path, f"duplicate slotId: {slot_id}")
        else:
            slot_ids.add(slot_id)
        if not isinstance(module_id, str) or not module_id:
            reporter.error(blueprint_path, f"{label} slot missing moduleId")
        else:
            module_ids.append(module_id)
            if not module_dir_for(content_root, module_id).is_dir():
                reporter.error(blueprint_path, f"{label} references missing module: {module_id}")

    core_modules = data.get("coreModules")
    if not isinstance(core_modules, list) or not core_modules:
        reporter.error(blueprint_path, "coreModules must be a non-empty array")
    else:
        for slot in core_modules:
            check_slot(slot, "coreModules")
    elective_groups = data.get("electiveGroups", [])
    if elective_groups is not None:
        if not isinstance(elective_groups, list):
            reporter.error(blueprint_path, "electiveGroups must be an array when present")
        else:
            group_ids: set[str] = set()
            for group in elective_groups:
                if not isinstance(group, dict):
                    reporter.error(blueprint_path, "electiveGroups entries must be objects")
                    continue
                group_id = group.get("groupId")
                if not isinstance(group_id, str) or not group_id:
                    reporter.error(blueprint_path, "elective group missing groupId")
                elif group_id in group_ids:
                    reporter.error(blueprint_path, f"duplicate elective groupId: {group_id}")
                else:
                    group_ids.add(group_id)
                min_sel = group.get("minSelections")
                max_sel = group.get("maxSelections")
                options = group.get("options")
                if not isinstance(options, list) or not options:
                    reporter.error(blueprint_path, f"elective group '{group_id}' needs non-empty options")
                    continue
                if not isinstance(min_sel, int) or not isinstance(max_sel, int) or min_sel < 0 or max_sel < min_sel:
                    reporter.error(blueprint_path, f"elective group '{group_id}' has invalid minSelections/maxSelections")
                elif max_sel > len(options):
                    reporter.error(blueprint_path, f"elective group '{group_id}' maxSelections exceeds options count")
                for slot in options:
                    check_slot(slot, f"electiveGroups.{group_id}")
    welcome = data.get("welcomePath")
    if isinstance(welcome, str) and welcome:
        welcome_path = safe_resolve(course_dir, welcome)
        if welcome_path is None or not ensure_inside(welcome_path, course_dir):
            reporter.error(blueprint_path, f"welcomePath must be course-relative: {welcome}")
        elif not welcome_path.exists():
            reporter.error(blueprint_path, f"welcomePath file not found: {welcome}")
        elif welcome_path.suffix.lower() == ".md":
            validate_course_markdown(welcome_path, course_dir, reporter, widgets_dir)
    validate_cover(course_dir, blueprint_path, data.get("coverImage"), reporter)
    reporter.pass_(blueprint_path, "blueprint.json checked")
    return module_ids


def validate_referenced_modules(module_ids: list[str], content_root: Path, reporter: Reporter, widgets_dir: Path | None) -> None:
    seen: set[str] = set()
    for module_id in module_ids:
        if module_id in seen:
            continue
        seen.add(module_id)
        module_dir = module_dir_for(content_root, module_id)
        if module_dir.is_dir():
            validate_module(module_dir, content_root, reporter, widgets_dir)


def validate_module(module_dir: Path, content_root: Path, reporter: Reporter, widgets_dir: Path | None) -> None:
    manifest_path = module_dir / "manifest.json"
    data = read_json(manifest_path, reporter)
    if not isinstance(data, dict):
        return
    if isinstance(data.get("modules"), list):
        validate_legacy_course(module_dir, reporter, widgets_dir)
        return
    reporter.record(f"module:{module_dir.name}")
    validate_required_string(data, "id", manifest_path, reporter)
    validate_required_string(data, "title", manifest_path, reporter)
    module_id = data.get("id")
    if isinstance(module_id, str):
        if module_id != module_dir.name:
            reporter.error(manifest_path, f"id '{module_id}' does not match folder name '{module_dir.name}'")
        if not is_kebab_case(module_id):
            reporter.warn(manifest_path, "module id should be lowercase kebab-case for new content")
    lessons = data.get("lessons")
    if not isinstance(lessons, list) or not lessons:
        reporter.error(manifest_path, "lessons must be a non-empty array")
        return
    lesson_ids: set[str] = set()
    referenced: set[Path] = set()
    for index, lesson in enumerate(lessons, start=1):
        if not isinstance(lesson, dict):
            reporter.error(manifest_path, f"lesson {index} must be an object")
            continue
        lesson_id = lesson.get("id")
        lesson_type = lesson.get("type")
        if not isinstance(lesson_id, str) or not lesson_id:
            reporter.error(manifest_path, f"lesson {index} missing id")
            continue
        if lesson_id in lesson_ids:
            reporter.error(manifest_path, f"duplicate lesson id: {lesson_id}")
        lesson_ids.add(lesson_id)
        if "|||" in lesson_id:
            reporter.warn(manifest_path, f"lesson id '{lesson_id}' uses legacy separator; use local lesson IDs for module-first content")
        if lesson_type not in ALLOWED_LESSON_TYPES:
            reporter.error(manifest_path, f"lesson '{lesson_id}' has unsupported type '{lesson_type}'")
            continue
        if lesson_type == "content":
            rel = lesson.get("markdownPath")
            if not isinstance(rel, str) or not rel:
                reporter.error(manifest_path, f"content lesson '{lesson_id}' missing markdownPath")
                continue
            full = safe_resolve(module_dir, rel)
            if full is None or not ensure_inside(full, module_dir):
                reporter.error(manifest_path, f"content lesson '{lesson_id}' markdownPath must be module-relative: {rel}")
                continue
            referenced.add(full)
            if not full.exists():
                reporter.error(manifest_path, f"content lesson '{lesson_id}' file not found: {rel}")
            elif full.suffix.lower() != ".md":
                reporter.error(manifest_path, f"content lesson '{lesson_id}' must point to a markdown file")
            else:
                validate_markdown(full, content_root, reporter, widgets_dir, lesson_context=True)
        elif lesson_type == "quiz":
            rel = lesson.get("quizPath")
            if not isinstance(rel, str) or not rel:
                reporter.error(manifest_path, f"quiz lesson '{lesson_id}' missing quizPath")
                continue
            full = safe_resolve(module_dir, rel)
            if full is None or not ensure_inside(full, module_dir):
                reporter.error(manifest_path, f"quiz lesson '{lesson_id}' quizPath must be module-relative: {rel}")
                continue
            referenced.add(full)
            if not full.exists():
                reporter.error(manifest_path, f"quiz lesson '{lesson_id}' file not found: {rel}")
            else:
                validate_quiz(full, reporter)
        elif lesson_type == "section" and (lesson.get("markdownPath") or lesson.get("quizPath")):
            reporter.warn(manifest_path, f"section lesson '{lesson_id}' should not include markdownPath or quizPath")
    check_orphaned_module_files(module_dir, referenced, reporter)
    reporter.pass_(manifest_path, f"module manifest checked with {len(lesson_ids)} lesson(s)")


def validate_quiz(path: Path, reporter: Reporter) -> None:
    data = read_json(path, reporter)
    if not isinstance(data, dict):
        return
    if data.get("type") != "quiz":
        reporter.error(path, "quiz type must be 'quiz'")
    validate_required_string(data, "title", path, reporter)
    score = data.get("passingScore")
    if score is None:
        reporter.warn(path, "passingScore missing; use 70 unless the course needs a different threshold")
    elif not isinstance(score, (int, float)) or score < 0 or score > 100:
        reporter.error(path, "passingScore must be a number from 0 to 100")
    questions = data.get("questions")
    if not isinstance(questions, list) or not questions:
        reporter.error(path, "questions must be a non-empty array")
        return
    question_ids: set[str] = set()
    for q_index, question in enumerate(questions, start=1):
        if not isinstance(question, dict):
            reporter.error(path, f"question {q_index} must be an object")
            continue
        qid = question.get("id")
        qtype = question.get("type")
        if not isinstance(qid, str) or not qid:
            reporter.error(path, f"question {q_index} missing id")
            continue
        if qid in question_ids:
            reporter.error(path, f"duplicate question id: {qid}")
        question_ids.add(qid)
        if qtype not in ALLOWED_QUESTION_TYPES:
            reporter.error(path, f"question '{qid}' has unsupported type '{qtype}'")
        if not isinstance(question.get("question"), str) or not question.get("question", "").strip():
            reporter.error(path, f"question '{qid}' missing question text")
        answers = question.get("answers")
        if not isinstance(answers, list) or len(answers) < 2:
            reporter.error(path, f"question '{qid}' must have at least 2 answers")
            continue
        answer_ids: set[str] = set()
        if any(isinstance(answer, dict) and "isCorrect" in answer for answer in answers):
            reporter.error(path, f"question '{qid}' uses isCorrect; use correct")
        correct_count = 0
        for answer in answers:
            if not isinstance(answer, dict):
                reporter.error(path, f"question '{qid}' answers must be objects")
                continue
            aid = answer.get("id")
            if not isinstance(aid, str) or not aid:
                reporter.error(path, f"question '{qid}' has answer without id")
            elif aid in answer_ids:
                reporter.error(path, f"question '{qid}' duplicate answer id: {aid}")
            else:
                answer_ids.add(aid)
            if not isinstance(answer.get("text"), str) or not answer.get("text", "").strip():
                reporter.error(path, f"question '{qid}' answer '{aid}' missing text")
            if answer.get("correct") is True:
                correct_count += 1
            if qtype == "MATCHING" and not isinstance(answer.get("matchText"), str):
                reporter.error(path, f"question '{qid}' MATCHING answer '{aid}' missing matchText")
        if qtype == "MULTIPLE_CHOICE" and correct_count != 1:
            reporter.error(path, f"question '{qid}' MULTIPLE_CHOICE needs exactly 1 correct answer, found {correct_count}")
        if qtype == "MULTIPLE_RESPONSE" and correct_count < 1:
            reporter.error(path, f"question '{qid}' MULTIPLE_RESPONSE needs at least 1 correct answer")
    reporter.pass_(path, f"quiz checked with {len(question_ids)} question(s)")


def extract_markdown_refs(text: str) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    for match in re.finditer(r"!\[[^\]]*\]\(([^)]+)\)", text):
        refs.append(("image", match.group(1).strip()))
    for match in re.finditer(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", text):
        refs.append(("link", match.group(1).strip()))
    for match in re.finditer(r":::iframe\s*\n([\s\S]*?)\n:::", text):
        refs.append(("iframe", match.group(1).strip()))
    for match in re.finditer(r":::widget\s+([^\n]+)", text):
        refs.append(("widget", match.group(1).strip()))
    parser = HtmlReferenceParser()
    try:
        parser.feed(text)
    except Exception:
        pass
    refs.extend(parser.refs)
    return refs


def validate_markdown(path: Path, content_root: Path, reporter: Reporter, widgets_dir: Path | None, lesson_context: bool) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        reporter.error(path, f"could not read markdown: {exc}")
        return
    stripped = text.strip()
    if not stripped:
        reporter.error(path, "markdown file is empty")
        return
    if not stripped.startswith("# "):
        reporter.warn(path, "markdown should start with a single H1 heading")
    headings = [line for line in text.splitlines() if re.match(r"^#{1,6}\s+", line)]
    previous = 0
    for heading in headings:
        depth = len(heading.split(" ", 1)[0])
        if previous and depth > previous + 1:
            reporter.warn(path, f"heading level jumps from H{previous} to H{depth}")
        previous = depth
    html_parser = HtmlReferenceParser()
    try:
        html_parser.feed(text)
    except Exception:
        pass
    if lesson_context:
        if html_parser.has_script:
            reporter.warn(path, "inline <script> in lesson markdown will be stripped or unsafe; use widgets/<name>.html")
        if html_parser.has_event_handler:
            reporter.warn(path, "inline event handlers in lesson markdown are not supported reliably; use a widget")
        if html_parser.has_javascript_url:
            reporter.error(path, "javascript: URLs are not supported")
    for ref_type, ref in extract_markdown_refs(text):
        validate_markdown_ref(path, content_root, widgets_dir, ref_type, ref, reporter)
    reporter.pass_(path, "markdown references checked")


def validate_markdown_ref(
    source_file: Path,
    content_root: Path,
    widgets_dir: Path | None,
    ref_type: str,
    raw_ref: str,
    reporter: Reporter,
) -> None:
    ref = raw_ref.strip().strip("<>")
    if not ref or ref.startswith("#"):
        return
    if ref_type == "widget":
        name = ref.split()[0].strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
            reporter.error(source_file, f"widget name is not safe: {name}")
            return
        if widgets_dir is None:
            reporter.warn(source_file, f"widget '{name}' referenced but no widgets/ directory found")
            return
        widget_path = widgets_dir / f"{name}.html"
        if not widget_path.exists():
            reporter.error(source_file, f"widget file not found: widgets/{name}.html")
        else:
            validate_widget(widget_path, reporter)
        return
    lower_ref = ref.lower()
    if lower_ref.startswith(("http://", "https://")):
        if ref_type in {"image", "src", "poster"}:
            reporter.warn(source_file, f"external media reference cannot be validated locally: {ref}")
        return
    if lower_ref.startswith(("data:", "blob:", "mailto:")):
        return
    if lower_ref.startswith("javascript:"):
        reporter.error(source_file, "javascript: URL is not supported")
        return
    if ref.startswith("/api/widgets/"):
        if widgets_dir is None:
            reporter.warn(source_file, f"widget API reference cannot be validated without widgets/: {ref}")
            return
        name = Path(strip_ref_suffix(ref)).name
        if name.endswith(".html"):
            widget_path = widgets_dir / name
            if not widget_path.exists():
                reporter.error(source_file, f"widget file not found: widgets/{name}")
            else:
                validate_widget(widget_path, reporter)
        return
    if ref.startswith("/api/content/") or ref.startswith("/courses/"):
        reporter.warn(source_file, f"absolute content path is harder to move between courses: {ref}")
        return
    resolved = resolve_relative(source_file, ref)
    if resolved is None:
        return
    if not ensure_inside(resolved, content_root):
        reporter.error(source_file, f"local reference escapes content root: {ref}")
        return
    ext = resolved.suffix.lower()
    if ext in SUPPORTED_LOCAL_EXTS or ref_type in {"image", "src", "poster", "href", "link", "iframe"}:
        if not resolved.exists():
            reporter.error(source_file, f"referenced local file not found: {ref}")
        elif ext == ".html":
            reporter.warn(source_file, f"local HTML reference found; prefer widgets/<name>.html plus :::widget for interactive artifacts: {ref}")


def validate_widget(path: Path, reporter: Reporter) -> None:
    resolved = path.resolve()
    if resolved in reporter._validated_widgets:
        return
    reporter._validated_widgets.add(resolved)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        reporter.error(path, f"could not read widget: {exc}")
        return
    lower = text.lower()
    if "widget-ready" not in lower:
        reporter.error(path, "widget should post a widget-ready message")
    if "widget-resize" not in lower:
        reporter.warn(path, "widget should post widget-resize with its rendered height")
    if "<script" not in lower:
        reporter.warn(path, "widget has no script; use lesson markdown or plain HTML if no interactivity is needed")
    reporter.pass_(path, "widget HTML checked")


def check_orphaned_module_files(module_dir: Path, referenced: set[Path], reporter: Reporter) -> None:
    for child in module_dir.iterdir():
        if child.name == "manifest.json" or child.name == "assets" or child.is_dir():
            continue
        if child.suffix.lower() in {".md", ".json"} and child.resolve() not in referenced:
            reporter.warn(child, "file is not referenced by module manifest")


def validate_legacy_course(course_dir: Path, reporter: Reporter, widgets_dir: Path | None) -> None:
    manifest_path = course_dir / "manifest.json"
    data = read_json(manifest_path, reporter)
    if not isinstance(data, dict):
        return
    reporter.record(f"legacy-course:{course_dir.name}")
    validate_required_string(data, "id", manifest_path, reporter)
    validate_required_string(data, "title", manifest_path, reporter)
    modules = data.get("modules")
    if not isinstance(modules, list) or not modules:
        reporter.error(manifest_path, "legacy manifest modules must be a non-empty array")
        return
    course_id = data.get("id", course_dir.name)
    lesson_ids: set[str] = set()
    for module in modules:
        if not isinstance(module, dict):
            reporter.error(manifest_path, "legacy module entries must be objects")
            continue
        module_id = module.get("id")
        lessons = module.get("lessons")
        if not isinstance(module_id, str) or not module_id:
            reporter.error(manifest_path, "legacy module missing id")
            continue
        if not isinstance(lessons, list) or not lessons:
            reporter.warn(manifest_path, f"legacy module '{module_id}' has no lessons")
            continue
        for lesson in lessons:
            if not isinstance(lesson, dict):
                reporter.error(manifest_path, f"legacy module '{module_id}' lesson must be an object")
                continue
            lesson_id = lesson.get("id")
            lesson_type = lesson.get("type")
            if not isinstance(lesson_id, str) or not lesson_id:
                reporter.error(manifest_path, f"legacy module '{module_id}' lesson missing id")
                continue
            if lesson_id in lesson_ids:
                reporter.error(manifest_path, f"duplicate lesson id: {lesson_id}")
            lesson_ids.add(lesson_id)
            if "|||" not in lesson_id:
                reporter.warn(manifest_path, f"legacy lesson id '{lesson_id}' should use module|||lesson format")
            if lesson_type == "content":
                rel = lesson.get("markdownPath")
                if not isinstance(rel, str) or not rel:
                    reporter.error(manifest_path, f"content lesson '{lesson_id}' missing markdownPath")
                    continue
                local_rel = rel.replace(f"/courses/{course_id}/", "").lstrip("/")
                full = safe_resolve(course_dir, local_rel)
                if full is None or not ensure_inside(full, course_dir):
                    reporter.error(manifest_path, f"markdownPath is not course-relative: {rel}")
                    continue
                if not full.exists():
                    reporter.error(manifest_path, f"markdownPath file not found: {rel}")
                else:
                    validate_markdown(full, course_dir, reporter, widgets_dir, lesson_context=True)
            elif lesson_type == "quiz":
                rel = lesson.get("quizPath")
                if not isinstance(rel, str) or not rel:
                    reporter.error(manifest_path, f"quiz lesson '{lesson_id}' missing quizPath")
                    continue
                local_rel = rel.replace(f"/courses/{course_id}/", "").lstrip("/")
                full = safe_resolve(course_dir, local_rel)
                if full is None or not ensure_inside(full, course_dir):
                    reporter.error(manifest_path, f"quizPath is not course-relative: {rel}")
                    continue
                if not full.exists():
                    reporter.error(manifest_path, f"quizPath file not found: {rel}")
                else:
                    validate_quiz(full, reporter)
            elif lesson_type not in ALLOWED_LESSON_TYPES:
                reporter.error(manifest_path, f"lesson '{lesson_id}' has unsupported type '{lesson_type}'")
    reporter.pass_(manifest_path, f"legacy manifest checked with {len(lesson_ids)} lesson(s)")


def validate_target(path: Path, strict: bool = False) -> Reporter:
    reporter = Reporter()
    target = path.expanduser().resolve()
    if not target.exists():
        reporter.error(target, "path not found")
        return reporter
    if not target.is_dir():
        reporter.error(target, "path must be a directory")
        return reporter
    content_root = find_content_root(target)
    widgets_dir = content_root / "widgets" if (content_root / "widgets").is_dir() else None

    if (target / "courses").is_dir() or (target / "modules").is_dir():
        if (target / "modules").is_dir():
            for module_dir in sorted((target / "modules").iterdir()):
                if module_dir.is_dir():
                    validate_module(module_dir, target, reporter, widgets_dir)
        if (target / "courses").is_dir():
            for course_dir in sorted((target / "courses").iterdir()):
                if not course_dir.is_dir():
                    continue
                detected = False
                if (course_dir / "course.json").exists():
                    detected = True
                    validate_course_json(course_dir, target, reporter, widgets_dir)
                if (course_dir / "blueprint.json").exists():
                    detected = True
                    validate_blueprint(course_dir, target, reporter, widgets_dir)
                if (course_dir / "manifest.json").exists() and not detected:
                    detected = True
                    validate_legacy_course(course_dir, reporter, widgets_dir)
                if not detected:
                    reporter.error(course_dir, "course directory needs course.json, blueprint.json, or legacy manifest.json")
    elif (target / "course.json").exists():
        module_ids = validate_course_json(target, content_root, reporter, widgets_dir)
        validate_referenced_modules(module_ids, content_root, reporter, widgets_dir)
    elif (target / "blueprint.json").exists():
        module_ids = validate_blueprint(target, content_root, reporter, widgets_dir)
        validate_referenced_modules(module_ids, content_root, reporter, widgets_dir)
    elif (target / "manifest.json").exists():
        validate_module(target, content_root, reporter, widgets_dir)
    else:
        reporter.error(target, "could not detect CourseViewerPlatform content format")

    if strict:
        pass
    return reporter


def outline() -> dict[str, Any]:
    return {
        "recommended_structure": [
            "courses/<course-id>/course.json",
            "courses/<course-id>/welcome.md",
            "courses/<course-id>/assets/cover.png",
            "modules/<module-id>/manifest.json",
            "modules/<module-id>/<lesson-id>.md",
            "modules/<module-id>/quiz.json",
            "modules/<module-id>/assets/<image-or-video>",
            "widgets/<widget-name>.html",
        ],
        "course_files": ["course.json", "blueprint.json for electives", "legacy manifest.json only for older monolithic courses"],
        "lesson_types": sorted(ALLOWED_LESSON_TYPES),
        "quiz_question_types": sorted(ALLOWED_QUESTION_TYPES),
        "media": {
            "images": sorted(IMAGE_EXTS),
            "video": sorted(VIDEO_EXTS),
            "audio": sorted(AUDIO_EXTS),
            "documents": sorted(DOCUMENT_EXTS),
            "html_widgets": "widgets/<name>.html referenced with :::widget name",
        },
        "validation_command": "python3 skills/colab-course-publisher/scripts/cli.py validate <path>",
        "single_course_validation": "Validating courses/<course-id> also validates referenced module manifests, lessons, quizzes, assets, and widgets.",
    }


def print_outline(json_output: bool) -> None:
    data = outline()
    if json_output:
        print(json.dumps(data, indent=2))
        return
    print("CourseViewerPlatform recommended structure:")
    for item in data["recommended_structure"]:
        print(f"  - {item}")
    print()
    print("Create courses with course.json or blueprint.json, modules with manifest.json, markdown lessons, quiz.json, assets/, and widgets/<name>.html for interactive HTML.")
    print(f"Validate with: {data['validation_command']}")
    print(data["single_course_validation"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create outlines and validate CourseViewerPlatform course content.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    outline_parser = subparsers.add_parser("outline", help="print the supported course structure")
    outline_parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    validate_parser = subparsers.add_parser("validate", help="validate a course, module, or content root")
    validate_parser.add_argument("path", help="path to content root, course directory, or module directory")
    validate_parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    validate_parser.add_argument("--strict", action="store_true", help="treat warnings as failures")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "outline":
        print_outline(args.json)
        return 0
    if args.command == "validate":
        reporter = validate_target(Path(args.path), strict=args.strict)
        result = reporter.to_json(strict=args.strict)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            reporter.print_human(strict=args.strict)
        return 0 if result["ok"] else 1
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    sys.exit(main())
