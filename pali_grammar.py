#!/usr/bin/env python3

"""Compile HTML table of all grammatical possibilities of every inflected word-form."""

import pickle

# from css_html_js_minify import css_minify, js_minify
from json import loads
from mako.template import Template

from db.db_helpers import get_db_session
from db.models import DpdHeadword
from db.models import InflectionTemplates
from db.models import Lookup

from exporter.goldendict.ru_components.tools.paths_ru import RuPaths
from exporter.goldendict.ru_components.tools.tools_for_ru_exporter import ru_replace_abbreviations

from tools.all_tipitaka_words import make_all_tipitaka_word_set
from tools.configger import config_test
from tools.deconstructed_words import make_words_in_deconstructions
from tools.goldendict_exporter import DictInfo, DictVariables, DictEntry
from tools.goldendict_exporter import export_to_goldendict_with_pyglossary
from tools.lookup_is_another_value import is_another_value
from tools.mdict_exporter import export_to_mdict
from tools.niggahitas import add_niggahitas
from tools.pali_sort_key import pali_sort_key
from tools.paths import ProjectPaths
from tools.printer import p_counter, p_green, p_green_title, p_title, p_yes
from tools.tic_toc import tic, toc
from tools.update_test_add import update_test_add
from tools.meaning_construction import summarize_construction
from pathlib import Path

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
    "x": "⚧",
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

    chunks = grammar.split(' ')
    return ''.join(map(lambda s: to_symbol.get(s, s), chunks))

class ProgData():
    def __init__(self) -> None:
        if config_test("dictionary", "make_mdict", "yes"):
            self.make_mdict = True
        else:
            self.make_mdict = False

        if config_test("exporter", "language", "en"):
            self.lang = "en"
        elif config_test("exporter", "language", "ru"):
            self.lang = "ru"
        else:
            raise ValueError("Invalid language parameter")

        self.pth = ProjectPaths()
        self.rupth = RuPaths()
        self.db_session = get_db_session(self.pth.dpd_db_path)
        self.db = self.load_db()
        self.headwords_list: list[str] = [i.lemma_1 for i in self.db]

        self.pth.grammar_css_path = Path("./pali_grammar/grammar.css")
        self.pth.grammar_dict_goldendict_dir = Path("./pali_grammar/pali-grammar")
        self.pth.grammar_dict_mdd_path = Path("./pali_grammar/pali-grammar-mdict.mdd")
        self.pth.grammar_dict_mdx_path = Path("./pali_grammar/pali-grammar-mdict.mdx")
        self.pth.grammar_dict_header_templ_path = Path("./pali_grammar/grammar_dict_header.html")
        self.pth.grammar_templ_path = Path("./pali_grammar/pali_grammar.html")
        self.pth.grammar_dict_output_dir =  Path("./pali_grammar/output")
        self.pth.grammar_dict_output_html_dir =  Path("./pali_grammar/output/html")
        self.pth.grammar_dict_pickle_path =  Path("./pali_grammar/output/grammar_dict_pickle")
        self.pth.grammar_dict_tsv_path =  Path("./pali_grammar/output/grammar_dict.tsv")
        self.pth.share_dir = Path("./pali_grammar/share")
        
        # types of words
        self.nouns = ["fem", "masc", "nt", ]
        self.verbs = ["aor", "cond", "fut", "imp", "imperf", "opt", "perf", "pr"]
        self.all_words_set: set

        # the grammar dictionaries
        self.grammar_dict: dict[str, list[tuple[str, str, str]]]
        self.grammar_dict_table: dict[str, list[tuple[str, str, str]]]
        self.grammar_dict_html: dict[str, str]

        # goldendict and mdict data_list
        self.dict_data: list[DictEntry]

    def load_db(self):
        db = self.db_session.query(DpdHeadword).all()
        return sorted(db, key=lambda x: pali_sort_key(x.lemma_1))
    
    def close_db(self):
        self.db_session.close()
    
    def commit_db(self):
        self.db_session.commit()


def main():
    tic()
    p_title("exporting Pali grammar dictionary")
    
    g = ProgData()

    modify_pos(g)
    make_sets_of_words(g)
    generate_grammar_dict(g)
    
    # dont commit the changes into the db
    g.close_db()
    g.load_db()
    
    save_pickle_and_tsv(g)
    add_to_lookup_table(g)
    make_data_lists(g)
    prepare_gd_mdict_and_export(g)

    toc()


