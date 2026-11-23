"""
ブログのカテゴリをCMS（content/blog-categories/）から読む仕組みのテスト。
対象: deploy_hp/build_blog.py の load_categories / visible_categories / render_filter_buttons
作成: 2026-11-01
"""

import json
import os
import sys

import pytest

DEPLOY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.abspath(DEPLOY_DIR))

import build_blog  # noqa: E402


def write_cat(folder, file_name, data):
    with open(os.path.join(folder, file_name), "w", encoding="utf-8") as f:
        if isinstance(data, str):
            f.write(data)
        else:
            json.dump(data, f, ensure_ascii=False)


# ---- load_categories ----


def test_順番どおりに読める(tmp_path):
    write_cat(tmp_path, "b.json", {"name": "キッチン", "order": 2})
    write_cat(tmp_path, "a.json", {"name": "エアコン", "order": 1})
    write_cat(tmp_path, "c.json", {"name": "洗濯機", "order": 3})
    assert build_blog.load_categories(str(tmp_path)) == [
        "エアコン",
        "キッチン",
        "洗濯機",
    ]


def test_順番が空なら最後に回る(tmp_path):
    write_cat(tmp_path, "a.json", {"name": "洗濯機"})
    write_cat(tmp_path, "b.json", {"name": "エアコン", "order": 1})
    assert build_blog.load_categories(str(tmp_path)) == ["エアコン", "洗濯機"]


def test_同じ名前は1つにまとめる(tmp_path):
    write_cat(tmp_path, "a.json", {"name": "エアコン", "order": 1})
    write_cat(tmp_path, "b.json", {"name": " エアコン ", "order": 5})
    assert build_blog.load_categories(str(tmp_path)) == ["エアコン"]


def test_壊れたファイルと名前なしは飛ばす(tmp_path):
    write_cat(tmp_path, "a.json", {"name": "エアコン", "order": 1})
    write_cat(tmp_path, "broken.json", "{ これはJSONではない")
    write_cat(tmp_path, "noname.json", {"order": 2})
    write_cat(tmp_path, "memo.txt", "関係ないファイル")
    assert build_blog.load_categories(str(tmp_path)) == ["エアコン"]


def test_フォルダが無ければ空(tmp_path):
    assert build_blog.load_categories(str(tmp_path / "nothing")) == []


# ---- visible_categories（ボタンに出すカテゴリ） ----


# 2026-11-02 仕様変更（RIKIYA指示「自動で消さないで」）：記事0本のカテゴリもボタンを出す
def test_記事0本のカテゴリも出す():
    articles = [{"category": "エアコン"}, {"category": "エアコン"}]
    assert build_blog.visible_categories(["エアコン", "洗濯機"], articles) == [
        "エアコン",
        "洗濯機",
    ]


def test_一覧に無いカテゴリの記事も消さず末尾に出す():
    articles = [{"category": "エアコン"}, {"category": "旧カテゴリ"}]
    assert build_blog.visible_categories(["エアコン"], articles) == [
        "エアコン",
        "旧カテゴリ",
    ]


def test_一覧が空でも記事のカテゴリで出す():
    articles = [{"category": "キッチン"}, {"category": "エアコン"}]
    assert build_blog.visible_categories([], articles) == ["キッチン", "エアコン"]


# ---- render_filter_buttons ----


def test_ボタンは_すべて_が先頭で選択状態():
    html_out = build_blog.render_filter_buttons(["エアコン", "洗濯機"])
    assert html_out.index('data-filter="すべて"') < html_out.index(
        'data-filter="エアコン"'
    )
    assert html_out.count('aria-pressed="true"') == 1
    assert 'data-filter="洗濯機"' in html_out


def test_ボタンの文字は無害化される():
    html_out = build_blog.render_filter_buttons(['<b>"x"</b>'])
    assert "<b>" not in html_out
    assert "&lt;b&gt;" in html_out


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
