#!/usr/bin/env python3
"""
Export Pali Grammar Dictionary to sharded JSON for static web deployment.
Extracts inflected and uninflected words from dpd.db, applying the textbook grammar
symbols, integrates compound/sandhi deconstructions from digitalpalidictionary/deconstructor_output,
and partitions into balanced range shards for O(1) binary search lookup.
"""

import argparse
import io
import json
import os
import re
import sqlite3
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

from tools.meaning_construction import make_meaning_combo_html, summarize_construction


class DummyWord:
    __slots__ = (
        "id",
        "lemma_1",
        "lemma_2",
        "pos",
        "meaning_1",
        "meaning_lit",
        "meaning_2",
        "construction",
        "root_base",
        "origin",
        "root_key",
        "root_sign",
        "family_root",
        "family_word",
    )

    def __init__(self, r):
        (
            self.id,
            self.lemma_1,
            self.lemma_2,
            self.pos,
            self.meaning_1,
            self.meaning_lit,
            self.meaning_2,
            self.construction,
            self.root_base,
            self.origin,
            self.root_key,
            self.root_sign,
            self.family_root,
            self.family_word,
        ) = r

    @property
    def root_clean(self):
        return re.sub(r" \d.*$", "", self.root_key) if self.root_key else ""


def load_deconstructor_data(
    decon_tar_path: Path | None,
    con: sqlite3.Connection,
    auto_download: bool = True,
) -> dict[str, list[str]]:
    """
    Load deconstructor output mapping: word -> list of splits.
    Tries:
    1. Specified or default tar.gz file
    2. Auto-download from GitHub if auto_download is True
    3. Fallback to lookup.deconstructor in dpd.db
    """
    url = "https://raw.githubusercontent.com/digitalpalidictionary/deconstructor_output/main/deconstructor_output.json.tar.gz"

    if decon_tar_path and decon_tar_path.exists():
        print(f"   Loading deconstructor from local tar archive: {decon_tar_path}")
        try:
            with tarfile.open(decon_tar_path, "r:gz") as tar:
                f = tar.extractfile(tar.getmember("deconstructor_output.json"))
                if f:
                    data = json.load(f)
                    print(f"   Loaded {len(data)} deconstructions from {decon_tar_path.name}")
                    return data
        except Exception as e:
            print(f"   Warning: Failed to load from {decon_tar_path}: {e}")

    if auto_download and decon_tar_path:
        print(f"   Downloading deconstructor output from {url}...")
        try:
            decon_tar_path.parent.mkdir(parents=True, exist_ok=True)
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req) as resp:
                content = resp.read()
                with open(decon_tar_path, "wb") as f_out:
                    f_out.write(content)
            print(f"   Saved {len(content) / (1024*1024):.1f} MB to {decon_tar_path}")
            with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as tar:
                f = tar.extractfile(tar.getmember("deconstructor_output.json"))
                if f:
                    data = json.load(f)
                    print(f"   Loaded {len(data)} deconstructions from download")
                    return data
        except Exception as e:
            print(f"   Warning: Download failed: {e}. Falling back to dpd.db...")

    print("   Loading deconstructor data from dpd.db lookup table...")
    cur = con.cursor()
    cur.execute("SELECT lookup_key, deconstructor FROM lookup WHERE deconstructor != ''")
    decon_map = {}
    for k, v in cur.fetchall():
        if not k:
            continue
        try:
            splits = json.loads(v) if v else []
            if splits:
                decon_map[k.strip()] = splits
        except Exception:
            pass
    print(f"   Loaded {len(decon_map)} deconstructions from dpd.db")
    return decon_map