def modify_pos(g: ProgData):
    """Modify parts of speech into general categories."""

    # modify parts of speech
    for i in g.db:
        if i.pos in g.nouns:
            i.pos = "noun"
        if i.pos in g.verbs:
            i.pos = "verb"
        if "adv" in i.grammar and i.pos != "sandhi":
            i.pos = "adv"
        if "excl" in i.grammar:
            i.pos = "excl"
        if "prep" in i.grammar:
            i.pos = "prep"
        if "emph" in i.grammar:
            i.pos = "emph"
        if "interr" in i.grammar:
            i.pos = "interr"


def make_sets_of_words(g: ProgData):
    """Make the set of all words to be used,
    all words in the tipitaka + all the words in deconstructed compounds"""

    # tipitaka word set
    p_green("all tipitaka words")
    tipitaka_word_set = make_all_tipitaka_word_set()
    p_yes(len(tipitaka_word_set))

    # word in deconstructed compounds
    p_green("all words in deconstructions")
    words_in_deconstructions_set = make_words_in_deconstructions(g.db_session)
    p_yes(len(words_in_deconstructions_set))

    # all words set
    p_green("all words set")
    g.all_words_set = tipitaka_word_set | words_in_deconstructions_set
    p_yes(len(g.all_words_set))


def render_header_templ(
        __pth__: ProjectPaths,
        css: str,
        js: str,
        header_templ: Template
) -> str:
    """render the html header with css and js"""

    return str(header_templ.render(css=css, js=js))


