# pali_grammar

Dictionary of Pali grammatical inflections with grammatical symbols, usage, meaning and construction, based on Digital Pali Dictionary

1. Clone this repo

```shell
git clone https://github.com/ChristineTham/pali_grammar.git
```

2. Install [uv](https://docs.astral.sh/uv/) for your operating system

3. Install all the dependencies with uv

```shell
uv sync
```

4. Download latest version of dpd.db.tar.bz2 from [dpd-db releases page](https://github.com/digitalpalidictionary/dpd-db/releases)

```shell
tar xvf dpd.db.tar.bz2
```

That should create an SQLite database `dpd.db` in the project folder which can be accessed with [DB Browser](https://sqlitebrowser.org/), [DBeaver](https://dbeaver.io/), through [SQLAlchemy](https://www.sqlalchemy.org/) or your preferred method.

5. Now, generate Pali grammar dictionary

```shell
uv run main.py
```

The dictionaries are located in `share` folder. Copy them to your favourite dictionary program in the same way as DPD dictionaries.

Enjoy!
