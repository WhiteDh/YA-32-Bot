"""Click through every screen as the owner: nothing may end in «😵 Щось пішло не так»."""

from __future__ import annotations

import logging

import pytest
from aiogram import Bot, Dispatcher
from aiogram.filters.callback_data import CallbackData

from tests.conftest import NOW, OWNER_ID, STUDENT_ID, FakeSession
from tests.test_bot import cb, feed, msg
from ya32_bot.app import build_dispatcher
from ya32_bot.bot import ui
from ya32_bot.bot.context import AppContext
from ya32_bot.bot.keyboards.callbacks import Adm, CalCb, HwCb, LessonCb, Nav, SetCb, WeekCb, d2i
from ya32_bot.db.models import Holiday, Homework, Subject, TemplateLesson

D = d2i(NOW.date())
Y, M = NOW.year, NOW.month


@pytest.fixture
def dp(seeded: AppContext) -> Dispatcher:
    ui.RICH.enabled = True
    return build_dispatcher(seeded)


def _no_errors(fake_session: FakeSession, caplog: pytest.LogCaptureFixture) -> None:
    texts = fake_session.texts() + [str(getattr(c, "text", "") or "") for c in fake_session.of("AnswerCallbackQuery")]
    broken = [t for t in texts if "😵" in t]
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert not broken and not errors, (broken, [r.getMessage() for r in errors])


STUDENT_CLICKS = [
    Nav(to="menu"), Nav(to="today"), Nav(to="tomorrow"), Nav(to="week"), Nav(to="nextweek"), Nav(to="now"),
    Nav(to="help"), Nav(to="settings"), Nav(to="ics"), WeekCb(d=D), LessonCb(d=D, s=1), CalCb(p="view", y=Y, m=M),
    CalCb(p="view", y=Y, m=M, d=7), HwCb(a="list"), HwCb(a="list", s=1),
    SetCb(a="open", k="view"), SetCb(a="open", k="notify"), SetCb(a="open", k="presets"), SetCb(a="open", k="other"),
    SetCb(a="tog", k="compact", v="view"), SetCb(a="preset", v="full"), SetCb(a="time", k="morning_time"),
    SetCb(a="time", k="morning_time", v="8"), SetCb(a="timeset", k="morning_time", v="0815"), SetCb(a="remind"),
    SetCb(a="remindset", v="15"), SetCb(a="preview"), SetCb(a="tog", k="reply_keyboard", v="other"),
]  # fmt: skip


STUDENT_MESSAGES = [
    "/start", "/today", "/tomorrow", "/week", "/nextweek", "/now", "/day 12.10", "/day", "/hw", "/settings",
    "/help", "/menu", "/avatar", "кава", "/42", "/secrets", "/cancel", "щось незрозуміле", "/search аналіз",
    "/search", "/ics", "економічна",
]  # fmt: skip


async def test_student_walkthrough(dp, bot: Bot, fake_session: FakeSession, caplog):
    for text in STUDENT_MESSAGES:
        await feed(dp, bot, msg(STUDENT_ID, text))
    for data in STUDENT_CLICKS:
        await feed(dp, bot, cb(STUDENT_ID, data.pack()))
    _no_errors(fake_session, caplog)


ADMIN_CLICKS = [
    Adm(a="menu"), Adm(a="pickday"), CalCb(p="edit", y=Y, m=M), CalCb(p="edit", y=Y, m=M, d=5), Adm(a="day", d=D),
    Adm(a="slot", d=D, s=1), Adm(a="kindpick", d=D, s=1), Adm(a="kind", d=D, s=1, v="lab"), Adm(a="cancel", d=D, s=1),
    Adm(a="restore", d=D, s=1), Adm(a="add", d=D, s=6), Adm(a="addsubj", d=D, s=6, id=0), Adm(a="move", d=D, s=6),
    CalCb(p="move", y=Y, m=M, x=D * 10 + 6), CalCb(p="move", y=Y, m=M, d=6, x=D * 10 + 6),
    Adm(a="moveto", d=d2i(NOW.date().replace(day=6)), s=1, id=D * 10 + 6),
    Adm(a="tpl"), Adm(a="tplw", s=1), Adm(a="tpld", s=1, d=0), Adm(a="tplr", id=1), Adm(a="tplkp", id=1),
    Adm(a="tplk", id=1, v="prac"), Adm(a="tplsp", id=1), Adm(a="tpls", id=1, s=5), Adm(a="tplev", id=1),
    Adm(a="tpladd", s=1, d=5), Adm(a="tpladds", s=1, d=5, id=2), Adm(a="tpladdn", s=1, d=5, id=2, v="0"),
    Adm(a="sync"), Adm(a="sychk"), Adm(a="syauto", v="apply"), Adm(a="syrel"), Adm(a="sysem"),
    Adm(a="syapp", v="update"),
    Adm(a="sem"), Adm(a="semflip"), CalCb(p="sem_s", y=Y, m=M), CalCb(p="sem_e", y=Y, m=12, d=31),
    CalCb(p="hol_s", y=Y, m=M, d=14),
    Adm(a="subj"), Adm(a="subjo", id=1),
    Adm(a="stats"), Adm(a="log"), Adm(a="undo", id=3), Adm(a="people"), Adm(a="who", id=STUDENT_ID),
    Adm(a="role", id=STUDENT_ID, v="editor"), Adm(a="inv"), Adm(a="invmk", v="editor"),
    HwCb(a="new"), CalCb(p="hw", y=Y, m=M, d=6), HwCb(a="add", d=D),
    HwCb(a="subj", d=d2i(NOW.date().replace(day=11)), id=0),
    HwCb(a="list"),
]  # fmt: skip