def generate_grammar_dict(g: ProgData):
    p_green_title("generating Pali grammar dictionary")

    # three grammar dicts will be generated here at the same time. 
    # 1. grammar_dict is pure data {inflection: [(headword, pos, grammar)]}
    # 2. grammar_dict_table is just an html table {inflection: "html"}
    # 3. grammar_dict_html is full html page with header, style etc. {inflection: "html"}

    grammar_dict = {}
    grammar_dict_table = {}
    grammar_dict_html = {}

    # create the header from a template
    header_templ = Template(filename=str(g.pth.grammar_dict_header_templ_path))
    html_header1 = render_header_templ(
        g.pth, css="", js="", header_templ=header_templ)
    html_header1 += "<body><div class='grammar_dict'>"
    html_header2 = "<table class='grammar_dict'>"
    html_header2 += "<thead><tr><th id='col1'>pos ⇅</th><th id='col2'>⇅</th><th id='col3'>⇅</th><th id='col4'>⇅</th><th id='col5'>meaning ⇅</th><th id='col6'>word ⇅</th></tr></thead><tbody>"
    
    html_table_header1 = "<body><div class='dpd_grammar'>"
    html_table_header2 = "<table class='dpd_grammar'>"

    # process the inflections of each word in DpdHeadword
    for counter, i in enumerate(g.db):
        mlist = "<ul>"
        mlist += f"<li>{summarize_construction(i)}</li>"
        if i.meaning_1:
            mlist += f"<li>{i.meaning_1}</li>"
        if i.meaning_2:
            mlist += f"<li>[alt] {i.meaning_2}</li>"
        if i.meaning_lit:    
            mlist += f"<li>[lit] {i.meaning_lit}</li>"
        mlist += "</ul>"

        # words with ! in the stem are inflected forms 
        # and wil get dealt with under the main headwords 
        if "!" in i.stem:
            pass
        
        # words with '*' in stem are irregular inflections, remove the * for clean processing. 
        if i.stem == "*":
            i.stem = ""
        
        # process indeclinables
        if i.stem == "-":
            continue
            data_line = (i.lemma_clean, i.pos, "indeclinable")
            html_line = f"<tr><td><b>{i.pos}</b></td><td colspan='4'>indeclinable</td><td>🔼({i.lemma_clean})</td></tr>"

            # grammar_dict update
            if i.lemma_clean not in grammar_dict:
                grammar_dict[i.lemma_clean] = [data_line]
            else:
                if data_line not in grammar_dict[i.lemma_clean]:
                    grammar_dict[i.lemma_clean].append(data_line)

            # grammar_dict_html update
            if i.lemma_clean not in grammar_dict_html:
                grammar_dict_html[i.lemma_clean] = f"{html_header1}{mlist}{html_header2}{html_line}"
                grammar_dict_table[i.lemma_clean] = f"{html_table_header1}{mlist}{html_table_header2}{html_line}"
            else:
                if html_line not in grammar_dict_html[i.lemma_clean]:
                    grammar_dict_html[i.lemma_clean] += html_line
                    grammar_dict_table[i.lemma_clean] += html_line

        # all other words need an inflection table generated 
        # to find out their grammatical category, i.e. masc nom sg
        else:
            # get template
            template = g.db_session \
                .query(InflectionTemplates) \
                .filter(InflectionTemplates.pattern == i.pattern) \
                .first()

            if template is not None:
                template_data = loads(template.data)
                
                # data is a nest of lists
                # list[] table
                # list[[]] row
                # list[[[]]] cell
                # row 0 is the top header
                # column 0 is the grammar header
                # odd rows > 0 are inflections
                # even rows > 0 are grammar info

                for row_number, row_data in enumerate(template_data):
                    for column_number, cell_data in enumerate(row_data):

                        if (
                            row_number > 0                      #   skip the top header
                            and column_number > 0               #   skip the side header
                            and column_number % 2 == 1          #   skip even numbers = grammar info 
                            and row_data[0][0] != "in comps"    #   skip this row
                        ):
                            grammar: str = [row_data[column_number+1]][0][0]
                            gsymbol = get_symbols(grammar)
                            case_usage = ''.join([val for key, val in to_meaning.items() if key in grammar])

                            for inflection in cell_data:
                                if inflection:
                                    inflected_word = f"{i.stem}{inflection}"
                                    if inflected_word in g.all_words_set:

                                        data_line = (i.lemma_clean, i.pos, grammar)
                                        html_line = "<tr>"
                                        html_line += f"<td><b>{i.pos}</b></td>"
                                        # get grammatical_categories from grammar
                                        grammatical_categories = []
                                        if grammar.startswith("reflx"):
                                            grammatical_categories.append(grammar.split()[0] + " " + grammar.split()[1])
                                            grammatical_categories += grammar.split()[2:]
                                            for grammatical_category in grammatical_categories:
                                                html_line += f"<td>{grammatical_category}</td>"
                                        elif grammar.startswith("in comps"):
                                            html_line += f"<td colspan='3'>{grammar}</td>"
                                        else:
                                            grammatical_categories = grammar.split()
                                            # adding empty values if there are less than 3
                                            while len(grammatical_categories) < 3:
                                                grammatical_categories.append("")
                                            for grammatical_category in grammatical_categories:
                                                html_line += f"<td>{grammatical_category}</td>"
                                        html_line += f"<td>{case_usage}{'(' + i.plus_case + ') ' if i.plus_case else ''}</td>"
                                        html_line += f"<td>{gsymbol}({i.lemma_clean})</td>"
                                        html_line += "</tr>"

                                        # grammar_dict update
                                        if inflected_word not in grammar_dict:
                                            grammar_dict[inflected_word] = [data_line]
                                        else:
                                            if data_line not in grammar_dict[inflected_word]:
                                                grammar_dict[inflected_word].append(data_line)

                                        # grammar_dict_html update
                                        if inflected_word not in grammar_dict_html:
                                            grammar_dict_html[inflected_word] = f"{html_header1}{mlist}{html_header2}{html_line}"
                                            grammar_dict_table[inflected_word] = f"{html_table_header1}{mlist}{html_table_header1}{html_line}"
                                        else:
                                            if html_line not in grammar_dict_html[inflected_word]:
                                                grammar_dict_html[inflected_word] += html_line
                                                grammar_dict_table[inflected_word] += html_line

        if counter % 5000 == 0:
            p_counter(counter, len(g.db), i.lemma_1)

    if g.lang == "ru":

        # !!! FIXME very slow!

        print_counter = 0
        p_green("replacing abbreviations: en > ru")
        for inflected_word, html_content in grammar_dict_html.items():
            # Replace abbreviations in each HTML line
            html_lines = html_content.split('<tr>')
            for i, line in enumerate(html_lines):
                if line:
                    # Replace abbreviations in the line
                    line = ru_replace_abbreviations(line, kind="gram")
                    # Update the HTML lines with the modified line
                    html_lines[i] = line
            # Join the modified lines back into a single HTML string
            grammar_dict_html[inflected_word] = '<tr>'.join(html_lines)

            print_counter += 1
            if print_counter % 5000 == 0:
                p_counter(print_counter, len(grammar_dict_html), inflected_word)


    # clean up the html
    # FIXME what about using Jinja template here?

    for item in grammar_dict_html:
        grammar_dict_html[item] += "</table></div></body></html>"

    for item in grammar_dict_table:
        grammar_dict_table[item] += "</table></div>"

    # FIXME find out how to remove headings from table with only 1 row

    for item in grammar_dict_table:
        grammar_dict_table[item] += "</tbody></table></div>"
    
    g.grammar_dict = grammar_dict
    g.grammar_dict_table = grammar_dict_table
    g.grammar_dict_html = grammar_dict_html

    p_yes(len(g.grammar_dict))


