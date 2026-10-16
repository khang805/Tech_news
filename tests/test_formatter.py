from newsintel.formatter import INSUFFICIENT_OVERVIEW, build_text_fields


def test_insufficient_content_is_not_invented():
    f = build_text_fields("Short text only.")
    assert f["content_status"] == "insufficient"
    assert f["overview"] == INSUFFICIENT_OVERVIEW
    assert f["explanation"] == ""


def test_partial_and_full_thresholds():
    assert build_text_fields(" ".join(["word"] * 14) + ".")["content_status"] == "insufficient"
    assert build_text_fields(" ".join(["word"] * 15) + ".")["content_status"] == "partial"
    assert build_text_fields(" ".join(["word"] * 60) + ".")["content_status"] == "full"


def test_overview_is_one_line_and_explanation_is_one_paragraph():
    sentences = [f"Sentence number {i} describes the release in detail." for i in range(1, 12)]
    f = build_text_fields(" ".join(sentences))
    assert f["overview"] == sentences[0]
    assert "\n" not in f["overview"]
    assert f["explanation"].startswith("Sentence number 2")
    assert "\n" not in f["explanation"]
    assert f["explanation"].count("Sentence number") == 6
