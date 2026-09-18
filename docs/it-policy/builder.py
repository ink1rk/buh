"""Движок вёрстки многостраничного PDF-документа Политики ОТИ.

Отвечает за шрифты, шаблоны страниц, колонтитулы, нумерацию разделов,
таблиц и рисунков, оглавление и типовые блоки (врезки, формы, чек-листы).
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Frame,
    Image,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

NAVY = colors.HexColor("#14263C")
BLUE = colors.HexColor("#2B6CB0")
BLUE_L = colors.HexColor("#EAF2FA")
TEAL = colors.HexColor("#2C8C99")
TEAL_L = colors.HexColor("#E7F3F5")
GREEN = colors.HexColor("#2E7D5B")
GREEN_L = colors.HexColor("#E8F3EE")
AMBER = colors.HexColor("#C98A0B")
AMBER_L = colors.HexColor("#FDF4E1")
RED = colors.HexColor("#B33A3A")
RED_L = colors.HexColor("#FBEAEA")
GREY = colors.HexColor("#6B7785")
GREY_L = colors.HexColor("#F2F5F8")
LINE = colors.HexColor("#D6DEE6")
INK = colors.HexColor("#20303F")

FONT_SETS = [
    {
        "regular": "/usr/share/fonts/truetype/macos/Inter-Regular.ttf",
        "bold": "/usr/share/fonts/truetype/macos/Inter-SemiBold.ttf",
        "italic": "/usr/share/fonts/truetype/macos/Inter-Italic.ttf",
        "boldItalic": "/usr/share/fonts/truetype/macos/Inter-SemiBoldItalic.ttf",
    },
    {
        "regular": "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "bold": "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "italic": "/usr/share/fonts/truetype/noto/NotoSans-Italic.ttf",
        "boldItalic": "/usr/share/fonts/truetype/noto/NotoSans-BoldItalic.ttf",
    },
    {
        "regular": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "bold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "italic": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
        "boldItalic": "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",
    },
]

BODY = "Body"
BODY_B = "Body-Bold"
BODY_I = "Body-Italic"
BODY_BI = "Body-BoldItalic"


def register_fonts() -> None:
    chosen = None
    for fs in FONT_SETS:
        if all(Path(p).exists() for p in fs.values()):
            chosen = fs
            break
    if chosen is None:
        raise RuntimeError("Не найден шрифт с поддержкой кириллицы")
    pdfmetrics.registerFont(TTFont(BODY, chosen["regular"]))
    pdfmetrics.registerFont(TTFont(BODY_B, chosen["bold"]))
    pdfmetrics.registerFont(TTFont(BODY_I, chosen["italic"]))
    pdfmetrics.registerFont(TTFont(BODY_BI, chosen["boldItalic"]))
    pdfmetrics.registerFontFamily(
        BODY, normal=BODY, bold=BODY_B, italic=BODY_I, boldItalic=BODY_BI
    )


DOC_TITLE = "Политика отдела технической инфраструктуры"
DOC_CODE = "ПОЛ-ОТИ-01"
DOC_VERSION = "Редакция 1.0 (проект)"
COMPANY = "Группа компаний «ЭКСОН»"
CONFIDENTIAL = "Для внутреннего использования"


class PolicyDoc(BaseDocTemplate):
    def __init__(self, path: str, **kw):
        self.left = 20 * mm
        self.right = 18 * mm
        self.top = 20 * mm
        self.bottom = 18 * mm
        super().__init__(
            path,
            pagesize=A4,
            leftMargin=self.left,
            rightMargin=self.right,
            topMargin=self.top,
            bottomMargin=self.bottom,
            title=DOC_TITLE,
            author=COMPANY,
            subject="Нормативный документ ИТ-блока",
            creator="Генератор документа (reportlab)",
            **kw,
        )
        pw, ph = A4
        lw, lh = landscape(A4)
        body_frame = Frame(
            self.left, self.bottom,
            pw - self.left - self.right, ph - self.top - self.bottom,
            id="body", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
        )
        cover_frame = Frame(
            self.left, self.bottom,
            pw - self.left - self.right, ph - self.top - self.bottom,
            id="cover", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
        )
        wide_frame = Frame(
            16 * mm, 14 * mm,
            lw - 30 * mm, lh - 30 * mm,
            id="wide", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
        )
        self.addPageTemplates([
            PageTemplate(id="cover", frames=[cover_frame], onPage=self._cover_decor, pagesize=A4),
            PageTemplate(id="body", frames=[body_frame], onPage=self._body_decor, pagesize=A4),
            PageTemplate(id="wide", frames=[wide_frame], onPage=self._wide_decor,
                         pagesize=landscape(A4)),
        ])
        self.current_section = ""
        self._section_by_page = {}
        self._prev_section_by_page = {}

    # -- оформление страниц ------------------------------------------------------------
    def _cover_decor(self, canv, doc):
        pw, ph = A4
        canv.saveState()
        canv.setFillColor(NAVY)
        canv.rect(0, ph - 34 * mm, pw, 34 * mm, stroke=0, fill=1)
        canv.setFillColor(BLUE)
        canv.rect(0, ph - 37 * mm, pw, 3 * mm, stroke=0, fill=1)
        canv.setFillColor(NAVY)
        canv.rect(0, 0, pw, 12 * mm, stroke=0, fill=1)
        canv.setFillColor(colors.white)
        canv.setFont(BODY, 8)
        canv.drawString(self.left, 5 * mm, f"{COMPANY} · {CONFIDENTIAL}")
        canv.drawRightString(pw - self.right, 5 * mm, DOC_CODE)
        canv.restoreState()

    def _header_footer(self, canv, doc, pagesize):
        pw, ph = pagesize
        canv.saveState()
        canv.setFont(BODY, 7.2)
        canv.setFillColor(GREY)
        left_margin = doc.leftMargin
        right_margin = pw - doc.rightMargin
        canv.drawString(left_margin, ph - 12 * mm, f"{DOC_CODE} · {DOC_TITLE}")
        section = (self._section_for_page(canv.getPageNumber()) or "")[:74]
        canv.drawRightString(right_margin, ph - 12 * mm, section)
        canv.setStrokeColor(LINE)
        canv.setLineWidth(0.6)
        canv.line(left_margin, ph - 13.6 * mm, right_margin, ph - 13.6 * mm)
        canv.line(left_margin, 12.4 * mm, right_margin, 12.4 * mm)
        canv.setFillColor(GREY)
        canv.drawString(left_margin, 9 * mm, f"{COMPANY} · {CONFIDENTIAL}")
        canv.drawRightString(right_margin, 9 * mm, DOC_VERSION)
        canv.setFont(BODY_B, 7.6)
        canv.setFillColor(NAVY)
        canv.drawCentredString(pw / 2.0, 9 * mm, f"{canv.getPageNumber()}")
        canv.restoreState()

    def _body_decor(self, canv, doc):
        self._header_footer(canv, doc, A4)

    def _wide_decor(self, canv, doc):
        self._header_footer(canv, doc, landscape(A4))

    # -- оглавление --------------------------------------------------------------------
    def handle_documentBegin(self):
        self._prev_section_by_page = self._section_by_page
        self._section_by_page = {}
        super().handle_documentBegin()

    def _section_for_page(self, page_no):
        mapping = self._prev_section_by_page or self._section_by_page
        candidates = [p for p in mapping if p <= page_no]
        return mapping[max(candidates)] if candidates else ""

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph):
            style = flowable.style.name
            text = flowable.getPlainText()
            if style == "H1":
                self.current_section = text
                self._section_by_page.setdefault(self.page, text)
                self.notify("TOCEntry", (0, text, self.page))
            elif style == "H2":
                self.notify("TOCEntry", (1, text, self.page))


def _styles():
    base = ParagraphStyle(
        "Body", fontName=BODY, fontSize=9.2, leading=13.4, textColor=INK,
        alignment=TA_JUSTIFY, spaceAfter=4.5,
    )
    s = {"body": base}
    s["title"] = ParagraphStyle("CoverTitle", parent=base, fontName=BODY_B, fontSize=25,
                                leading=30, textColor=NAVY, alignment=TA_LEFT, spaceAfter=0)
    s["subtitle"] = ParagraphStyle("CoverSub", parent=base, fontSize=12, leading=17,
                                   textColor=BLUE, alignment=TA_LEFT)
    s["cover_small"] = ParagraphStyle("CoverSmall", parent=base, fontSize=8.6, leading=12.4,
                                      textColor=GREY, alignment=TA_LEFT)
    s["h1"] = ParagraphStyle("H1", parent=base, fontName=BODY_B, fontSize=16, leading=20,
                             textColor=NAVY, alignment=TA_LEFT, spaceBefore=0, spaceAfter=7)
    s["h1sub"] = ParagraphStyle("H1Sub", parent=base, fontSize=9, leading=12.6,
                                textColor=GREY, alignment=TA_LEFT, spaceAfter=10)
    s["h2"] = ParagraphStyle("H2", parent=base, fontName=BODY_B, fontSize=11.2, leading=15,
                             textColor=BLUE, alignment=TA_LEFT, spaceBefore=9, spaceAfter=4)
    s["h3"] = ParagraphStyle("H3", parent=base, fontName=BODY_B, fontSize=9.6, leading=13.2,
                             textColor=NAVY, alignment=TA_LEFT, spaceBefore=6, spaceAfter=3)
    s["bullet"] = ParagraphStyle("Bullet", parent=base, leftIndent=11, bulletIndent=2,
                                 spaceAfter=2.2)
    s["caption"] = ParagraphStyle("Caption", parent=base, fontName=BODY_I, fontSize=7.8,
                                  leading=10.6, textColor=GREY, alignment=TA_CENTER,
                                  spaceBefore=3, spaceAfter=9)
    s["th"] = ParagraphStyle("TH", parent=base, fontName=BODY_B, fontSize=7.6, leading=10,
                             textColor=colors.white, alignment=TA_LEFT, spaceAfter=0)
    s["td"] = ParagraphStyle("TD", parent=base, fontSize=7.6, leading=10.2,
                             alignment=TA_LEFT, spaceAfter=0)
    s["td_b"] = ParagraphStyle("TDB", parent=base, fontName=BODY_B, fontSize=7.6, leading=10.2,
                               alignment=TA_LEFT, spaceAfter=0)
    s["td_c"] = ParagraphStyle("TDC", parent=base, fontSize=7.6, leading=10.2,
                               alignment=TA_CENTER, spaceAfter=0)
    s["callout"] = ParagraphStyle("Callout", parent=base, fontSize=8.8, leading=12.6,
                                  spaceAfter=0)
    s["callout_t"] = ParagraphStyle("CalloutT", parent=base, fontName=BODY_B, fontSize=8.8,
                                    leading=12.4, spaceAfter=2.5, alignment=TA_LEFT)
    s["form_label"] = ParagraphStyle("FormLabel", parent=base, fontSize=7.8, leading=10.4,
                                     alignment=TA_LEFT, spaceAfter=0)
    s["form_hint"] = ParagraphStyle("FormHint", parent=base, fontName=BODY_I, fontSize=6.9,
                                    leading=9.2, textColor=GREY, alignment=TA_LEFT, spaceAfter=0)
    s["toc1"] = ParagraphStyle("TOC1", parent=base, fontName=BODY_B, fontSize=9.4, leading=14,
                               textColor=NAVY, spaceBefore=5, alignment=TA_LEFT)
    s["toc2"] = ParagraphStyle("TOC2", parent=base, fontSize=8.6, leading=12.2,
                               leftIndent=14, textColor=INK, alignment=TA_LEFT)
    s["note"] = ParagraphStyle("Note", parent=base, fontName=BODY_I, fontSize=8.2,
                               leading=11.6, textColor=GREY)
    return s


class Builder:
    """Сборщик содержания документа."""

    def __init__(self, out_path: str, charts: dict):
        register_fonts()
        self.doc = PolicyDoc(out_path)
        self.s = _styles()
        self.charts = charts
        self.story = []
        self.chapter = 0
        self.sub = 0
        self.table_no = 0
        self.figure_no = 0
        self.form_no = 0
        self.appendix_mode = False
        self.appendix_letters = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        self.appendix_idx = -1
        self.content_width = A4[0] - self.doc.left - self.doc.right
        self.wide_width = landscape(A4)[0] - 30 * mm

    # -- служебное ---------------------------------------------------------------------
    def add(self, flowable):
        self.story.append(flowable)

    def spacer(self, h=6):
        self.add(Spacer(1, h))

    def page_break(self):
        for fl in reversed(self.story):
            if isinstance(fl, NextPageTemplate):
                continue
            if isinstance(fl, PageBreak):
                return
            break
        self.add(PageBreak())

    def keep_next(self, height=60):
        self.add(CondPageBreak(height))

    def next_template(self, name):
        self.add(NextPageTemplate(name))

    def wide_start(self):
        """Переход на альбомную страницу."""
        self.add(NextPageTemplate("wide"))
        self.add(PageBreak())

    def wide_end(self):
        self.add(NextPageTemplate("body"))
        self.add(PageBreak())

    # -- заголовки ---------------------------------------------------------------------
    def h1(self, title, lead=None, new_page=True):
        if new_page and self.story:
            self.page_break()
        self.chapter += 1
        self.sub = 0
        num = f"{self.chapter}."
        self.add(_ChapterRule(self.content_width))
        self.add(Paragraph(f"{num} {title}", self.s["h1"]))
        if lead:
            self.add(Paragraph(lead, self.s["h1sub"]))

    def appendix(self, title, lead=None, wide=False):
        if wide:
            self.add(NextPageTemplate("wide"))
        self.page_break()
        self.appendix_idx += 1
        letter = self.appendix_letters[self.appendix_idx]
        self.sub = 0
        self.add(_ChapterRule(self.wide_width if wide else self.content_width, color=TEAL))
        self.add(Paragraph(f"Приложение {letter}. {title}", self.s["h1"]))
        if lead:
            self.add(Paragraph(lead, self.s["h1sub"]))
        return letter

    def h2(self, title):
        self.sub += 1
        prefix = f"{self.chapter}.{self.sub}."
        if self.appendix_mode:
            prefix = ""
        self.keep_next(100)
        self.add(Paragraph(f"{prefix} {title}".strip(), self.s["h2"]))

    def h3(self, title):
        self.keep_next(66)
        self.add(Paragraph(title, self.s["h3"]))

    # -- текст -------------------------------------------------------------------------
    def p(self, text, style="body"):
        self.add(Paragraph(text, self.s[style]))

    def note(self, text):
        self.add(Paragraph(text, self.s["note"]))

    def bullets(self, items, numbered=False, dash=False):
        for i, it in enumerate(items, 1):
            if numbered:
                bullet = f"{i})"
            elif dash:
                bullet = "—"
            else:
                bullet = "•"
            self.add(Paragraph(it, self.s["bullet"], bulletText=bullet))
        self.spacer(3)

    # -- таблицы -----------------------------------------------------------------------
    def table(self, rows, widths=None, caption=None, header=True, wide=False,
              align_center=None, bold_col0=False, fontsize=7.6, row_colors=None,
              cell_colors=None, keep=True):
        total = self.wide_width if wide else self.content_width
        ncols = len(rows[0])
        if widths is None:
            col_widths = [total / ncols] * ncols
        else:
            ssum = float(sum(widths))
            col_widths = [total * w / ssum for w in widths]

        align_center = align_center or []
        data = []
        for r_i, row in enumerate(rows):
            out = []
            for c_i, cell in enumerate(row):
                if isinstance(cell, (Table, Image, Paragraph)):
                    out.append(cell)
                    continue
                text = "" if cell is None else str(cell)
                if header and r_i == 0:
                    st = self.s["th"]
                elif c_i in align_center:
                    st = self.s["td_c"]
                elif bold_col0 and c_i == 0:
                    st = self.s["td_b"]
                else:
                    st = self.s["td"]
                if fontsize != 7.6:
                    st = ParagraphStyle(f"{st.name}-{fontsize}", parent=st,
                                        fontSize=fontsize, leading=fontsize * 1.34)
                out.append(Paragraph(text, st))
            data.append(out)

        cmds = [
            ("GRID", (0, 0), (-1, -1), 0.45, LINE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3.4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.6),
        ]
        if header:
            cmds += [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, NAVY),
                ("REPEATROWS", (0, 0), (-1, 0), 1),
            ]
            for r in range(1, len(data)):
                if r % 2 == 0:
                    cmds.append(("BACKGROUND", (0, r), (-1, r), GREY_L))
        for spec in (row_colors or []):
            r, color = spec
            cmds.append(("BACKGROUND", (0, r), (-1, r), color))
        for spec in (cell_colors or []):
            c, r, color = spec
            cmds.append(("BACKGROUND", (c, r), (c, r), color))

        t = Table(data, colWidths=col_widths, repeatRows=1 if header else 0, hAlign="LEFT")
        t.setStyle(TableStyle(cmds))
        block = [t]
        if caption:
            self.table_no += 1
            block.append(Paragraph(f"Таблица {self.table_no}. {caption}", self.s["caption"]))
        else:
            block.append(Spacer(1, 8))
        if keep and len(rows) <= 8:
            self.add(KeepTogether(block))
        else:
            for b in block:
                self.add(b)

    # -- рисунки -----------------------------------------------------------------------
    def figure(self, chart_name, caption, width_ratio=1.0, wide=False, max_height=None):
        path = self.charts[chart_name]
        avail = (self.wide_width if wide else self.content_width) * width_ratio
        reader = ImageReader(path)
        iw, ih = reader.getSize()
        w = avail
        h = avail * ih / iw
        limit = max_height or (215 * mm if wide else 225 * mm)
        if h > limit:
            h = limit
            w = limit * iw / ih
        img = Image(path, width=w, height=h)
        img.hAlign = "CENTER"
        self.figure_no += 1
        cap = Paragraph(f"Рис. {self.figure_no}. {caption}", self.s["caption"])
        self.add(KeepTogether([img, cap]))

    # -- врезки ------------------------------------------------------------------------
    def callout(self, text, title=None, kind="rule"):
        palette = {
            "rule": (BLUE, BLUE_L),
            "warn": (AMBER, AMBER_L),
            "stop": (RED, RED_L),
            "ok": (GREEN, GREEN_L),
            "info": (GREY, GREY_L),
            "key": (TEAL, TEAL_L),
        }
        edge, fill = palette[kind]
        inner = []
        if title:
            inner.append(Paragraph(title, ParagraphStyle(
                "cot", parent=self.s["callout_t"], textColor=edge)))
        inner.append(Paragraph(text, self.s["callout"]))
        t = Table([[inner]], colWidths=[self.content_width], hAlign="LEFT")
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), fill),
            ("LINEBEFORE", (0, 0), (0, -1), 2.4, edge),
            ("BOX", (0, 0), (-1, -1), 0.4, edge),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        self.add(KeepTogether([t, Spacer(1, 8)]))

    # -- формы для заполнения ----------------------------------------------------------
    def form(self, fields, widths=(34, 66), rowheight=17, caption=None, wide=False):
        """Форма «ярлык — пустое поле». fields: [(label, hint|None), ...]"""
        total = self.wide_width if wide else self.content_width
        w = [total * widths[0] / 100.0, total * widths[1] / 100.0]
        data = []
        for label, hint in fields:
            left = [Paragraph(label, self.s["form_label"])]
            if hint:
                left.append(Paragraph(hint, self.s["form_hint"]))
            data.append([left, Spacer(1, rowheight - 5)])
        t = Table(data, colWidths=w, hAlign="LEFT")
        t.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.45, LINE),
            ("BACKGROUND", (0, 0), (0, -1), GREY_L),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ]))
        block = [t]
        if caption:
            self.form_no += 1
        block.append(Paragraph(
            f"Форма {self.form_no}. {caption}" if caption else "", self.s["caption"]))
        self.add(KeepTogether(block) if len(fields) <= 14 else block[0])
        if len(fields) > 14:
            self.add(block[1])

    def blank_table(self, headers, n_rows=8, widths=None, caption=None, rowheight=16,
                    wide=False, numbered=True):
        """Пустая таблица для заполнения от руки или в электронном виде."""
        total = self.wide_width if wide else self.content_width
        head = (["№"] if numbered else []) + list(headers)
        if widths is None:
            widths = [1] * len(headers)
        w = ([0.35] if numbered else []) + list(widths)
        ssum = float(sum(w))
        col_widths = [total * x / ssum for x in w]
        data = [[Paragraph(h, self.s["th"]) for h in head]]
        for i in range(1, n_rows + 1):
            row = ([Paragraph(str(i), self.s["td_c"])] if numbered else []) + [""] * len(headers)
            data.append(row)
        t = Table(data, colWidths=col_widths,
                  rowHeights=[None] + [rowheight] * n_rows, repeatRows=1, hAlign="LEFT")
        t.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.45, LINE),
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        block = [t]
        if caption:
            self.form_no += 1
            block.append(Paragraph(f"Форма {self.form_no}. {caption}", self.s["caption"]))
        else:
            block.append(Spacer(1, 8))
        if n_rows <= 10:
            self.add(KeepTogether(block))
        else:
            for b in block:
                self.add(b)

    def checklist(self, items, caption=None, columns=("Выполнено (да/нет)", "Дата", "Ответственный")):
        total = self.content_width
        widths = [0.35, 5.2] + [1.35] * len(columns)
        ssum = float(sum(widths))
        col_widths = [total * x / ssum for x in widths]
        data = [[Paragraph("№", self.s["th"]), Paragraph("Контрольный пункт", self.s["th"])]
                + [Paragraph(c, self.s["th"]) for c in columns]]
        for i, it in enumerate(items, 1):
            data.append([Paragraph(str(i), self.s["td_c"]),
                         Paragraph(it, self.s["td"])] + [""] * len(columns))
        t = Table(data, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
        t.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.45, LINE),
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3.6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.8),
        ] + [("BACKGROUND", (0, r), (-1, r), GREY_L) for r in range(2, len(data), 2)]))
        block = [t]
        if caption:
            self.form_no += 1
            block.append(Paragraph(f"Форма {self.form_no}. {caption}", self.s["caption"]))
        else:
            block.append(Spacer(1, 8))
        if len(items) <= 10:
            self.add(KeepTogether(block))
        else:
            for b in block:
                self.add(b)

    def signature_block(self, roles=(("Разработал", "Руководитель отдела технической инфраструктуры"),
                                     ("Согласовал", "ИТ-директор"),
                                     ("Согласовал", "Начальник отдела информационной безопасности"),
                                     ("Утвердил", "Генеральный директор"))):
        rows = [["Действие", "Должность", "Ф. И. О.", "Подпись", "Дата"]]
        for action, role in roles:
            rows.append([action, role, "", "", ""])
        self.table(rows, widths=[13, 34, 22, 16, 15], caption=None, keep=True)

    # -- оглавление --------------------------------------------------------------------
    def toc(self):
        toc = TableOfContents()
        toc.levelStyles = [self.s["toc1"], self.s["toc2"]]
        toc.dotsMinLevel = 0
        self.add(Paragraph("Содержание", self.s["h1"]))
        self.add(Spacer(1, 4))
        self.add(toc)

    def build(self):
        self.doc.multiBuild(self.story)
        return self.doc.filename


class _ChapterRule(Spacer):
    """Тонкая цветная линия перед заголовком раздела."""

    def __init__(self, width, color=BLUE, thickness=2.2):
        super().__init__(width, thickness + 5)
        self._w = width
        self._color = color
        self._t = thickness

    def draw(self):
        self.canv.saveState()
        self.canv.setFillColor(self._color)
        self.canv.rect(0, 5, self._w * 0.18, self._t, stroke=0, fill=1)
        self.canv.setFillColor(LINE)
        self.canv.rect(self._w * 0.18, 5 + self._t / 2 - 0.25, self._w * 0.82, 0.5,
                       stroke=0, fill=1)
        self.canv.restoreState()
