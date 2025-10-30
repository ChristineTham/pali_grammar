#!/usr/bin/env python3

"""Outputs a cspell custom dictionary called 'pali.txt'"""

from pathlib import Path

from db.db_helpers import get_db_session
from db.models import Lookup
from tools.paths import ProjectPaths
from tools.printer import printer as pr


class ProgData:
    def __init__(self) -> None:
        self.pth = ProjectPaths()
        self.db_session = get_db_session(self.pth.dpd_db_path)

    def close_db(self):
        self.db_session.close()


def main():
    pr.tic()
    pr.title("generating Cspell custom dictionary")

    g = ProgData()

    # Query the Lookup table for entries with grammar data
    pr.green("querying database")
    lookup_results = (
        g.db_session.query(Lookup)
        .filter(Lookup.grammar.is_not(None), Lookup.grammar != "")
        .all()
    )
    pr.yes(f"{len(lookup_results)}")

    g.close_db()

    pr.green("writing share/pali.txt")
    output_path = Path("share/pali.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        for entry in lookup_results:
            f.write(f"{entry.lookup_key}\n")
    pr.yes(f"dictionary written to {output_path}")

    pr.toc()


if __name__ == "__main__":
    main()
