"""
This module implements the easy_draft functionality for generating a draft of the Bible.
"""
import os
import time
import json
from openai import OpenAI
from pydantic import BaseModel
import yaml
import verse_parsing


with open( 'key.yaml', encoding='utf-8' ) as keys_f:
    api_key = yaml.load(keys_f, Loader=yaml.FullLoader)['openai_key']
client = OpenAI(api_key=api_key)

def split_ref( reference ):
    """
    Given a Bible reference, return the book, chapter, and verse.
    """
    if " " not in reference:
        return reference, None, None
    last_space_index = reference.rindex(" ")
    book_split = reference[:last_space_index]
    chapter_verse_str = reference[last_space_index+1:]
    if ":" not in chapter_verse_str:
        return book_split, int(chapter_verse_str), None
    chapter_num,verse_num = chapter_verse_str.split(":")
    return book_split, int(chapter_num), int(verse_num)

class Verse(BaseModel):
    """
    A single verse from the Bible.  Contains the reference and the text.
    """
    reference: str
    text: str


class Translation(BaseModel):
    """
    A translation of a verse from the Bible.  Contains the related verses,
    translation notes, and the translation itself.
    """
    thoughts_on_if_words_from_this_verse_should_come_before_words_from_previous_verse: str
    forming_verse_range_with_previous_verse: bool
    related_verses: list[Verse]
    translation_notes: str
    fresh_translation: Verse


def load_file_to_list(file_path: str) -> list[str]:
    """
    Load a file and return its contents as a list of strings, one for each line.
    """
    with open(file_path, encoding='utf-8') as f:
        return f.read().splitlines()


def generate_verse(
    vref: str,
    source: str,
    last_translation_dict: dict,
    model_name: str,
    target_language: str,
    temperature: float,
    top_p: float,
    max_verse_range: int,
    translation_command: str
) -> Translation:
    """
    Generate a fresh translation of a verse from the Bible.  Before the verse,
    quote 5 other verses from the Bible which use similar words which would be
    useful.
    """

    #going to time how long this takes.
    start_time = time.time()

    message = (f"Generate a fresh translation of {vref} in {target_language}.  Before the verse " +
      f"quote 5 other verses from the Bible in {target_language} which use similar words which " +
      "would be useful. Pay attention to the source text and don't plagiarize existing " +
      f"translations. {translation_command}")
    message += f"\nThe source text is: {vref}: {source}"
    if last_translation_dict:
        message += f"\nFor context the previous verse is: {last_translation_dict['vref']}: " + \
            f"{last_translation_dict['fresh_translation']['text']}"

        last_book, last_chapter, _ = split_ref(last_translation_dict['vrefs'][0])
        this_book, this_chapter, _ = split_ref(vref)

        allow_range = True

        #prevent ranging over max verse range
        if len(last_translation_dict['vrefs']) >= max_verse_range:
            allow_range = False

        #prevent ranging over chapter breaks.
        if last_book != this_book or last_chapter != this_chapter:
            allow_range = False

        if allow_range:
            message += f"\nIf the meaning or grammar of this verse {vref} is dependent on the " + \
                f"previous verse {last_translation_dict['vref']} to the extent that words or " + \
                "ideas from this verse need to be rearranged **before or within** the " + \
                "previous verse for the translation to make sense, indicate that this verse " + \
                "should be merged into a \"verse range.\"\nOnly suggest merging if such " + \
                "reordering is essential and results in a combined, cohesive translation " + \
                "where the individual verses can no longer be clearly identified.\nIf merging " + \
                "is not required, provide a standalone translation for this verse. Clearly " + \
                "state whether merging is needed using forming_verse_range_with_previous_verse."
        else:
            message += "\nSet forming_verse_range_with_previous_verse to false."
    else:
        message += "\nSet forming_verse_range_with_previous_verse to false."

    completion = client.beta.chat.completions.parse(
        model=model_name,
        messages=[
            {"role": "system", "content": "You are a Christian Bible translator with 30 years " +
            "of experience as a linguist who translates the Bible from a Conservative Christian " +
            "perspective."},
            {"role": "user", "content": message },
        ],
        temperature=temperature,
        top_p=top_p,
        response_format=Translation
    )

    result = completion.choices[0].message.parsed

    end_time = time.time()
    translation_time = end_time - start_time

    return result, translation_time


