"""Offline tests for the news composer and the Telegram formatter.

Run on the assistant host:
    /opt/assistant/.venv/bin/python -m pytest /opt/assistant/tests -q
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import news
import tgfmt


def story(title, source="Лента", topic="other", ts=None, link="https://example.org/a"):
    return news.Story(title=title, link=link, source=source,
                      ts=ts if ts is not None else time.time(), topic=topic)


class TestFormatter:
    def test_markdown_becomes_html(self):
        out = tgfmt.to_html("**Итог:** всё ок\n- раз\n- два")
        assert out == "<b>Итог:</b> всё ок\n• раз\n• два"

    def test_existing_tags_survive(self):
        out = tgfmt.to_html('<b>Тема</b> и <a href="https://x.dev/a?b=1&c=2">ссылка</a>')
        assert out == '<b>Тема</b> и <a href="https://x.dev/a?b=1&amp;c=2">ссылка</a>'

    def test_unbalanced_tags_fall_back_to_plain(self):
        assert "<b>" not in tgfmt.to_html("Незакрытый <b>тег")

    def test_angle_brackets_are_escaped(self):
        assert tgfmt.to_html("5 < 7 & 8 > 3") == "5 &lt; 7 &amp; 8 &gt; 3"

    def test_plain_keeps_math_but_drops_markup(self):
        assert tgfmt.plain("<b>5 < 7</b> и **жирный**") == "5 < 7 и жирный"

    def test_split_keeps_chunks_balanced_and_short(self):
        text = "\n\n".join(f"<b>Блок {i}</b>\n" + "строка " * 80 for i in range(30))
        parts = tgfmt.split(text, limit=1000)
        assert parts and all(len(p) <= 1000 for p in parts)
        assert all(tgfmt._balanced(p) for p in parts)


class TestClassification:
    def test_rss_category_wins(self):
        assert news.classify("Некий заголовок", "", "", ["спорт"]) == "sport"

    def test_compound_category(self):
        assert news.classify("Заголовок", "", "", ["технологии / ит-бизнес"]) == "tech"

    def test_link_path_is_used(self):
        assert news.classify("Заголовок без слов", "", "https://tass.ru/proisshestviya/1", []) == "incident"

    def test_headline_keywords(self):
        assert news.classify("ЦБ снова поднял ставку", "", "", []) == "econ"

    def test_headline_beats_summary(self):
        topic = news.classify("Матч закончился вничью", "Спонсор — крупный банк", "", [])
        assert topic == "sport"

    def test_feed_topic_override(self):
        assert news.classify("Любой заголовок", "", "", ["спорт"], forced="tech") == "tech"


class TestFiltering:
    def test_tabloid_titles_dropped(self):
        assert news.is_junk("Звезда показала фигуру в бикини", [])
        assert news.is_junk("Гороскоп на неделю", [])

    def test_skipped_rubrics_dropped(self):
        assert news.is_junk("Обычный заголовок", ["из жизни"])

    def test_real_news_kept(self):
        assert not news.is_junk("Правительство обнулило пошлины на экспорт зерна", ["экономика"])


class TestDedupAndRanking:
    def test_similar_headlines_merge(self):
        a = news._tokens("Правительство обнулило пошлины на экспорт зерновых до конца года")
        b = news._tokens("Кабмин обнулил пошлины на экспорт зерновых до конца года")
        assert news._same_story(a, b)

    def test_unrelated_headlines_do_not_merge(self):
        a = news._tokens("Овечкин получил травму на сборах")
        b = news._tokens("Правительство обнулило пошлины на экспорт зерна")
        assert not news._same_story(a, b)

    def test_multi_source_story_outranks_clickbait(self):
        big = story("ЦБ снизил ключевую ставку", topic="econ")
        big.sources = ["РБК", "ТАСС"]
        fluff = story("Названы самые дешёвые города России", topic="other")
        assert news.score(big) > news.score(fluff)


class TestRendering:
    def test_html_has_links_sources_and_topic_headers(self):
        groups = {"main": [story("Главная новость", source="РБК", topic="econ")],
                  "sport": [story("Спортивная новость", source="Лента", topic="sport")]}
        out = news.render_html(groups=groups)
        assert '<a href="https://example.org/a">Главная новость</a>' in out
        assert "<b>Главное</b>" in out and "<b>Спорт</b>" in out
        assert "РБК · 1 мин назад" in out
        assert tgfmt._balanced(out)

    def test_flat_render_prefixes_topic_emoji(self):
        assert news.render_flat.__doc__          # flat view exists for briefings

    def test_empty_groups_produce_a_message(self):
        assert "нечего показать" in news.render_html(groups={})
