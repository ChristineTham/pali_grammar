#!/usr/bin/env python3

"""Compile HTML table of all grammatical possibilities of every inflected word-form."""

import argparse
from pathlib import Path
from typing import Optional

from mako.template import Template

from db.db_helpers import get_db_session
from db.models import DpdHeadword, Lookup

from tools.appledict_exporter import export_to_appledict
from tools.css_manager import CSSManager
from tools.goldendict_exporter import DictInfo, DictVariables, DictEntry
from tools.goldendict_exporter import export_to_goldendict_with_pyglossary
from tools.mdict_exporter import export_to_mdict
from tools.niggahitas import add_niggahitas
from tools.paths import ProjectPaths
from tools.printer import printer as pr

to_symbol = {
    "nom": "①",
    "acc": "②",
    "instr": "③",
    "dat": "④",
    "abl": "⑤",
    "gen": "⑥",
    "loc": "⑦",
    "voc": "⓪",
    "masc": "🚹",
    "fem": "🚺",
    "nt": "🚻",
    "x": "⚧️",
    "sg": "⨀",
    "pl": "⨂",
    "dual": "⨁",
    "act": "🟢",
    "reflx": "🔵",
    "pr": "▶️",
    "fut": "⏭",
    "aor": "⏮",
    "opt": "⏯",
    "imp": "⏹",
    "cond": "🔀",
    "imperf": "↩️",
    "perf": "🔄",
    "1st": "👆",
    "2nd": "🤘",
    "3rd": "🤟",
}

to_meaning = {
    "nom": "subject",
    "acc": "object",
    "instr": "by/with",
    "dat": "for",
    "abl": "from",
    "gen": "of",
    "loc": "in/at/on",
    "voc": "vocative",
}


def get_symbols(grammar: str):
    if grammar == "in comps":
        return "🆎"

    chunks = grammar.split(" ")
    return "".join(map(lambda s: to_symbol.get(s, s), chunks))