def run_config(config: dict, ebible_dir: str) -> None:
    """
    Run the configuration given to generate a draft of the Bible.

    This loads the source text and reference text from the ebible metadata
    directory, and then generates a fresh translation of the text from the
    source language to the target language.  Before generating each verse,
    it quotes the 5 other verses from the Bible which use similar words which
    would be useful.

    If the output file already exists, it loads the previous results from that
    file and uses them as a starting point.  The results are then saved to a
    temporary file until the end of the run, at which point the temporary file
    is renamed to the final output name.

    :param config: A dictionary of configuration options.
    :param ebible_dir: The path to the ebible metadata directory.
    :param config['start_line']: The one-based line number to start at.
    :param config['end_line']: The one-based line number to end at.
    :param config['source']: The source language (e.g. grc-grcbyz).
    :param config['target_language']: The target language (e.g. en).
    :param config['model']: The model to use for translation (e.g. gpt-4o-mini).
    :param config['output']: The output filename (without path).
    :param config['active']: A boolean indicating if this config should be run.
    """
    start_line = int(config['start_line']) -1
    end_line = int(config['end_line']) -1  #subtract one to make it zero based like lists.
    source = config['source']
    active = config['active']
    if not active:
        return

    vrefs = load_file_to_list( os.path.join( ebible_dir, 'metadata', 'vref.txt' ) )
    source = load_file_to_list( os.path.join( ebible_dir, 'corpus', source + '.txt' ) )
    out_filename = os.path.join( "output", config['output'] + ".txt" )
    out_filename_jsonl = os.path.join( "output", config['output'] + ".jsonl" )
    temp_out_filename = os.path.join( "output", config['output'] + "~.txt"  )
    temp_out_filename_jsonl = os.path.join( "output", config['output'] + "~.jsonl"  )
    max_verse_range = config.get( 'max_verse_range', 5 )
    previous_result = []
    previous_result_jsonl = []

    if os.path.exists( out_filename ):
        previous_result = load_file_to_list( out_filename )

    if os.path.exists( out_filename_jsonl ):
        previous_result_jsonl = load_file_to_list( out_filename_jsonl )

    os.makedirs( os.path.dirname( temp_out_filename ), exist_ok=True )

    with open( temp_out_filename_jsonl, 'w', encoding="utf-8" ) as jsonl_output_file:
        with open( temp_out_filename, 'w', encoding="utf-8" ) as plane_text_output_file:
            last_translation_result = {}
            for i, vref in enumerate( vrefs ):

                result = None
                translation_result = {}

                if i < len( previous_result_jsonl ) and previous_result_jsonl[i]:
                    translation_result = json.loads( previous_result_jsonl[i] )
                    if 'fresh_translation' in translation_result:
                        result = translation_result['fresh_translation']['text']

                        if 'vref' not in translation_result:
                            translation_result['vref'] = vref
                        if 'source' not in translation_result:
                            translation_result['source'] = source[i]

                #of we previously had a result
                if i < len( previous_result ) and previous_result[i]:
                    result = previous_result[i]
                #if we are outside the range
                elif i < start_line or i > end_line:
                    result = ""
                #if there is no source for this location
                elif i >= len( source ) or not source[i]:
                    result = ""
                else:
                    #load the source
                    source_line = source[i]

                    got_it = False
                    while not got_it:
                        try:
                            object_result, translation_time = generate_verse( vref=vref,
                              source=source_line,
                              last_translation_dict=last_translation_result,
                              model_name=config['model'],
                              target_language=config['target_language'],
                              temperature=config['temperature'], top_p=config['top_p'],
                              max_verse_range=max_verse_range,
                              translation_command=config['translation_command'] )
                            got_it = True
                        except Exception as e:  # pylint: disable=broad-except
                            print( f"Failed to generate verse for {vref}: {e}" )
                            time.sleep( 10 )

                    translation_result = object_result.model_dump()
                    translation_result['translation_time'] = translation_time
                    if not object_result.forming_verse_range_with_previous_verse:
                        translation_result['source'] = source_line
                        translation_result['vrefs'] = [vref]
                        translation_result['vref'] = vref
                    else:
                        assert last_translation_result, "last_translation_result should " + \
                            "be truthy if we got a range output."
                        translation_result['source'] = last_translation_result['source'] + " " + \
                            source_line
                        translation_result['vrefs'] = last_translation_result['vrefs'] + [vref]
                        translation_result['vref'] = verse_parsing.to_range(
                            translation_result['vrefs'],  vrefs )

                    result = object_result.fresh_translation.text

                    print( f"Translated {vref}: {result}" )

                plane_text_output_file.write( result + "\n" )
                jsonl_output_file.write( json.dumps( translation_result, ensure_ascii=False ) +
                    "\n" )
                last_translation_result = translation_result


    os.rename( temp_out_filename, out_filename )
    os.rename( temp_out_filename_jsonl, out_filename_jsonl )


def main():
    """
    This is the main entry point for the script.
    """
    with open('rangeable_easy_draft.yaml', encoding='utf-8') as f:
        config = yaml.load(f, Loader=yaml.FullLoader)

    for specific_config in config['configs'].values():
        run_config( specific_config, config['global_configs']['ebible_dir'] )

if __name__ == "__main__":
    main()

    print( "Done!" )
