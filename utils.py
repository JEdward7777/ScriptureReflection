"""
Utility functions.
Moved them here so that the scripts don't import eachother so much.
"""

import json
import os

def split_ref( reference ):
    """
    Splits a reference into book, chapter, and verse.
    """
    if " " not in reference:
        return reference, None, None
    last_space_index = reference.rindex(" ")
    book_split = reference[:last_space_index]
    chapter_verse_str = reference[last_space_index+1:]
    if ":" not in chapter_verse_str:
        return book_split, int(chapter_verse_str), None
    chapter_num,verse_num = chapter_verse_str.split(":")
    if "-" in verse_num:
        return book_split, int(chapter_num), verse_num
    return book_split, int(chapter_num), int(verse_num)


def load_jsonl(file):
    """
    Load a file with one JSON object per line.
    """
    with open(file, encoding='utf-8') as f:
        return [json.loads(line) for line in f]

def save_jsonl(filename, data):
    """
    Save a file with one JSON object per line.
    """
    if not os.path.exists(os.path.dirname(filename)):
        os.makedirs(os.path.dirname(filename))
    temp_filename = f"{filename}~"
    with open(temp_filename, 'w', encoding='utf-8') as f:
        for line in data:
            f.write(json.dumps(line, ensure_ascii=False) + '\n')
    os.replace(temp_filename, filename)

def load_json(file):
    """
    Load a file with one JSON object at the root.
    """
    with open(file, encoding='utf-8') as f:
        return json.load(f)

def save_json(filename, data, indent=4):
    """
    Save a file with one JSON object at the root.
    """
    if not os.path.exists(os.path.dirname(filename)):
        os.makedirs(os.path.dirname(filename))
    temp_filename = f"{filename}~"
    with open(temp_filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)
    os.replace(temp_filename, filename)


def look_up_key( data, keys ):
    """
    Look up a key in a nested dictionary.
    :param data: The dictionary to look up in.
    :param keys: The list of keys to look up.
    :return: The value at the key, or None if it doesn't exist.
    """
    for key in keys:
        if key in data:
            data = data[key]
        else:
            return None
    return data

def set_key( data, keys, value ):
    """
    Set a key in a nested dictionary.
    :param data: The dictionary to set in.
    :param keys: The list of keys to set.
    :param value: The value to set.
    """
    for key in keys[:-1]:
        if key not in data:
            data[key] = {}
        data = data[key]
    data[keys[-1]] = value

def get_overridden_references(translation, reference_key, override_key):
    """Find references that have been overridden"""
    overridden_references = []
    if override_key:
        last_reference = None
        for verse in translation:
            reference = look_up_key( verse, reference_key )
            if last_reference:
                is_override = look_up_key( verse, override_key )
                if is_override:
                    overridden_references.append( last_reference )
            last_reference = reference
    return overridden_references