class ProgData:
    def __init__(self) -> None:
        self.make_goldendict = True
        self.make_mdict = True
        self.make_appledict = True
        self.install_appledict = False
        self.limit: Optional[int] = None

        self.pth = ProjectPaths()
        self.db_session = get_db_session(self.pth.dpd_db_path)

        self.grammar_css_path = Path("./grammar.css")
        self.grammar_apple_css_path = Path("./grammar_apple.css")
        self.pth.dpd_grammar_goldendict_dir = Path("./pali-grammar")
        self.pth.dpd_grammar_mdd_path = Path("./pali-grammar-mdict.mdd")
        self.pth.dpd_grammar_mdx_path = Path("./pali-grammar-mdict.mdx")
        self.pth.dpd_grammar_appledict_dir = Path("./share/pali-grammar-apple")
        self.pth.dpd_grammar_apple_bundle_path = Path("./share/pali-grammar.dictionary")
        self.pth.dpd_grammar_apple_zip_path = Path(
            "./share/pali-grammar-apple.dictionary.zip"
        )
        self.pth.grammar_dict_header_templ_path = Path("./grammar_dict_header.html")
        self.pth.grammar_templ_path = Path("./pali_grammar.html")
        self.pth.share_dir = Path("./share")

        self.pth.share_dir.mkdir(parents=True, exist_ok=True)

        # the grammar dictionaries
        self.html_dict: dict[str, str] = {}  # Renamed from grammar_dict_html

        # goldendict, mdict, and appledict data_list
        self.dict_data: list[DictEntry] = []

    def close_db(self):
        self.db_session.close()

    def commit_db(self):
        self.db_session.commit()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compile Pali Grammar dictionary for GoldenDict, MDict, and Apple Dictionary."
    )
    parser.add_argument(
        "--apple-only",
        action="store_true",
        help="Export only to Apple Dictionary",
    )
    parser.add_argument(
        "--goldendict-only",
        action="store_true",
        help="Export only to GoldenDict",
    )
    parser.add_argument(
        "--mdict-only",
        action="store_true",
        help="Export only to MDict",
    )
    parser.add_argument(
        "--no-apple",
        action="store_true",
        help="Skip Apple Dictionary export",
    )
    parser.add_argument(
        "--no-goldendict",
        action="store_true",
        help="Skip GoldenDict export",
    )
    parser.add_argument(
        "--no-mdict",
        action="store_true",
        help="Skip MDict export",
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="Install compiled Apple Dictionary bundle into ~/Library/Dictionaries",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="Export static web dictionary to share/web_dict (or --web-dir)",
    )
    parser.add_argument(
        "--web-dir",
        type=Path,
        default=Path("./share/web_dict"),
        help="Directory to write static web dictionary shards",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of entries processed (useful for testing)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    pr.tic()
    pr.title("exporting Pāḷi grammar dictionary")

    g = ProgData()

    if args.apple_only:
        g.make_goldendict = False
        g.make_mdict = False
        g.make_appledict = True
    elif args.goldendict_only:
        g.make_goldendict = True
        g.make_mdict = False
        g.make_appledict = False
    elif args.mdict_only:
        g.make_goldendict = False
        g.make_mdict = True
        g.make_appledict = False
    else:
        if args.no_apple:
            g.make_appledict = False
        if args.no_goldendict:
            g.make_goldendict = False
        if args.no_mdict:
            g.make_mdict = False

    if args.install:
        g.install_appledict = True
    if args.limit:
        g.limit = args.limit

    if args.web:
        from export_web_dict import export_web_dict

        export_web_dict(out_dir=args.web_dir, limit=args.limit)
        pr.toc()
        return

    generate_html_from_lookup(g)  # New function replaces old ones

    g.close_db()  # Close db session when done

    make_data_lists(g)
    prepare_gd_mdict_and_export(g)

    pr.toc()


def render_header_templ(
    __pth__: ProjectPaths, css: str, js: str, header_templ: Template
) -> str:
    """render the html header with css and js"""

    return str(header_templ.render(css=css, js=js))


def generate_html_from_lookup(g: ProgData):
    """Generate HTML grammar tables from Lookup table data."""
    pr.green("querying database")

    # Query the Lookup table for entries with grammar data
    query = (
        g.db_session.query(Lookup)
        .filter(Lookup.grammar.is_not(None), Lookup.grammar != "")
    )
    if g.limit is not None and g.limit > 0:
        query = query.limit(g.limit)
    lookup_results = query.all()

    pr.green("preloading headwords into memory")
    all_headwords = g.db_session.query(DpdHeadword).all()
    headwords_dict = {w.id: w for w in all_headwords}
    pr.yes(f"{len(headwords_dict)}")

    pr.green_title("compiling html")

    html_dict = {}

    # create the header from a template
    header_templ = Template(filename=str(g.pth.grammar_dict_header_templ_path))
    html_header = render_header_templ(
        g.pth, css=str(g.grammar_css_path), js="", header_templ=header_templ
    )

    # Add variables and fonts to header
    css_manager = CSSManager()
    html_header = css_manager.update_style(html_header, "primary")

    html_header1 = "<body>"
    html_header2 = "<div class='grammar_dict'><table class='grammar_dict'><thead><tr><th id='col1'>pos ⇅</th><th id='col2'>⇅</th><th id='col3'>⇅</th><th id='col4'>⇅</th><th id='col5'>usage ⇅</th><th id='col6'>word ⇅</th></tr></thead><tbody>"

    # Process each lookup entry
    for counter, lookup_entry in enumerate(lookup_results):
        inflected_word = lookup_entry.lookup_key
        grammar_data_list = (
            lookup_entry.grammar_unpack
        )  # [(headword, pos, grammar_str)]
        headwords = lookup_entry.headwords_unpack
        words = [
            headwords_dict[id]
            for id in headwords
            if id in headwords_dict
        ]
        mlist = "<ol>"
        for word in words:
            mlist += f"<li><i>{word.lemma_1}</i>"
            if word.lemma_2:
                mlist += f" (<i>{word.lemma_2}</i>)"
            mlist += f" [{word.construction_summary}]"
            mlist += f": {word.meaning_combo_html}"
            mlist += "</li>"
        mlist += "</ol>"

        html_lines = []
        for data_tuple in grammar_data_list:
            headword, pos, grammar_str = data_tuple
            html_line = "<tr>"
            html_line += f"<td><b>{pos}</b></td>"

            # get grammatical_categories from grammar_str
            grammatical_categories = []
            if grammar_str.startswith("reflx"):
                grammatical_categories.append(
                    grammar_str.split()[0] + " " + grammar_str.split()[1]
                )
                grammatical_categories += grammar_str.split()[2:]
                for grammatical_category in grammatical_categories:
                    html_line += f"<td>{grammatical_category}</td>"
            elif grammar_str.startswith("in comps"):
                html_line += f"<td colspan='3'>{grammar_str}</td>"
            else:
                grammatical_categories = grammar_str.split()
                # adding empty values if there are less than 3
                while len(grammatical_categories) < 3:
                    grammatical_categories.append("")
                for grammatical_category in grammatical_categories:
                    html_line += f"<td>{grammatical_category}</td>"

            gsymbol = get_symbols(grammar_str)
            case_usage = "".join(
                [val for key, val in to_meaning.items() if key in grammar_str]
            )

            html_line += f"<td>{case_usage}</td>"
            html_line += f"<td>{gsymbol}({headword})</td>"
            html_line += "</tr>"
            html_lines.append(html_line)

        # Assemble the full HTML for the entry
        entry_html = (
            html_header
            + html_header1
            + mlist
            + html_header2
            + "".join(html_lines)
            + "</tbody></table></div></body></html>"
        )
        html_dict[inflected_word] = entry_html

        if counter % 10000 == 0:
            pr.counter(counter, len(lookup_results), inflected_word)

    g.html_dict = html_dict
    pr.yes(len(g.html_dict))


def make_data_lists(g: ProgData):
    """Make the data_lists to be consumed by GoldenDict and MDict"""
    pr.green("making data lists")

    dict_data: list[DictEntry] = []
    # Use the refactored html_dict
    for word, html in g.html_dict.items():
        synonyms = add_niggahitas([word])

        dict_data += [
            DictEntry(
                word=word, definition_html=html, definition_plain="", synonyms=synonyms
            )
        ]

    g.dict_data = dict_data
    pr.yes("ok")


def prepare_gd_mdict_and_export(g: ProgData):
    """Prepare the metadata and export to goldendict, mdict & apple dictionary."""

    dict_info = DictInfo(
        bookname="Pali Grammar",
        author="Bodhirasa (+Chris Tham)",
        description="<h3>Pali Grammar</h3><p>Dictionary of Pali grammatical inflections with grammatical symbols, usage, meaning and construction</p>",
        website="https://github.com/ChristineTham/pali_grammar",
        source_lang="pi",
        target_lang="en",
    )
    dict_name = "pali-grammar"

    dict_vars = DictVariables(
        css_paths=[g.pth.dpd_css_and_fonts_path],
        js_paths=[g.pth.sorter_js_path],
        gd_path=g.pth.share_dir,
        md_path=g.pth.share_dir,
        dict_name=dict_name,
        icon_path=g.pth.dpd_logo_svg,
        font_path=g.pth.fonts_dir,
        zip_up=True,
        delete_original=False,
        apple_path=g.pth.share_dir,
    )

    if g.make_goldendict:
        export_to_goldendict_with_pyglossary(dict_info, dict_vars, g.dict_data)

    if g.make_mdict:
        export_to_mdict(dict_info, dict_vars, g.dict_data)

    if g.make_appledict:
        export_to_appledict(
            dict_info,
            dict_vars,
            g.dict_data,
            install=g.install_appledict,
        )


if __name__ == "__main__":
    main()
