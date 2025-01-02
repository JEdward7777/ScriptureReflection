"""
This module implements the reflection functionality for generating a draft of the Bible.
"""
import os
import time
import copy
from typing import List
import json


from collections import defaultdict, OrderedDict
from pydantic import BaseModel
from openai import OpenAI
import yaml
import utils

def perform_chapter_reflection( client, source_and_translation, translation_objective, model_name,
        temperature, top_p, grades ):
    """
    Perform a reflection on the translation.
    """
    source_and_translation_json = json.dumps( source_and_translation, ensure_ascii=False, indent=2 )

    system_message = "You are a gifted Bible student, who is implementing corrections from " + \
        "your teachers, on your Bible translation.  Both you and your teachers operate from " + \
        "a Conservative Christian perspective."

    user_message_array = [ "Translation Objective: ", translation_objective, "\n\n",
        source_and_translation_json, "\n" ]


    user_message_array += [
        "\n##Teachers corrections:\n" ]

    for i,grade in enumerate(grades['grades']):
        user_message_array += [ "Correction #", i+1, ":\n```\n", grade['comment'], "\n```\n\n" ]

    user_message_array += ["Attempt to satisfy all provided instructions to the best of your ",
        "ability. If the instructions are contradictory or mutually exclusive, use your own ",
        "logic to resolve the conflict while prioritizing consistency and alignment with the ",
        "overall goal.  The output should be JSON using keys reference and translation using ",
        "the same reference keys as the input.\n" ]


    user_message = "".join(str(s) for s in user_message_array)

    class ReflectionResponse(BaseModel):
        """A def for structured response from ChatGPT"""
        planning_thoughts: str
        reference: str
        translation: str

    class ChatperReflectionResponse(BaseModel):
        """A def for structured response from ChatGPT"""
        reflection: List[ReflectionResponse]

    completion = client.beta.chat.completions.parse(
        model=model_name,
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ],
        temperature=temperature,
        top_p=top_p,
        response_format=ChatperReflectionResponse
    )

    result = completion.choices[0].message.parsed.model_dump()

    return result['reflection']


def main():
    """
    Run the reflection process which improves the translation by utilizing the grades.
    """

    with open( 'key.yaml', encoding='utf-8' ) as keys_f:
        api_keys = yaml.load(keys_f, Loader=yaml.FullLoader)


    #load do_reflection.yaml
    with open( 'do_chapter_reflection.yaml', encoding='utf-8' ) as f:
        do_reflection_yaml = yaml.load(f, Loader=yaml.FullLoader)

    save_timeout = do_reflection_yaml.get( 'global_configs', {} ).get( 'save_timeout', 20 )

    for config_name, config in do_reflection_yaml['configs'].items():
        print( f"Running config {config_name}" )
        if config['active']:
            client = OpenAI(api_key=utils.look_up_key( api_keys, config['api_key'] ))

            chapter_reflection_output_filename = config['chapter_reflection_output']
            translation_key = config['translation_key']
            translation_input = utils.load_jsonl( config['translation_input'] )

            #load the result if we didn't finish last time.
            if os.path.exists(chapter_reflection_output_filename):
                chapter_reflection_output = utils.load_jsonl( chapter_reflection_output_filename )
            else:
                #otherwise load the existing translation and blank out all the translation keys.
                chapter_reflection_output = copy.deepcopy( translation_input )

                for verse in chapter_reflection_output:
                    if utils.look_up_key( verse, translation_key ):
                        utils.set_key( verse, translation_key, "" )
            last_save = time.time()


            translation_comment_key = config.get('translation_comment_key', None)

            reference_key = config['reference_key']
            source_key = config['source_key']
            over_ridden_references = utils.get_overridden_references( translation_input,
                reference_key, config.get( 'override_key', None ) )


            translation_objective = config['translation_objective']
            model_name = config['model']
            temperature = config['temperature']
            top_p = config['top_p']


            translation_chapter_grades_filename = config['translation_chapter_grades']
            translation_chapter_grades = utils.load_json( translation_chapter_grades_filename )


            #here I will iterate through the translation and split it into chapters so that
            #I can iterate through the chapters and do the reflection.
            book_chapter_to_verses = defaultdict(list)
            for verse in translation_input:
                verse_reference = utils.look_up_key( verse, reference_key )
                if verse_reference and verse_reference not in over_ridden_references:
                    book, chapter, _ = utils.split_ref( verse_reference )
                    book_chapter_to_verses[f"{book} {chapter}"].append( verse )


            #Here I will index all input and output verses by reference.
            input__reference_to_verse  = { utils.look_up_key( verse, reference_key ): verse for verse in translation_input }
            output__reference_to_verse = { utils.look_up_key( verse, reference_key ): verse for verse in chapter_reflection_output }
            


            #now loop through the translation and do the grading.
            for book_chapter, chapter_of_verses in book_chapter_to_verses.items():
                #now I need to create a structure which I will use to convert to json for ChatGPT
                #to read.
                source_and_translation = []
                for verse in chapter_of_verses:
                    verse_reference = utils.look_up_key( verse, reference_key )
                    translation = utils.look_up_key( verse, translation_key )
                    source = utils.look_up_key( verse, source_key )

                    source_and_translation.append( {
                        "reference": verse_reference,
                        "source": source,
                        "translation": translation,
                    })

                #see if the output has a translation set yet for the first verse.
                first_reference = utils.look_up_key( chapter_of_verses[0], reference_key )
                if not utils.look_up_key( output__reference_to_verse[first_reference], translation_key ):

                    print( f"Processing {book_chapter}" )
                    #do the reflection.

                    grades = translation_chapter_grades['chapters'][book_chapter]


                    reflection_result = perform_chapter_reflection( client, source_and_translation,
                        translation_objective, model_name, temperature, top_p, grades )

                    for verse in reflection_result:
                        assert verse['reference'] in output__reference_to_verse, \
                            f"{verse['reference']} is not in output__reference_to_verse"
                        utils.set_key( output__reference_to_verse[verse['reference']], translation_key,
                            verse['translation'] )

                        if translation_comment_key:
                            utils.set_key( output__reference_to_verse[verse['reference']],
                                translation_comment_key, verse['planning_thoughts'] )


                    #if we haven't saved in a while, do it now.
                    if time.time() - last_save > save_timeout:
                        utils.save_jsonl(chapter_reflection_output_filename,
                            chapter_reflection_output)
                        last_save = time.time()


            #save the reflection output
            utils.save_jsonl( chapter_reflection_output_filename, chapter_reflection_output )









if __name__ == "__main__":
    main()

    print( "Done!" )