async def test_admin_walkthrough_with_text_inputs(dp, bot: Bot, fake_session: FakeSession, seeded: AppContext, caplog):
    await feed(dp, bot, msg(STUDENT_ID, "/start"))
    await feed(dp, bot, msg(OWNER_ID, "/start"))
    await feed(dp, bot, msg(OWNER_ID, "/admin"))
    for data in ADMIN_CLICKS:
        await feed(dp, bot, cb(OWNER_ID, data.pack()))
    await feed(dp, bot, msg(OWNER_ID, "/cancel"))

    # Text inputs: every FSM prompt followed by an answer.
    steps: list[tuple[CallbackData, str]] = [
        (Adm(a="field", d=D, s=2, v="teacher"), "Іваненко І. І."),
        (Adm(a="field", d=D, s=2, v="note"), "-"),
        (Adm(a="addtext", d=D, s=7), "Факультатив"),
        (Adm(a="tplf", id=2, v="room"), "17-101"),
        (Adm(a="tpladdt", s=2, d=5, id=3), "Новий предмет"),
        (Adm(a="subjf", id=1, v="link"), "https://meet.google.com/abc-defg-hij"),
        (Adm(a="subjf", id=1, v="short"), "Інвест"),
        (Adm(a="bc"), "Завтра пари онлайн"),
    ]
    for data, answer in steps:
        await feed(dp, bot, cb(OWNER_ID, data.pack()))
        await feed(dp, bot, msg(OWNER_ID, answer))
    await feed(dp, bot, cb(OWNER_ID, CalCb(p="hol_s", y=Y, m=M, d=14).pack()))
    await feed(dp, bot, cb(OWNER_ID, CalCb(p="hol_e", y=Y, m=M, d=16, x=d2i(NOW.date().replace(day=14))).pack()))
    await feed(dp, bot, msg(OWNER_ID, "Осінні"))

    await feed(dp, bot, cb(OWNER_ID, HwCb(a="pick", d=D, s=3).pack()))
    await feed(dp, bot, msg(OWNER_ID, "Прочитати розділ 2"))
    await feed(dp, bot, cb(OWNER_ID, "hw_due"))
    await feed(dp, bot, cb(OWNER_ID, CalCb(p="hw", y=Y, m=M, d=9, x=1).pack()))
    await feed(dp, bot, cb(OWNER_ID, "hw_save"))
    for data in (HwCb(a="open", id=1), HwCb(a="done", id=1), HwCb(a="edit", id=1)):
        await feed(dp, bot, cb(OWNER_ID, data.pack()))
    await feed(dp, bot, msg(OWNER_ID, "Прочитати розділи 2–3"))
    for data in (HwCb(a="del", id=1), HwCb(a="delok", id=1)):
        await feed(dp, bot, cb(OWNER_ID, data.pack()))

    _no_errors(fake_session, caplog)
    async with seeded.db.session() as session:
        subject = await session.get(Subject, 1)
        room_row = await session.get(TemplateLesson, 2)
        holidays = await session.get(Holiday, 1)
        hw = await session.get(Homework, 1)
    assert subject is not None and subject.link and subject.short == "Інвест"
    assert room_row is not None and room_row.room == "17-101"
    assert holidays is not None and holidays.title == "Осінні"
    assert hw is None  # deleted at the end
