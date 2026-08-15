"""Test doubles: a fake Telegram session and synthetic update builders."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import (
    AnswerCallbackQuery,
    EditMessageText,
    SendMessage,
    SendPhoto,
    SetMyCommands,
    TelegramMethod,
)
from aiogram.types import CallbackQuery, Chat, Message, PhotoSize, Update
from aiogram.types import User as TelegramUser

_TEXT_METHODS = (SendMessage, EditMessageText, SendPhoto)
_FIXED_DATE = datetime(2026, 1, 1)


class FakeSession(BaseSession):
    """Records outgoing API calls instead of contacting Telegram."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []

    async def close(self) -> None:  # pragma: no cover - nothing to close
        return None

    async def stream_content(self, *args: Any, **kwargs: Any):  # pragma: no cover
        raise NotImplementedError

    async def make_request(
        self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None
    ) -> Any:
        self.calls.append(method)
        if isinstance(method, _TEXT_METHODS):
            chat_id = int(getattr(method, "chat_id", 0) or 0)
            return Message(
                message_id=len(self.calls),
                date=_FIXED_DATE,
                chat=Chat(id=chat_id, type="private"),
                text=getattr(method, "text", None) or getattr(method, "caption", None),
            )
        if isinstance(method, (AnswerCallbackQuery, SetMyCommands)):
            return True
        return True

    # ------------------------------------------------------------ assertions
    def texts(self, chat_id: int | None = None) -> list[str]:
        """Bodies of every message sent or edited, optionally per chat."""
        result: list[str] = []
        for call in self.calls:
            if not isinstance(call, _TEXT_METHODS):
                continue
            if chat_id is not None and int(getattr(call, "chat_id", 0) or 0) != chat_id:
                continue
            body = getattr(call, "text", None) or getattr(call, "caption", None)
            if body:
                result.append(body)
        return result

    def last_text(self, chat_id: int | None = None) -> str:
        texts = self.texts(chat_id)
        assert texts, f"no message was sent to {chat_id}"
        return texts[-1]

    def button_labels(self, chat_id: int | None = None) -> list[str]:
        labels: list[str] = []
        for markup in self._markups(chat_id):
            for row in markup.inline_keyboard:
                labels.extend(button.text for button in row)
        return labels

    def callbacks(self, chat_id: int | None = None) -> list[str]:
        data: list[str] = []
        for markup in self._markups(chat_id):
            for row in markup.inline_keyboard:
                data.extend(
                    button.callback_data for button in row if button.callback_data
                )
        return data

    def find_callback(self, pattern: str, chat_id: int | None = None) -> str:
        matches = [item for item in self.callbacks(chat_id) if re.match(pattern, item)]
        assert matches, f"no callback matching {pattern!r} in {self.callbacks(chat_id)}"
        return matches[-1]

    def alerts(self, chat_id: int | None = None) -> list[str]:
        """Texts shown via ``answerCallbackQuery`` popups."""
        return [
            call.text or ""
            for call in self.calls
            if isinstance(call, AnswerCallbackQuery) and call.text
        ]

    def answered_callbacks(self) -> list[AnswerCallbackQuery]:
        return [call for call in self.calls if isinstance(call, AnswerCallbackQuery)]

    def clear(self) -> None:
        self.calls.clear()

    def _markups(self, chat_id: int | None):
        for call in self.calls:
            if not isinstance(call, _TEXT_METHODS):
                continue
            if chat_id is not None and int(getattr(call, "chat_id", 0) or 0) != chat_id:
                continue
            markup = getattr(call, "reply_markup", None)
            if markup is not None and getattr(markup, "inline_keyboard", None):
                yield markup


def telegram_user(user_id: int, name: str = "Tester") -> TelegramUser:
    return TelegramUser(
        id=user_id, is_bot=False, first_name=name, username=f"user{user_id}"
    )


def message_update(text: str, user_id: int, update_id: int = 1) -> Update:
    return Update(
        update_id=update_id,
        message=Message(
            message_id=update_id,
            date=_FIXED_DATE,
            chat=Chat(id=user_id, type="private"),
            from_user=telegram_user(user_id),
            text=text,
        ),
    )


def photo_update(
    user_id: int, caption: str | None = None, update_id: int = 1
) -> Update:
    return Update(
        update_id=update_id,
        message=Message(
            message_id=update_id,
            date=_FIXED_DATE,
            chat=Chat(id=user_id, type="private"),
            from_user=telegram_user(user_id),
            caption=caption,
            photo=[
                PhotoSize(
                    file_id="proof-file-id",
                    file_unique_id="proof-unique",
                    width=100,
                    height=100,
                )
            ],
        ),
    )


def press_update(data: str, user_id: int, update_id: int = 99) -> Update:
    return Update(
        update_id=update_id,
        callback_query=CallbackQuery(
            id=str(update_id),
            from_user=telegram_user(user_id),
            chat_instance="chat-instance",
            data=data,
            message=Message(
                message_id=update_id,
                date=_FIXED_DATE,
                chat=Chat(id=user_id, type="private"),
                text="previous screen",
            ),
        ),
    )
