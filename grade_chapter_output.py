"""
This module grades a translation a chapter at a time using ChatGPT.
"""

import os
import time
import json
from collections import defaultdict
import yaml

from openai import OpenAI
from pydantic import BaseModel

import utils
import grade_output


def grade_chapter( client, source_and_translation,
        translation_objective, model_name, temperature, top_p ):
    """
    Grade the translation of a verse.
    :param reference: The reference to the verse.
    :param translation: The translation of the verse.
    :param source: The source text of the verse.
    :return: The grade of the translation.
    """
    system_message = "You are a teacher grading a student's translation of the Bible from a " + \
        "conservitive Christian viewpoint."



    source_and_translation_json = json.dumps( source_and_translation, ensure_ascii=False, indent=2 )

    user_message_array = [
        "Translation Objective: ", translation_objective, "\n\n",
        source_and_translation_json, "\n" ]

    user_message_array += [ "\nReview the students work from a conservative Christian perspective ",
     "and give it a grade comment and a grade from 0 to 100 where 0 is failing and 100 is ",
     "perfection." ]
    user_message = "".join(str(x) for x in user_message_array)

    class GradeResponse(BaseModel):
        """A def for structured response from ChatGPT"""
        comment: str
        grade: int

    completion = client.beta.chat.completions.parse(
        model=model_name,
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ],
        temperature=temperature,
        top_p=top_p,
        response_format=GradeResponse
    )

    result = completion.choices[0].message.parsed.model_dump()

    return result




def main():
    """
    Run the grade output routines.
    """

    with open( 'key.yaml', encoding='utf-8' ) as keys_f:
        api_keys = yaml.load(keys_f, Loader=yaml.FullLoader)



    #load grade_chapter_output.yaml
    with open( 'grade_chapter_output.yaml', encoding='utf-8' ) as f:
        grade_output_yaml = yaml.load(f, Loader=yaml.FullLoader)


    save_timeout = grade_output_yaml.get( 'global_configs', {} ).get( 'save_timeout', 20 )

    for config_name, config in grade_output_yaml['configs'].items():
        print( f"Running config {config_name}" )
        if config['active']:
            client = OpenAI(api_key=utils.look_up_key( api_keys, config['api_key'] ))

            translation_chapter_grades_filename = config['translation_chapter_grades']

            #load the result if we didn't finish last time.
            if os.path.exists(translation_chapter_grades_filename):
                translation_chapter_grades = utils.load_json( translation_chapter_grades_filename )
            else:
                translation_chapter_grades = {"chapters": {}}
            last_save = time.time()

            #now load the translation.
            translation_filename = config['translation']
            translation = utils.load_jsonl( translation_filename )

            reference_key = config['reference_key']
            source_key = config['source_key']
            translation_key = config['translation_key']

            num_grades_per_chapter = config['num_grades_per_chapter']

            #need to run through the translation and find the overridden verses.
            #this is a thing where to support verse ranges, a verse can declare that it combines
            #with the one before it.
            over_ridden_references = utils.get_overridden_references( translation, reference_key,
                config.get( 'override_key', None ) )


            translation_objective = config['translation_objective']
            model_name = config['model']
            temperature = config['temperature']
            top_p = config['top_p']

            #here I will iterate through the translation and split it into chapters so that
            #I can iterate through the chapters and do the grading.
            book_chapter_to_translation = defaultdict(list)
            for verse in translation:
                verse_reference = utils.look_up_key( verse, reference_key )
                if verse_reference and verse_reference not in over_ridden_references:
                    book, chapter, _ = utils.split_ref( verse_reference )
                    book_chapter_to_translation[(book,chapter)].append( verse )


            #now loop through the translation a chapter at a time and do the grading.
            for (book, chapter), chapter_of_verses in book_chapter_to_translation.items():
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
                    } )

                print( f"Processing {book} {chapter}" )

                #see if we need any more grades for this verse.
                while f"{book} {chapter}" not in translation_chapter_grades['chapters'] or \
                        len(translation_chapter_grades['chapters'][f"{book} {chapter}"]['grades']) < \
                        num_grades_per_chapter:

                    grade_result = grade_chapter( client, source_and_translation,
        translation_objective, model_name, temperature, top_p )

                    if f"{book} {chapter}" not in translation_chapter_grades['chapters']:
                        translation_chapter_grades['chapters'][f"{book} {chapter}"] = {'grades': []}

                    translation_chapter_grades['chapters'][f"{book} {chapter}"]['grades'] \
                        .append( grade_result )

                    #now reduce the grades to a single grade.
                    translation_chapter_grades['chapters'][f"{book} {chapter}"]['grade'] = \
                        grade_output.average_grades(
                        translation_chapter_grades['chapters'][f"{book} {chapter}"]['grades'] )


                    #if we haven't saved in a while, do it now.
                    if time.time() - last_save > save_timeout:
                        utils.save_json( translation_chapter_grades_filename,
                            translation_chapter_grades )
                        last_save = time.time()

                if not "grade" in translation_chapter_grades['chapters'][f"{book} {chapter}"]:
                    translation_chapter_grades['chapters'][f"{book} {chapter}"]['grade'] = \
                            grade_output.average_grades(
                            translation_chapter_grades['chapters'][f"{book} {chapter}"]['grades'] )

            #compute the average grade for the entire work.
            grade_count = 0
            grade_sum = 0
            for book_chapter in translation_chapter_grades['chapters'].keys():
                if 'grade' in translation_chapter_grades['chapters'][book_chapter]:
                    grade_count += 1
                    grade_sum += translation_chapter_grades['chapters'][book_chapter]['grade']
            translation_chapter_grades['average_grade'] = grade_sum / grade_count


            utils.save_json( translation_chapter_grades_filename, translation_chapter_grades )









if __name__ == "__main__":
    main()

    print( "Done!" )
