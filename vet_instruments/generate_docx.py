#!/usr/bin/env python3
"""
Generator script: creates one DOCX file per instrument category,
matching the format of the example Bone Cutters & Nibblers file.
"""

import os
import sys
from docx import Document
from docx.shared import Pt, RGBColor, Cm, Twips
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from PIL import Image as PILImage

# ── colour / size constants ──────────────────────────────────────────────────
BLUE   = RGBColor(0x1F, 0x4E, 0x9C)   # header
ORANGE = RGBColor(0xE8, 0x73, 0x0C)   # category title
GRAY   = RGBColor(0x8A, 0x7F, 0x6A)   # instrument name
BLACK  = RGBColor(0x00, 0x00, 0x00)

SZ_HEADER   = 40   # half-points  → 20 pt
SZ_CATEGORY = 28   # 14 pt
SZ_INSTNAME = 24   # 12 pt
SZ_HEADING  = 22   # 11 pt
SZ_BODY     = 21   # 10.5 pt

IMAGE_WIDTH_CM = 5.5      # right-cell image width
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMG_BASE = os.path.join(BASE_DIR, "INSTRUMENTS")
OUT_DIR  = os.path.join(BASE_DIR, "output_docx")
os.makedirs(OUT_DIR, exist_ok=True)


# ── low-level helpers ────────────────────────────────────────────────────────

def _set_run_format(run, size_hp, bold=False, color=None, italic=False):
    rpr = run._r.get_or_add_rPr()
    sz = OxmlElement('w:sz');   sz.set(qn('w:val'), str(size_hp)); rpr.append(sz)
    szcs = OxmlElement('w:szCs'); szcs.set(qn('w:val'), str(size_hp)); rpr.append(szcs)
    if bold:
        b = OxmlElement('w:b');   rpr.append(b)
        bcs = OxmlElement('w:bCs'); rpr.append(bcs)
    if color:
        c = OxmlElement('w:color')
        hex_val = '{:02X}{:02X}{:02X}'.format(color[0], color[1], color[2])
        c.set(qn('w:val'), hex_val); rpr.append(c)
    if italic:
        i = OxmlElement('w:i'); rpr.append(i)


def _set_para_spacing(para, before=0, after=0):
    ppr = para._p.get_or_add_pPr()
    sp = OxmlElement('w:spacing')
    sp.set(qn('w:before'), str(before))
    sp.set(qn('w:after'),  str(after))
    ppr.append(sp)


def _set_para_align(para, align='center'):
    ppr = para._p.get_or_add_pPr()
    jc = OxmlElement('w:jc'); jc.set(qn('w:val'), align); ppr.append(jc)


def add_styled_para(doc, text, size_hp, bold=False, color=None,
                    align=None, before=0, after=0):
    para = doc.add_paragraph()
    _set_para_spacing(para, before=before, after=after)
    if align:
        _set_para_align(para, align)
    run = para.add_run(text)
    _set_run_format(run, size_hp, bold=bold, color=color)
    return para


def set_cell_borders_none(cell):
    tc = cell._tc
    tcpr = tc.get_or_add_tcPr()
    borders = OxmlElement('w:tcBorders')
    for side in ('top', 'left', 'bottom', 'right'):
        el = OxmlElement(f'w:{side}')
        el.set(qn('w:val'),   'none')
        el.set(qn('w:color'), 'FFFFFF')
        el.set(qn('w:sz'),    '0')
        borders.append(el)
    tcpr.append(borders)


def set_cell_margins(cell, top=0, left=0, bottom=0, right=0):
    tc = cell._tc
    tcpr = tc.get_or_add_tcPr()
    mar = OxmlElement('w:tcMar')
    for side, val in (('top', top), ('left', left), ('bottom', bottom), ('right', right)):
        el = OxmlElement(f'w:{side}')
        el.set(qn('w:type'), 'dxa')
        el.set(qn('w:w'),    str(val))
        mar.append(el)
    tcpr.append(mar)


