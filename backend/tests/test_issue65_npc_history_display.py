"""Issue #65 - 대화 기록의 RAG 내부 메타데이터 비노출 회귀 테스트."""

from crimescene.chat.npc_history_display import render_stored_npc_message
from crimescene.retriever.npc_response_gate import FALLBACK_REPLY

HEADER = "제가 확인한 자료에는 이렇게 나와 있어요."


def test_saved_quote_is_shown_as_plain_npc_speech():
    raw = (
        f"{HEADER}\n"
        "“저녁 8시 조금 넘어서 기범 씨와 학교 운영을 상의했습니다.” "
        "(근거: K-C01-01)\n"
        "“20시 2분 본관에 들어갔고 20시 28분에 나왔습니다.” "
        "(근거: K-C01-02)"
    )
    rendered = render_stored_npc_message(raw, ("K-C01-01", "K-C01-02"))

    assert rendered == (
        "저녁 8시 조금 넘어서 기범 씨와 학교 운영을 상의했습니다.\n"
        "20시 2분 본관에 들어갔고 20시 28분에 나왔습니다."
    )
    assert "제가 확인한 자료에는" not in rendered
    assert "근거:" not in rendered
    assert "K-C01" not in rendered


def test_duplicate_source_id_is_allowed_when_consistent():
    raw = (
        f"{HEADER}\n"
        "“제가 먼저 회의를 마쳤습니다.” (근거: K-C01-01)\n"
        "“언쟁은 없었습니다.” (근거: K-C01-01)"
    )
    rendered = render_stored_npc_message(raw, ("K-C01-01",))
    assert rendered == "제가 먼저 회의를 마쳤습니다.\n언쟁은 없었습니다."


def test_source_mismatch_fails_closed():
    raw = f"{HEADER}\n“확인한 사실입니다.” (근거: K-C01-01)"
    assert render_stored_npc_message(raw, ("K-C01-02",)) == FALLBACK_REPLY


def test_malformed_quote_fails_closed():
    raw = f"{HEADER}\n비공개 정보 (근거: K-C01-01)"
    assert render_stored_npc_message(raw, ("K-C01-01",)) == FALLBACK_REPLY


def test_safe_social_message_kept():
    text = "안녕하세요. 무슨 일로 찾아오셨나요?"
    assert render_stored_npc_message(text, ()) == text


def test_unverified_metadata_is_not_shown():
    raw = "검증하지 않은 정보입니다. (근거: INTERNAL-SECRET)"
    assert render_stored_npc_message(raw, ()) == FALLBACK_REPLY


def test_missing_message_fails_closed():
    assert render_stored_npc_message("", ()) == FALLBACK_REPLY
