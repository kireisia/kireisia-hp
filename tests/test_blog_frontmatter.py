"""
ブログ記事の読み込みの不具合修正テスト（2026-11-01）
1) CMSが改行入りの文章を `lead: |-` 形式で保存すると「|-」だけ表示されていた
2) slug の前後に空白が入るとURLに %20 が混ざっていた
対象: deploy_hp/build_blog.py の parse_front_matter / format_lead_html / clean_slug
"""

import os
import sys

import pytest

DEPLOY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.abspath(DEPLOY_DIR))

import build_blog  # noqa: E402


def fm(*lines):
    return "\n".join(["---", *lines, "---", "本文"])


# ---- 改行入りの値（YAMLのブロック形式） ----


def test_改行を保つ形式_縦棒ハイフン():
    meta, body = build_blog.parse_front_matter(
        fm("lead: |-", "  1段落目です。", "", "  2段落目です。", "published: true")
    )
    assert meta["lead"] == "1段落目です。\n\n2段落目です。"
    assert meta["published"] == "true"
    assert body == "本文"


def test_改行を保つ形式_縦棒のみ():
    meta, _ = build_blog.parse_front_matter(fm("lead: |", "  1行目", "  2行目"))
    assert meta["lead"] == "1行目\n2行目"


def test_折りたたむ形式():
    meta, _ = build_blog.parse_front_matter(fm("lead: >-", "  1行目", "  2行目"))
    assert meta["lead"] == "1行目 2行目"


def test_ブロックの中のコロンをキーと誤認しない():
    meta, _ = build_blog.parse_front_matter(
        fm("lead: |-", "  料金: 1万円から", "date: 2026-11-01")
    )
    assert meta["lead"] == "料金: 1万円から"
    assert meta["date"] == "2026-11-01"
    assert "料金" not in meta


def test_今までの1行形式はそのまま():
    meta, _ = build_blog.parse_front_matter(fm('title: "タイトル"', "slug: abc"))
    assert meta["title"] == "タイトル"
    assert meta["slug"] == "abc"


def test_ブロックが空でも落ちない():
    meta, _ = build_blog.parse_front_matter(fm("lead: |-", "date: 2026-11-01"))
    assert meta["lead"] == ""
    assert meta["date"] == "2026-11-01"


# ---- リードの表示（段落・改行・無害化） ----


def test_リードの改行はbrになる():
    out = build_blog.format_lead_html("1段落目\n\n2段落目\n3行目")
    assert out == "1段落目<br><br>2段落目<br>3行目"


def test_リードは無害化される():
    assert "<script>" not in build_blog.format_lead_html("<script>x</script>")


# ---- slug の空白 ----


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("    aircon-cleaning-price-guide", "aircon-cleaning-price-guide"),
        ("abc  ", "abc"),
        ("abc", "abc"),
        ("\tabc　", "abc"),
    ],
)
def test_slugの前後の空白を取る(raw, expected):
    assert build_blog.clean_slug(raw) == expected


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