def set_cell_valign(cell, align='top'):
    tc = cell._tc
    tcpr = tc.get_or_add_tcPr()
    va = OxmlElement('w:vAlign'); va.set(qn('w:val'), align)
    tcpr.append(va)


def set_cell_width(cell, width_twips):
    tc = cell._tc
    tcpr = tc.get_or_add_tcPr()
    w = OxmlElement('w:tcW')
    w.set(qn('w:type'), 'dxa')
    w.set(qn('w:w'),    str(width_twips))
    tcpr.append(w)


def set_table_width(table, width_twips):
    tbl = table._tbl
    tblpr = tbl.find(qn('w:tblPr'))
    if tblpr is None:
        tblpr = OxmlElement('w:tblPr')
        tbl.insert(0, tblpr)
    w = OxmlElement('w:tblW')
    w.set(qn('w:type'), 'dxa')
    w.set(qn('w:w'),    str(width_twips))
    tblpr.append(w)


def add_table_borders(table):
    tbl = table._tbl
    tblpr = tbl.find(qn('w:tblPr'))
    if tblpr is None:
        tblpr = OxmlElement('w:tblPr')
        tbl.insert(0, tblpr)
    borders = OxmlElement('w:tblBorders')
    for side in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        el = OxmlElement(f'w:{side}')
        el.set(qn('w:val'),   'single')
        el.set(qn('w:color'), 'auto')
        el.set(qn('w:sz'),    '4')
        borders.append(el)
    tblpr.append(borders)


def insert_image_in_cell(cell, img_path):
    """Add image to an existing cell, preserving the cell's empty paragraph."""
    para = cell.paragraphs[0]
    run = para.add_run()
    try:
        with PILImage.open(img_path) as im:
            w_px, h_px = im.size
        # maintain aspect ratio
        target_w_cm = IMAGE_WIDTH_CM
        target_h_cm = target_w_cm * h_px / w_px
        run.add_picture(img_path, width=Cm(target_w_cm), height=Cm(target_h_cm))
    except Exception as e:
        para.add_run(f'[Image: {os.path.basename(img_path)}]')


# ── per-instrument block ─────────────────────────────────────────────────────