def save_pickle_and_tsv(g: ProgData):
    """Save in pickle and tsv formats for external use."""

    # save pickle file
    p_green("saving grammar_dict pickle")
    with open(g.pth.grammar_dict_pickle_path, "wb") as f:
        pickle.dump(g.grammar_dict, f)
    p_yes("ok")
    
    # save tsv of inflection and table
    p_green("saving grammar_dict tsv")
    with open(g.pth.grammar_dict_tsv_path, "w") as f:
        f.write("inflection\thtml\n")
        for inflection, table in g.grammar_dict_table.items():
            f.write(f"{inflection}\t{table}\n")
    p_yes("ok")


def add_to_lookup_table(g: ProgData):
    """Add the grammar dict items to the Lookup table."""

    p_green("saving to Lookup table")

    lookup_table = g.db_session.query(Lookup).all()
    results = update_test_add(lookup_table, g.grammar_dict)
    update_set, test_set, add_set = results

    # update test add
    for i in lookup_table:
        if i.lookup_key in update_set:
            i.grammar_pack(g.grammar_dict[i.lookup_key])
        elif i.lookup_key in test_set:
            if is_another_value(i, "grammar"):
                i.grammar = ""
            else:
                g.db_session.delete(i)                
    
    g.commit_db()

    # add
    add_to_db = []
    for inflection, grammar_data in g.grammar_dict.items():
        if inflection in add_set:
            add_me = Lookup()
            add_me.lookup_key = inflection
            add_me.grammar_pack(grammar_data)
            add_to_db.append(add_me)

    g.db_session.add_all(add_to_db)
    g.commit_db()
    p_yes("ok")


def make_data_lists(g: ProgData):
    """Make the data_lists to be consumed by GoldenDict and MDict"""
    p_green("making data lists")

    dict_data: list[DictEntry] = []
    for word, html in g.grammar_dict_html.items():
        synonyms = add_niggahitas([word])

        dict_data += [DictEntry(
            word=word,
            definition_html=html,
            definition_plain="",
            synonyms=synonyms
        )]

    g.dict_data = dict_data
    p_yes("ok")


def prepare_gd_mdict_and_export(g: ProgData):
    """Prepare the metadata and export to goldendict & mdict."""

    if g.lang == "en":
        dict_info = DictInfo(
            bookname = "Pali Grammar",
            author = "Bodhirasa (+Chris Tham)",
            description = "<h3>Pali Grammar</h3><p>Pali Grammar Dictionary with grammatical symbols, case usage, meaning and construction</p>",
            website = "https://github.com/ChristineTham/pali_grammar",
            source_lang = "pi",
            target_lang = "en"
        )
        dict_name = "pali-grammar"
    
    elif g.lang == "ru":
        dict_info = DictInfo(
            bookname = "Pali Грамматика",
            author = "Дост. Бодхираса",
            description = "<h3>DPD Грамматика</h3><p>Таблица всех грамматических возможностей, которыми может обладать определенное слово в склонении или спряжении. Для получения дополнительной информации посетите <a href='https://digitalpalidictionary.github.io/rus/grammardict.html' target='_blank'>веб-сайт DPD</a>.</p>",
            website = "https://github.com/ChristineTham/pali_grammar",
            source_lang = "pi",
            target_lang = "ru"
        )
        dict_name = "ru-pali-grammar"

    dict_vars = DictVariables(
        css_path=g.pth.grammar_css_path,
        js_paths=[g.pth.sorter_js_path],
        gd_path=g.pth.share_dir,
        md_path=g.pth.share_dir,
        dict_name=dict_name,
        icon_path=g.pth.icon_path,
        zip_up=True,
        delete_original=False
    )

    export_to_goldendict_with_pyglossary(dict_info, dict_vars, g.dict_data)
    
    if g.make_mdict:
        export_to_mdict(dict_info, dict_vars, g.dict_data)
        

if __name__ == "__main__":
    main()
