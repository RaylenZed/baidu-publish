from app.utils.cover import build_cover_keywords
from app.services.bjh_service import _normalize_cover_url


def test_build_cover_keywords_prioritizes_product_and_topic():
    keywords = build_cover_keywords(
        title="论文润色五大实战技巧：从结构混乱到逻辑严密",
        category="图书教育",
        topic_keyword="论文写作",
        product_name="写作书单",
    )

    assert keywords[0] == "写作书单"
    assert "论文写作" in keywords
    assert "图书教育论文写作" in keywords


def test_build_cover_keywords_adds_category_visual_fallbacks():
    keywords = build_cover_keywords(
        title="那些提升效率的方法",
        category="图书教育",
    )

    assert "图书教育" in keywords
    assert "读书" in keywords
    assert "学习" in keywords


def test_build_cover_keywords_deduplicates_and_cleans_title_parts():
    keywords = build_cover_keywords(
        title="《读书方法》：读书方法，真的能改变表达吗？",
        category="图书教育",
    )

    assert keywords.count("读书方法") == 1
    assert all("《" not in keyword and "》" not in keyword for keyword in keywords)


def test_normalize_cover_url_upgrades_http_to_https():
    assert (
        _normalize_cover_url("http://baijiahao.baidu.com/bjh/picproxy?param=abc")
        == "https://baijiahao.baidu.com/bjh/picproxy?param=abc"
    )
