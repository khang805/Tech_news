from newsintel.text_utils import article_id, clean_html, normalize_link, split_sentences, trim


def test_normalize_link_strips_tracking_www_and_trailing_slash():
    assert normalize_link("https://WWW.Example.com/post/?utm_source=x&id=2#top") == "https://example.com/post?id=2"


def test_article_id_matches_for_tracking_variants():
    assert article_id("https://example.com/a?utm_medium=rss") == article_id("https://example.com/a/")


def test_clean_html_removes_scripts_styles_and_tags():
    raw = "<p>Hello <b>world</b></p><script>alert(1)</script><style>p{}</style>"
    assert clean_html(raw) == "Hello world"


def test_split_sentences():
    assert split_sentences("First sentence here. Second one! Third? Yes.") == [
        "First sentence here.", "Second one!", "Third?", "Yes.",
    ]


def test_trim_adds_ellipsis():
    assert trim("abcdef", 4) == "abc..."
