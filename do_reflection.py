"""
This module implements the reflection functionality for generating a draft of the Bible.
It takes in a translation and grades on it, and outputs an update to the translation with 
changes requested in the grade file.
"""
import os
import time
import copy
import yaml
from openai import OpenAI
from pydantic import BaseModel

import utils

def perform_reflection( client, reference, from_translation, previous_output_translation,
        previous_vref, source, translation_objective, model_name, temperature, top_p, grades ):
    """
    Perform a reflection on the translation.
    :param from_translation: The translation of the verse.
    :param source: The source text of the verse.
    :return: The reflection of the translation.
    """

    system_message = "You are a gifted Bible student, who is implementing corrections from " + \
        "your teachers, on your Bible translation.  Both you and your teachers operate from " + \
        "a Conservative Christian perspective."

    user_message_array = [ "Translation Objective: ", translation_objective, "\n\n" ]



    if previous_output_translation:
        user_message_array += [ "Verse ", previous_vref, " one up for context:\n```\n",
        previous_output_translation, "\n```\n\n" ]


    user_message_array += [ "Current Reference: ", reference, "\n",
        "Current Source Text: ", source, "\n" ]


    user_message_array += [
        "Translation to revise:\n```\n", from_translation, "\n```\n"
        "\n##Teachers corrections:\n" ]

    for i,grade in enumerate(grades['grades']):
        user_message_array += [ "Correction #", i+1, ":\n```\n", grade['comment'], "\n```\n\n" ]

    user_message_array += ["Attempt to satisfy all provided instructions to the best of your ",
        "ability. If the instructions are contradictory or mutually exclusive, use your own ",
        "logic to resolve the conflict while prioritizing consistency and alignment with the ",
        "overall goal.\n" ]

    if previous_output_translation:
        user_message_array += [ "Make sure your update for ", reference,
        " works within context of ", previous_vref, " the verse just above it.  Don't repeat ",
        "yourself.\n" ]

    user_message = "".join(str(s) for s in user_message_array)

    class ReflectionResponse(BaseModel):
        """A def for structured response from ChatGPT"""
        planning_thoughts: str
        reference: str
        updated_translation: str

    completion = client.beta.chat.completions.parse(
        model=model_name,
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ],
        temperature=temperature,
        top_p=top_p,
        response_format=ReflectionResponse
    )

    result = completion.choices[0].message.parsed.model_dump()

    return result


def main():
    """
    Run the reflection process which improves the translation by utilizing the grades.
    """

    with open( 'key.yaml', encoding='utf-8' ) as keys_f:
        api_keys = yaml.load(keys_f, Loader=yaml.FullLoader)


    #load do_reflection.yaml
    with open( 'do_reflection.yaml', encoding='utf-8' ) as f:
        do_reflection_yaml = yaml.load(f, Loader=yaml.FullLoader)

    save_timeout = do_reflection_yaml.get( 'global_configs', {} ).get( 'save_timeout', 20 )

    for config_name, config in do_reflection_yaml['configs'].items():
        print( f"Running config {config_name}" )
        if config['active']:
            client = OpenAI(api_key=utils.look_up_key( api_keys, config['api_key'] ))

            reflection_output_filename = config['reflection_output']
            translation_key = config['translation_key']
            translation_input = utils.load_jsonl( config['translation_input'] )

            #load the result if we didn't finish last time.
            if os.path.exists(reflection_output_filename):
                reflection_output = utils.load_jsonl( reflection_output_filename )
            else:
                #otherwise load the existing translation and blank out all the translation keys.
                reflection_output = copy.deepcopy( translation_input )

                for verse in reflection_output:
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


            translation_grades_filename = config['translation_grades']
            translation_grades = utils.load_json( translation_grades_filename )


            #now loop through the translation and do the grading.
            previous_output_translation = None
            previous_vref = None
            for i,verse in enumerate(reflection_output):
                reference = utils.look_up_key( verse, reference_key )
                source = utils.look_up_key( verse, source_key )


                if reference and reference not in over_ridden_references:

                    #see if the output has a translation set yet for this verse.
                    if not utils.look_up_key( verse, translation_key ):

                        from_translation = utils.look_up_key(translation_input[i],
                            translation_key)

                        print( "Processing verse", i, reference, from_translation )
                        #do the reflection.

                        grades = translation_grades['verses'][reference]


                        reflection_result = perform_reflection( client, reference,
                            from_translation, previous_output_translation, previous_vref, source,
                            translation_objective, model_name, temperature, top_p, grades )

                        if translation_comment_key:
                            utils.set_key( verse, translation_comment_key,
                                reflection_result['planning_thoughts'] )

                        output_translation = reflection_result['updated_translation']

                        if output_translation:
                            utils.set_key( verse, translation_key, output_translation )


                        #if we haven't saved in a while, do it now.
                        if time.time() - last_save > save_timeout:
                            utils.save_jsonl(reflection_output_filename, reflection_output)
                            last_save = time.time()
                    else:
                        output_translation = utils.look_up_key( verse, translation_key )


                    previous_output_translation = output_translation
                    previous_vref = reference

            utils.save_jsonl( reflection_output_filename, reflection_output )









if __name__ == "__main__":
    main()

    print( "Done!" )
