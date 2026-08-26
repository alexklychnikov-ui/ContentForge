from app.services.adapters.gmail import build_email_message, with_recipient_greeting


def test_with_recipient_greeting_named() -> None:
    assert with_recipient_greeting("Текст письма", "Анна").startswith("Привет, Анна!\n\n")


def test_with_recipient_greeting_no_name() -> None:
    assert with_recipient_greeting("Текст", None).startswith("Привет!\n\n")
    assert with_recipient_greeting("Текст", "  ").startswith("Привет!\n\n")


def test_with_recipient_greeting_replaces_existing() -> None:
    body = "Привет, друг!\n\nОсновной текст"
    out = with_recipient_greeting(body, "Игорь")
    assert out.startswith("Привет, Игорь!\n\n")
    assert "друг" not in out
    assert "Основной текст" in out
    assert out.count("Привет") == 1


def test_build_email_message_personalizes_plain_body() -> None:
    msg = build_email_message(
        "from@example.com",
        "to@example.com",
        {"subject": "Тема", "body_markdown": "Новости недели"},
        recipient_name="Мария",
    )
    plain = msg.get_body(preferencelist=("plain",)).get_content()
    assert plain.startswith("Привет, Мария!")
