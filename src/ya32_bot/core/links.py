"""Meet / Zoom links for the current semester, taken from the group's list of teachers.

Keyed by the subject name exactly as schedule.kpi.ua returns it. When one subject has
different teachers for lectures and practice, the entry also names the teacher's surname.
These win over ``Subject.link`` set in the admin panel, which stays as a fallback.
"""

from __future__ import annotations

LINKS: tuple[tuple[str, str | None, str], ...] = (
    ("Інвестиційний аналіз", None, "https://meet.google.com/jmj-epwq-ajn"),
    ("Аналітика та реінжиніринг бізнес-процесів", None, "https://meet.google.com/oyd-hjyo-pss"),
    ("Економічна аналітика", None,
     "https://us05web.zoom.us/j/85196340989?pwd=Z3pWemVBbHljYUdBSHI0SWJ1b0pIdz09"),
    ("Інтелектуальний аналіз економічних даних", None,
     "https://us04web.zoom.us/j/9474157499?pwd=d3NzcEdTR0JlNUpYb2tvSjhkcE9qUT09"),
    ("Експериментальна та поведінкова економіка", "Капустян",
     "https://us04web.zoom.us/j/71659028840?pwd=SXlVUWs2a29pM1RKL3daeHFSMFZKZz09"),
    ("Експериментальна та поведінкова економіка", "Черноусова",
     "https://us04web.zoom.us/j/9026286574?pwd=dCtmd2VxL2Ywc3Rwa1l2emFyRjQ2Zz09"),
    ("Штучний інтелект в економічних процесах", None,
     "https://us04web.zoom.us/j/6534222097?pwd=8ScGLLLEbsPXENhXGMYSPvuQtb7H0a.1"),
    ("Електронна комерція", None,
     "https://us05web.zoom.us/j/4222512662?pwd=KzJpTlIvM0RzcXhBSUNJc3ZodWY3UT09"),
    ("Вебскрейпінг та аналіз соціальних мереж", None,
     "https://us02web.zoom.us/j/3043235346?pwd=diqJkVLsZKLS0LZPCndmlAvtGATTFS.1"),
    ("Практичний курс іноземної мови професійного спрямування. Частина 2", None,
     "https://us04web.zoom.us/launch/jc/73130973568"),
)  # fmt: skip


def _norm(text: str) -> str:
    return " ".join(text.casefold().split())


def link_for(subject: str, teacher: str | None) -> str | None:
    """The lesson's own link: a teacher-specific entry first, then the subject-wide one."""
    name = _norm(subject)
    who = _norm(teacher or "")
    fallback: str | None = None
    for subj, surname, url in LINKS:
        if _norm(subj) != name:
            continue
        if surname is None:
            fallback = fallback or url
        elif _norm(surname) in who:
            return url
    return fallback
