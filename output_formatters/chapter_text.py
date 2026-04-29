"""
Output formatter that writes one plain-text file per chapter.

File naming: output/chapter_text/{output_file}/{index:02d}_{book}_{chapter}.txt
  where {index} is the canonical Bible book order (01-67).

Each verse is written as bare translation text with a blank line between verses.
"""

import os
import re
from collections import defaultdict

from format_utilities import get_config_for
import utils

# Canonical Bible book order index, keyed by the 3-letter USFM book code.
# Numbers match the prefix used in the USFM formatter (e.g. MAT → 41).
BOOK_ORDER = {
    "GEN": 1,  "EXO": 2,  "LEV": 3,  "NUM": 4,  "DEU": 5,
    "JOS": 6,  "JDG": 7,  "RUT": 8,  "1SA": 9,  "2SA": 10,
    "1KI": 11, "2KI": 12, "1CH": 13, "2CH": 14, "EZR": 15,
    "NEH": 16, "EST": 17, "JOB": 18, "PSA": 19, "PRO": 20,
    "ECC": 21, "SNG": 22, "ISA": 23, "JER": 24, "LAM": 25,
    "EZK": 26, "DAN": 27, "HOS": 28, "JOL": 29, "AMO": 30,
    "OBA": 31, "JON": 32, "MIC": 33, "NAM": 34, "HAB": 35,
    "ZEP": 36, "HAG": 37, "ZEC": 38, "MAL": 39,
    "MAT": 41, "MRK": 42, "LUK": 43, "JHN": 44, "ACT": 45,
    "ROM": 46, "1CO": 47, "2CO": 48, "GAL": 49, "EPH": 50,
    "PHP": 51, "COL": 52, "1TH": 53, "2TH": 54, "1TI": 55,
    "2TI": 56, "TIT": 57, "PHM": 58, "HEB": 59, "JAS": 60,
    "1PE": 61, "2PE": 62, "1JN": 63, "2JN": 64, "3JN": 65,
    "JUD": 66, "REV": 67,
}


def run(file):
    """
    Converts a JSONL translation file into one plain-text file per chapter.

    Output path:
        output/chapter_text/{output_file}/{index:02d}_{book}_{chapter}.txt

    Each verse is written as bare translation text separated by a blank line.
    """
    print(f"converting {file} to chapter_text format")

    this_config = get_config_for(file)
    if this_config is None:
        this_config = {}

    # Respect the same config keys used by other formatters.
    translation_key = this_config.get("translation_key", ["fresh_translation", "text"])
    reference_key   = this_config.get("reference_key",   ["vref"])
    override_key    = this_config.get("override_key",    ["forming_verse_range_with_previous_verse"])
    output_file     = this_config.get("output_file",     os.path.splitext(file)[0])

    chapter_text_config = this_config.get("chapter_text", {})
    start_line = chapter_text_config.get(
        "start_line", this_config.get("start_line", None)
    )
    end_line = chapter_text_config.get(
        "end_line", this_config.get("end_line", None)
    )
    collapse_whitespace = chapter_text_config.get("collapse_whitespace", False)

    original_content = utils.load_jsonl(f"output/{file}")

    # Mark verses that are overridden by ranges so we can drop them.
    verse_to_drop = utils.get_overridden_references(
        original_content, reference_key, override_key
    )

    # Organise verses: book → chapter → [verse, ...]
    book_to_chapter_to_verses = defaultdict(lambda: defaultdict(list))

    for verse_index, verse in enumerate(original_content):
        if start_line is not None and verse_index < start_line - 1:
            continue
        if end_line is not None and verse_index > end_line - 1:
            break

        if not verse:
            continue

        reference = utils.look_up_key(verse, reference_key)
        if reference is None or " " not in reference:
            continue

        if reference in verse_to_drop:
            print(f"Dropping verse {reference}")
            continue

        book, chapter_num, _ = utils.split_ref(reference)
        book_to_chapter_to_verses[book][chapter_num].append(verse)

    # Write output files.
    output_folder = f"output/chapter_text/{output_file}"
    os.makedirs(output_folder, exist_ok=True)

    for book, chapter_to_verses in book_to_chapter_to_verses.items():
        book_index = BOOK_ORDER.get(book, 0)

        for chapter_num, verses in chapter_to_verses.items():
            filename = f"{book_index:02d}_{book}_{chapter_num}.txt"
            filepath = os.path.join(output_folder, filename)

            with open(filepath, "w", encoding="utf-8") as chapter_out:
                if collapse_whitespace:
                    # Collapse all whitespace within each verse, then join all
                    # verses onto a single line separated by a single space.
                    parts = []
                    for verse in verses:
                        translation = utils.look_up_key(verse, translation_key, default="")
                        if translation is None:
                            translation = ""
                        translation = re.sub(r'\s+', ' ', translation).strip()
                        if translation:
                            parts.append(translation)
                    chapter_out.write(" ".join(parts))
                    chapter_out.write("\n")
                else:
                    first_verse = True
                    for verse in verses:
                        translation = utils.look_up_key(verse, translation_key, default="")
                        if translation is None:
                            translation = ""

                        if not first_verse:
                            chapter_out.write("\n")  # blank line between verses
                        chapter_out.write(translation.strip())
                        chapter_out.write("\n")
                        first_verse = False

    print(f"chapter_text output written to {output_folder}")
