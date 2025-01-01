"""
This module grades a translation using ChatGPT.
"""

import os
import json
import time
import yaml
from openai import OpenAI
from pydantic import BaseModel


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

def grade_verse( client, reference, translation, source, previous_verse_translation,
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

    user_message_array = [
        "Translation Objective: ", str(translation_objective), "\n\n",
        "Reference: ", str(reference), "\n",
        "Translation: ", str(translation), "\n",
        "Source: ", str(source), "\n" ]
    if previous_verse_translation:
        user_message_array += [ "Previous Verse: ", str(previous_verse_translation), "\n" ]

    user_message_array += [ "\nReview the students work from a conservative Christain perspective ",
     "and give it a grade comment and a grade from 0 to 100 where 0 is failing and 100 is ",
     "perfection." ]
    user_message = "".join(user_message_array)

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

def average_grades( grades ):
    """Averages the grades"""
    return sum( [grade['grade'] for grade in grades] ) / len(grades)

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


def main():
    """
    Run the grade output routines.
    """

    with open( 'key.yaml', encoding='utf-8' ) as keys_f:
        api_keys = yaml.load(keys_f, Loader=yaml.FullLoader)



    #load grade_output.yaml
    with open( 'grade_output.yaml', encoding='utf-8' ) as f:
        grade_output_yaml = yaml.load(f, Loader=yaml.FullLoader)


    save_timeout = grade_output_yaml.get( 'global_configs', {} ).get( 'save_timeout', 20 )

    for config_name, config in grade_output_yaml['configs'].items():
        print( f"Running config {config_name}" )
        if config['active']:
            client = OpenAI(api_key=look_up_key( api_keys, config['api_key'] ))

            translation_grades_filename = config['translation_grades']

            #load the result if we didn't finish last time.
            if os.path.exists(translation_grades_filename):
                translation_grades = load_json( translation_grades_filename )
            else:
                translation_grades = {"verses": {}}
            last_save = time.time()

            #now load the translation.
            translation_filename = config['translation']
            translation = load_jsonl( translation_filename )

            reference_key = config['reference_key']
            source_key = config['source_key']
            translation_key = config['translation_key']

            num_grades_per_verse = config['num_grades_per_verse']

            #need to run through the translation and find the overridden verses.
            #this is a thing where to support verse ranges, a verse can declare that it combines
            #with the one before it.
            over_ridden_references = get_overridden_references( translation, reference_key,
                config.get( 'override_key', None ) )


            translation_objective = config['translation_objective']
            model_name = config['model']
            temperature = config['temperature']
            top_p = config['top_p']


            #now loop through the translation and do the grading.
            previous_verse_translation = None
            for i,verse in enumerate(translation):
                reference = look_up_key( verse, reference_key )
                translation = look_up_key( verse, translation_key )
                source = look_up_key( verse, source_key )

                if reference and translation and reference not in over_ridden_references:

                    print( "Processing verse", i, reference, translation )

                    #see if we need any more grades for this verse.
                    while reference not in translation_grades['verses'] or \
                            len(translation_grades['verses'][reference]['grades']) < \
                            num_grades_per_verse:

                        grade_result = grade_verse( client, reference, translation, source,
                            previous_verse_translation, translation_objective, model_name,
                            temperature, top_p )

                        if reference not in translation_grades['verses']:
                            translation_grades['verses'][reference] = {'grades': []}

                        translation_grades['verses'][reference]['grades'].append( grade_result )

                        #now reduce the grades to a single grade.
                        translation_grades['verses'][reference]['grade'] = average_grades(
                            translation_grades['verses'][reference]['grades'] )


                        #if we haven't saved in a while, do it now.
                        if time.time() - last_save > save_timeout:
                            save_json( translation_grades_filename, translation_grades )
                            last_save = time.time()

                    if not "grade" in translation_grades['verses'][reference]:
                        translation_grades['verses'][reference]['grade'] = average_grades(
                            translation_grades['verses'][reference]['grades'] )

                    previous_verse_translation = translation

            #compute the average grade for the entire work.
            grade_count = 0
            grade_sum = 0
            for reference in translation_grades['verses']:
                if 'grade' in translation_grades['verses'][reference]:
                    grade_count += 1
                    grade_sum += translation_grades['verses'][reference]['grade']
            translation_grades['average_grade'] = grade_sum / grade_count


            save_json( translation_grades_filename, translation_grades )









if __name__ == "__main__":
    main()

    print( "Done!" )
