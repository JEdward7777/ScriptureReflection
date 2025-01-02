"""
This module implements the easy_draft functionality for generating a draft of the Bible.
"""
import os
import time
import json
import yaml
from openai import OpenAI
from pydantic import BaseModel


with open( 'key.yaml', encoding='utf-8' ) as keys_f:
    api_key = yaml.load(keys_f, Loader=yaml.FullLoader)['openai_key']
client = OpenAI(api_key=api_key)
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
    last_result: str,
    model_name: str,
    target_langauge: str,
    temperature: float,
    top_p: float
) -> Translation:
    """
    Generate a fresh translation of a verse from the Bible.  Before the verse,
    quote 5 other verses from the Bible which use similar words which would be
    useful.
    """

    #going to time how long this takes.
    start_time = time.time()

    message = (f"Generate a fresh translation of {vref} in {target_langauge}.  Before the verse " +
      "quote 5 other verses from the Bible in {target_langauge} which use similar words which " +
      "would be useful. Pay attention to the source text and don't plagiarize existing " +
      "translations.")
    message += f"\nThe original text is: {source}"
    if last_result:
        message += f"\nFor context the previous verse was translated as: {last_result}"

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
    previous_result = []
    previous_result_jsonl = []

    if os.path.exists( out_filename ):
        previous_result = load_file_to_list( out_filename )

    if os.path.exists( out_filename_jsonl ):
        previous_result_jsonl = load_file_to_list( out_filename_jsonl )

    os.makedirs( os.path.dirname( temp_out_filename ), exist_ok=True )

    with open( temp_out_filename_jsonl, 'w', encoding="utf-8" ) as f_jsonl:
        with open( temp_out_filename, 'w', encoding="utf-8" ) as f:
            last_result = None
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
                            object_result, translation_time = generate_verse( vref, source_line,
                              last_result, config['model'], config['target_language'],
                              config['temperature'], config['top_p'] )
                            got_it = True
                        except Exception as e:  # pylint: disable=broad-except
                            print( f"Failed to generate verse for {vref}: {e}" )
                            time.sleep( 10 )

                    translation_result = object_result.model_dump()
                    translation_result['translation_time'] = translation_time
                    translation_result['vref'] = vref
                    translation_result['source'] = source_line
                    result = object_result.fresh_translation.text

                    print( f"Translated {vref}: {result}" )

                f.write( result + "\n" )
                f_jsonl.write( json.dumps( translation_result, ensure_ascii=False ) + "\n" )
                last_result = result


    os.rename( temp_out_filename, out_filename )
    os.rename( temp_out_filename_jsonl, out_filename_jsonl )


def main():
    """
    This is the main entry point for the script.
    """
    with open('easy_draft.yaml', encoding='utf-8') as f:
        config = yaml.load(f, Loader=yaml.FullLoader)

    for specific_config in config['configs'].values():
        run_config( specific_config, config['global_configs']['ebible_dir'] )

if __name__ == "__main__":
    main()

    print( "Done!" )
