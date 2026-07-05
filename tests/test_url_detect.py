from second_brain.processors.url import detect_url_type, is_probable_url, normalize_url
from second_brain.processors.url.youtube import video_id


def test_detect_url_type():
    assert detect_url_type("https://x.com/user/status/123") == "twitter"
    assert detect_url_type("https://twitter.com/user/status/123") == "twitter"
    assert detect_url_type("https://www.youtube.com/watch?v=abc123def45") == "youtube"
    assert detect_url_type("https://youtu.be/abc123def45") == "youtube"
    assert detect_url_type("https://www.linkedin.com/posts/foo") == "linkedin"
    assert detect_url_type("https://es.linkedin.com/in/foo") == "linkedin"
    assert detect_url_type("https://example.com/articulo") == "web"


def test_is_probable_url():
    assert is_probable_url("https://example.com")
    assert is_probable_url("  www.example.com  ")
    assert not is_probable_url("mira esto https://example.com")
    assert not is_probable_url("una nota cualquiera")


def test_normalize_url():
    assert normalize_url("www.example.com") == "https://www.example.com"
    assert normalize_url("https://example.com") == "https://example.com"


def test_youtube_video_id():
    assert video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert video_id("https://www.youtube.com/") is None