def export_web_dict(
    out_dir: Path,
    chunk_size: int = 1500,
    limit: int | None = None,
    decon_tar_path: Path | None = Path("./share/deconstructor_output.json.tar.gz"),
    include_deconstructor: bool = True,
):
    t_start = time.time()
    out_dir = Path(out_dir)
    print("=== Pali Grammar Static Web Dictionary Exporter ===")
    print(f"Output directory: {out_dir}")
    print(f"Chunk size: {chunk_size}")
    print(f"Include deconstructor: {include_deconstructor}")

    db_path = Path("dpd.db")
    if not db_path.exists():
        print(f"Error: {db_path} not found in current directory.", file=sys.stderr)
        sys.exit(1)

    con = sqlite3.connect(db_path)
    cur = con.cursor()

    # 1. Load and precompute headwords
    print("1. Loading headwords from database...")
    t0 = time.time()
    cur.execute("""
        SELECT id, lemma_1, lemma_2, pos, meaning_1, meaning_lit, meaning_2,
               construction, root_base, origin, root_key, root_sign, family_root, family_word
        FROM dpd_headwords
    """)
    rows = cur.fetchall()
    print(f"   Loaded {len(rows)} headwords in {time.time()-t0:.2f}s")

    print("2. Precomputing headword summaries...")
    t0 = time.time()
    hw_cache = {}
    for r in rows:
        w = DummyWord(r)
        l1 = w.lemma_1 or ""
        l2 = w.lemma_2 or ""
        if l2 == l1:
            l2 = ""
        c_sum = summarize_construction(w) or ""
        m_html = make_meaning_combo_html(w) or ""
        hw_cache[w.id] = [l1, l2, c_sum, m_html]
    print(f"   Precomputed {len(hw_cache)} headwords in {time.time()-t0:.2f}s")

    # 2. Query Lookup entries
    print("3. Querying lookup entries with grammar or meanings...")
    t0 = time.time()
    query = """
        SELECT lookup_key, grammar, headwords
        FROM lookup
        WHERE (grammar IS NOT NULL AND grammar != '')
           OR (headwords IS NOT NULL AND headwords != '' AND headwords != '[]')
    """
    if limit:
        query += f" LIMIT {limit}"

    cur.execute(query)
    lookup_results = cur.fetchall()
    print(f"   Fetched {len(lookup_results)} raw lookup rows in {time.time()-t0:.2f}s")

    # 3. Load deconstructor data if requested
    decon_map = {}
    if include_deconstructor:
        print("4. Loading compound & sandhi deconstructor data...")
        t0 = time.time()
        decon_map = load_deconstructor_data(decon_tar_path, con)
        print(f"   Finished deconstructor loading in {time.time()-t0:.2f}s")

    # 4. Process entries into compact dictionary
    print("5. Compiling compact dictionary entries...")
    t0 = time.time()
    word_dict = {}

    for key, grammar_json, headwords_json in lookup_results:
        if not key:
            continue
        key = key.strip()
        # Filter out abbreviation keys like DN1, AN10.222, etc.
        if not key or re.match(r"^[A-Z0-9]", key):
            continue

        try:
            hw_ids = json.loads(headwords_json) if headwords_json else []
        except Exception:
            hw_ids = []

        hws = [hw_cache[hid] for hid in hw_ids if hid in hw_cache]

        has_meaning = any(h[3] for h in hws)
        try:
            g_raw = json.loads(grammar_json) if grammar_json else []
        except Exception:
            g_raw = []

        has_grammar = bool(g_raw)
        has_decon = key in decon_map

        if not has_meaning and not has_grammar and not has_decon:
            continue

        compact_g = []
        if g_raw:
            for g in g_raw:
                compact_g.append([g[1], g[2], g[0]])

        if has_decon:
            word_dict[key] = [hws, compact_g, decon_map[key]]
        else:
            word_dict[key] = [hws, compact_g]

    # Add remaining deconstructor-only entries
    if decon_map and not limit:
        print("   Adding compound & sandhi deconstructor entries...")
        decon_added = 0
        for k, splits in decon_map.items():
            if not k:
                continue
            k = k.strip()
            if k in word_dict:
                continue
            # Filter out non-word keys
            if re.match(r"^[A-Z0-9]", k) or not splits:
                continue
            # Pure deconstruction entries are stored as a flat list of splits: ["part1 + part2", ...]
            word_dict[k] = splits
            decon_added += 1
        print(f"   Added {decon_added} pure deconstructor entries")

    con.close()
    print(f"   Compiled total {len(word_dict)} valid dictionary entries in {time.time()-t0:.2f}s")

    # 5. Partition into balanced range shards
    print("6. Partitioning into balanced range shards...")
    sorted_keys = sorted(word_dict.keys())
    chunks = [sorted_keys[i : i + chunk_size] for i in range(0, len(sorted_keys), chunk_size)]

    out_dir.mkdir(parents=True, exist_ok=True)

    manifest_boundaries = []
    manifest_files = []

    print(f"7. Writing {len(chunks)} shard files to {out_dir}...")
    t0 = time.time()
    for idx, chunk_keys in enumerate(chunks):
        file_id = f"d{idx:04d}"
        file_name = f"{file_id}.json"
        shard_path = out_dir / file_name

        shard_data = {k: word_dict[k] for k in chunk_keys}
        with open(shard_path, "w", encoding="utf-8") as f:
            json.dump(shard_data, f, ensure_ascii=False, separators=(",", ":"))

        manifest_boundaries.append(chunk_keys[0])
        manifest_files.append(file_id)

    # Clean up old extraneous shards if previous run had more shards
    for old_file in out_dir.glob("d*.json"):
        fid = old_file.stem
        if fid not in manifest_files:
            try:
                old_file.unlink()
            except OSError:
                pass

    # 6. Write manifest.json
    manifest = {
        "version": "1.1",
        "total_words": len(word_dict),
        "total_shards": len(chunks),
        "chunk_size": chunk_size,
        "boundaries": manifest_boundaries,
        "files": manifest_files,
    }
    manifest_path = out_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"   Wrote all shards and manifest in {time.time()-t0:.2f}s")
    print(f"   Manifest: {manifest_path} ({manifest_path.stat().st_size / 1024:.1f} KB)")
    print(f"=== Complete! Total elapsed time: {time.time()-t_start:.2f}s ===")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Export Pali Grammar dictionary with deconstructor to sharded JSON files for static web."
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("./share/web_dict"),
        help="Target directory to write JSON shards and manifest (default: ./share/web_dict)",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1500,
        help="Number of words per shard (default: 1500)",
    )
    parser.add_argument(
        "--deconstructor-tar",
        type=Path,
        default=Path("./share/deconstructor_output.json.tar.gz"),
        help="Path to deconstructor_output.json.tar.gz",
    )
    parser.add_argument(
        "--no-deconstructor",
        action="store_true",
        help="Skip deconstructor entries",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit entries for quick test run",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    export_web_dict(
        out_dir=args.out_dir,
        chunk_size=args.chunk_size,
        limit=args.limit,
        decon_tar_path=args.deconstructor_tar,
        include_deconstructor=not args.no_deconstructor,
    )


if __name__ == "__main__":
    main()