def add_instrument_block(doc, category_display, instrument, cat_folder):
    """Render a single instrument section into doc."""
    name    = instrument['name']
    img_fn  = instrument['image']
    i_use   = instrument['intended_use']
    func    = instrument['function']
    advs    = instrument['advantages']
    faqs    = instrument['faqs']

    img_path = os.path.join(IMG_BASE, cat_folder, img_fn)

    # ── header ────────────────────────────────────────────────────────────────
    add_styled_para(doc, 'ORTHOPAEDIC INSTRUMENTS',
                    SZ_HEADER, bold=True, color=BLUE,
                    align='center', after=60)

    # ── category title ────────────────────────────────────────────────────────
    add_styled_para(doc, category_display,
                    SZ_CATEGORY, bold=True, color=ORANGE,
                    align='center', after=160)

    # ── instrument name ───────────────────────────────────────────────────────
    add_styled_para(doc, name,
                    SZ_INSTNAME, bold=True, color=GRAY,
                    after=120)

    # ── Intended Use heading ──────────────────────────────────────────────────
    add_styled_para(doc, 'Intended Use',
                    SZ_HEADING, bold=True, color=BLACK,
                    before=160, after=80)

    # ── table: text | image ───────────────────────────────────────────────────
    table = doc.add_table(rows=1, cols=2)
    set_table_width(table, 9360)
    add_table_borders(table)

    left_cell  = table.cell(0, 0)
    right_cell = table.cell(0, 1)

    set_cell_width(left_cell,  5560)
    set_cell_width(right_cell, 3800)
    set_cell_borders_none(left_cell)
    set_cell_borders_none(right_cell)
    set_cell_margins(left_cell,  top=0, left=0, bottom=0, right=160)
    set_cell_margins(right_cell, top=0, left=80, bottom=0, right=0)
    set_cell_valign(left_cell, 'top')

    # text paragraph in left cell
    lp = left_cell.paragraphs[0]
    _set_para_align(lp, 'both')
    lr = lp.add_run(i_use)
    _set_run_format(lr, SZ_BODY)

    # image in right cell
    if os.path.exists(img_path):
        insert_image_in_cell(right_cell, img_path)
    else:
        right_cell.paragraphs[0].add_run(f'[Missing: {img_fn}]')

    # ── Function ──────────────────────────────────────────────────────────────
    add_styled_para(doc, 'Function',
                    SZ_HEADING, bold=True, color=BLACK,
                    before=160, after=80)
    p = doc.add_paragraph()
    r = p.add_run(func)
    _set_run_format(r, SZ_BODY)

    # ── Advantages ────────────────────────────────────────────────────────────
    add_styled_para(doc, 'Advantages',
                    SZ_HEADING, bold=True, color=BLACK,
                    before=160, after=80)
    for title, body in advs:
        p = doc.add_paragraph()
        r_title = p.add_run(f'{title}: ')
        _set_run_format(r_title, SZ_BODY, bold=True)
        r_body = p.add_run(body)
        _set_run_format(r_body, SZ_BODY, bold=True)

    # ── FAQ ───────────────────────────────────────────────────────────────────
    add_styled_para(doc, 'FAQ',
                    SZ_HEADING, bold=True, color=BLACK,
                    before=160, after=80)
    for q, a in faqs:
        pq = doc.add_paragraph()
        rq = pq.add_run(f'Q: {q}')
        _set_run_format(rq, SZ_BODY, bold=True)

        pa = doc.add_paragraph()
        ra = pa.add_run(f'A: {a}')
        _set_run_format(ra, SZ_BODY)


# ── category DOCX generator ──────────────────────────────────────────────────

def generate_category_docx(cat_key, cat_data):
    display = cat_data.get('display_name', cat_key)
    instruments = cat_data['instruments']
    cat_folder = cat_key  # folder name matches key

    doc = Document()

    # Remove default styles that add unwanted spacing
    for style in doc.styles:
        if style.name == 'Normal':
            style.font.size = Pt(10.5)

    for i, instr in enumerate(instruments):
        add_instrument_block(doc, display, instr, cat_folder)
        # page break between instruments (not after last)
        if i < len(instruments) - 1:
            doc.add_page_break()

    safe_name = display.replace('/', '-').replace('&', 'and').replace(',', '')
    out_path = os.path.join(OUT_DIR, f'{safe_name}.docx')
    doc.save(out_path)
    print(f'  Saved: {out_path}')
    return out_path


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    sys.path.insert(0, BASE_DIR)
    from content_data import CATEGORIES as CAT1

    all_categories = dict(CAT1)

    try:
        from content_data_part2 import CATEGORIES_PART2
        all_categories.update(CATEGORIES_PART2)
        print(f'Loaded part2: {len(CATEGORIES_PART2)} categories')
    except ImportError:
        print('content_data_part2.py not found')

    try:
        from content_data_part3a import CATEGORIES_PART3A
        all_categories.update(CATEGORIES_PART3A)
        print(f'Loaded part3a: {len(CATEGORIES_PART3A)} categories')
    except ImportError:
        print('content_data_part3a.py not found')

    try:
        from content_data_part3b import CATEGORIES_PART3B
        all_categories.update(CATEGORIES_PART3B)
        print(f'Loaded part3b: {len(CATEGORIES_PART3B)} categories')
    except ImportError:
        print('content_data_part3b.py not found')

    print(f'\nGenerating {len(all_categories)} category DOCX files...\n')
    for cat_key, cat_data in all_categories.items():
        print(f'Processing: {cat_key}')
        try:
            generate_category_docx(cat_key, cat_data)
        except Exception as e:
            print(f'  ERROR: {e}')

    print('\nDone.')


if __name__ == '__main__':
    main()
