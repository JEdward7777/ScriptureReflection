"""
Utility functions.
Moved them here so that the scripts don't import eachother so much.
"""

import json
import os
import time
from typing import Callable, Any
import functools

import yaml


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

def split_ref2( reference ):
    book, chapter, verse = split_ref( reference )
    if isinstance( verse, str) and "-" in verse:
        start_verse, end_verse = [int(x) for x in verse.split('-')]
        return book, chapter, start_verse, end_verse
    return book, chapter, verse, verse

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

def load_json(file, default=None):
    """
    Load a file with one JSON object at the root.
    If the file does not exist, return the default instead.
    """
    try:
        with open(file, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        if default is None:
            raise
        return default

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


def look_up_key( data, keys, default=None, none_is_valid=True ):
    """
    Look up a key in a nested dictionary. Which can have arrays in it.
    :param data: The dictionary to look up in.
    :param keys: The list of keys to look up.
    :return: The value at the key, or None if it doesn't exist.
    """
    for key in keys:
        if isinstance(data, list):
            if key < 0 or key >= len(data):
                return default
            data = data[key]
        elif isinstance(data, dict) and key in data:
            data = data[key]
        else:
            return default

    if data is None and not none_is_valid:
        return default

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
    overridden_references = {}
    if override_key:
        last_reference = None
        for verse in translation:
            reference = look_up_key( verse, reference_key )
            if last_reference:
                is_override = look_up_key( verse, override_key )
                if is_override:
                    overridden_references[last_reference] = reference
            last_reference = reference

    #If you have a verse range with more than two verses, update the pointers
    #on the base verse to point to the end instead of being a linked list.
    updated_references = {}
    for k,v in overridden_references.items():
        while v in overridden_references:
            v = overridden_references[v]
        updated_references[k] = v

    return updated_references

def load_file_to_list(file_path: str) -> list[str]:
    """
    Load a file and return its contents as a list of strings, one for each line.
    """
    with open(file_path, encoding='utf-8') as f:
        return f.read().splitlines()


class Tee:
    """
    A class that writes to multiple files.
    """
    def __init__(self, *files):
        self.files = files

    def write(self, message):
        """
        Write a message to all files.
        """
        for f in self.files:
            f.write(message)

    def flush(self):
        """
        Flushes all files.
        """
        for f in self.files:
            f.flush()


class GetStub:
    """
    A stub class that has a get method that returns a default value.
    """
    def get( self, _, default=None ):
        """Returns the default value"""
        if default is None:
            return self
        return default


def load_yaml_configuration( file ):
    """
    loads the specific yaml configuration
    and returns a stub if it doesn't exist.
    """
    if not os.path.exists(file):
        return GetStub()
    with open( file, encoding='utf-8' ) as f:
        return yaml.load(f, Loader=yaml.FullLoader)
    return None


def use_model( client, model, messages, temperature, top_p, response_format ):
    """This calls ChatGPT but wraps it in a try/catch to auto rehandle exceptions."""

    finished = False
    while not finished:
        try:
            completion = client.beta.chat.completions.parse(
                model=model,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                response_format=response_format,
                timeout=120,
            )

            finished = True
        except Exception as e: # pylint: disable=broad-except
            print(f"Error calling the model in use_model: {e}")
            print("Retrying...")
            time.sleep(5)

    return completion

def get_changes( value_old, value_new ):
    changes = []

    if type(value_old) == dict and type(value_new) == dict:
        for key, old_value in value_old.items():
            if key not in value_new:
                changes.append( ['delete', [key]] )
            else:
                new_value = value_new[key]
                if type(new_value) in [dict, list]:
                    for sub_change in get_changes( old_value, new_value ):
                        sub_change[1] = [key] + sub_change[1]
                        changes.append( sub_change )
                else:
                    if new_value != old_value:
                        changes.append( ['update', [key], new_value] )

        for key, new_value in value_new.items():
            if key not in value_old:
                if type(new_value) == dict:
                    for sub_change in get_changes( {}, new_value ):
                        sub_change[1] = [key] + sub_change[1]
                        changes.append( sub_change )
                elif type(new_value) == list:
                    for sub_change in get_changes( [], new_value ):
                        sub_change[1] = [key] + sub_change[1]
                        changes.append( sub_change )
                else:
                    changes.append( ['add', [key], new_value] )

    elif type(value_old) == list and type(value_new) == list:
        for i in range( min( len(value_old), len(value_new) ) ):
            for sub_change in get_changes( value_old[i], value_new[i] ):
                sub_change[1] = [i] + sub_change[1]
                changes.append( sub_change )
        if len(value_old) > len(value_new):
            for i in range( len(value_old)-1, len(value_new)-1, -1 ):
                changes.append( ['delete', [i]] )
        if len(value_old) < len(value_new):
            for i in range( len(value_old), len(value_new), 1 ):
                #Before adding the first index we have to identify
                #This as an array so we will touch it.
                if i == 0:
                    changes.append( ['touch_array', []] )
                if type( value_new[i] ) == dict:
                    for sub_change in get_changes( {}, value_new[i] ):
                        sub_change[1] = [i] + sub_change[1]
                        changes.append( sub_change )
                elif type( value_new[i] ) == list:
                    for sub_change in get_changes( [], value_new[i] ):
                        sub_change[1] = [i] + sub_change[1]
                        changes.append( sub_change )
                else:
                    changes.append( ['add', [i], value_new[i]] )

    else:
        if value_new != value_old:
            changes.append( ['update', [], value_new] )


    return changes


def apply_changes( dict_old, changes ):
    for change in changes:
        command = change[0]
        keys = change[1]

        if len( keys ) > 1:
            sub_change = change.copy()
            if type( dict_old ) == list:
                while len( dict_old ) <= keys[0]:
                    dict_old.append( {} )
            else:
                if command == 'add' and keys[0] not in dict_old:
                    dict_old[keys[0]] = {}
            sub_change[1] = keys[1:]
            apply_changes( dict_old[keys[0]], [sub_change] )
        else:
            if command == 'delete':
                del dict_old[keys[0]]
            elif command == 'touch_array':
                if type( dict_old ) == list:
                    while keys[0] >= len( dict_old ):
                        dict_old.append( [] )
                else:
                    if keys[0] not in dict_old:
                        dict_old[keys[0]] = []
            elif command in ['update', 'add']:
                new_value = change[2]
                if type(dict_old) == list:
                    while keys[0] >= len(dict_old):
                        dict_old.append( {} )
                dict_old[keys[0]] = new_value

    #don't need to use the returned value
    #because the input value wasn't cloned.
    return dict_old

def hash_array_by_key( data, key ):
    """
    Creates a dictionary out of an array of objects by using the value from
    each object at the specified key as the key in the dictionary.

    :param data: The data to be hashed.
    :param key: The key to use for hashing.
    :return: A dictionary where the keys are the values from the input data
             using the specified key, and the values are the objects from the
             input data.
    """
    return { look_up_key( x, key ): x for x in data }

def save_jsonl_updates(filename, data, unmodifed_data, reference_key ):
    """
    Saves out the updated data to the file, while leaving any of the verses that weren't modified
    in their original state. This means that if other people have modified the file since we last saw it,
    their changes will be preserved.

    :param filename: The name of the jsonl file to save.
    :param data: The updated data.
    :param unmodifed_data: The original data.
    :param reference_key: The key to use to find the particular verse in the data.
    :return: The updated data that was saved.
    """

    if os.path.exists(filename):
        data_hashed = hash_array_by_key( data, reference_key )
        unmodified_hashed = hash_array_by_key( unmodifed_data, reference_key )


        changes_hashed = {}
        for vref, modified in data_hashed.items():
            if vref and vref in unmodified_hashed:
                changes = get_changes( unmodified_hashed[vref], modified )
                if len(changes) > 0:
                    changes_hashed[vref] = changes

        fresh_loaded = load_jsonl(filename)
        fresh_hashed = hash_array_by_key( fresh_loaded, reference_key )

        
        #now apply the changes.
        for vref, changes in changes_hashed.items():
            if vref in fresh_hashed:
                apply_changes( fresh_hashed[vref], changes )

        #Then save it back out.
        save_jsonl(filename, fresh_loaded)
    else:
        #If the file doesn't exist, just save the new data.
        save_jsonl(filename, data)
        fresh_loaded = data

    return fresh_loaded


def normalize_ranges( content, reference_key, translation_key, source_key ):
    """
    Normalize a list of verses such that if there are any ranges (<range> in the source or translation)
    it will combine the previous verse with the current one (if there is one) into a single verse
    with a combined reference and source and translation.

    The idea is that if there are any ranges in the source or translation, this function will
    combine the previous verse with the current one into a single verse with a combined reference
    and source and translation.  If there are not any ranges, then the result is the same as the
    input.

    This function assumes that the input verses are sorted in the correct order.

    :param content: The list of verses to normalize.
    :param reference_key: The key to look for the reference in the verse objects.
    :param translation_key: The key to look for the translation in the verse objects.
    :param source_key: The key to look for the source in the verse objects.
    :return: A list of verses with any ranges combined into a single verse.
    """
    normalized = []
    for this_verse in content:
        this_translation = look_up_key( this_verse, translation_key, default="" ).strip()
        this_source = look_up_key( this_verse, source_key, default="" ).strip()
        if this_translation == "<range>" or this_source == "<range>" and len(normalized) > 0:
            last_verse = normalized.pop(-1)

            #combine the reference.
            last_reference = look_up_key( last_verse, reference_key )
            this_reference = look_up_key( this_verse, reference_key )
            last_book, last_chapter, last_start_verse, _              = split_ref2( last_reference )
            this_book, this_chapter, _               , this_end_verse = split_ref2( this_reference )
            assert last_book == this_book, "Ranges across books not supported."
            assert last_chapter == this_chapter, "Ranges across chapters not supported."
            reference = f"{last_book} {last_chapter}:{last_start_verse}-{this_end_verse}"

            #combine the source
            last_source = look_up_key( last_verse, source_key, default="" )
            if this_source == "<range>":
                source = last_source
            else:
                source = (last_source + "\n" + this_source).strip()

            #combine the translation
            last_translation = look_up_key( last_verse, translation_key, default="" )
            if this_translation == "<range>":
                translation = last_translation
            else:
                translation = (last_translation + "\n" + this_translation).strip()

            #now create the new structure.
            #combined_verse = copy.deepcopy( this_verse )
            combined_verse = {}
            set_key( combined_verse, reference_key, reference )
            if source:
                set_key( combined_verse, source_key, source )
            if translation:
                set_key( combined_verse, translation_key, translation )

            #add it to the result
            normalized.append( combined_verse )
        else:
            normalized.append( this_verse )
    return normalized

         
def cache_decorator(cache_key: str, enabled: bool) -> Callable:
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            if enabled:
                # Create a unique key from function arguments
                arg_key = str(args) + str(kwargs)
                
                # Load cache from JSON file
                cache_file = f"{cache_key}.json"
                cache = load_json(cache_file, {})
                
                # Check if result is in cache
                if arg_key in cache:
                    return cache[arg_key]
                
                # Call the function and cache the result
                result = func(*args, **kwargs)
                cache[arg_key] = result
                save_json(cache_file, cache)
                
                return result
            else:
                return func(*args, **kwargs)
        return wrapper
    return decorator
