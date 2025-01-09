"""
This builds on the lessons learned from do_reflection.py and do_chapter_reflection.py as well as
grade_output.py .  It incorperates the full loop into one file so the stages do not need to be 
manualy iterated with the configuration files.  It uses about a chapter's worth of context but
only updates one verse at a time.  It outputs the current average grade of the translation while
it is running.  The intermediate output is saved in new entries in the output translation jsonl 
file.
"""

import os
import time
import copy
import json

from pydantic import BaseModel
from openai import OpenAI
import yaml
import utils


def compute_completed_loops( verse ):
    """
    Compute the number of loops that have been completed for a given verse.
    """
    #it is the same as the length of 'reflection_loops' unless the last one is incomplete.
    if 'reflection_loops' not in verse:
        return 0

    if len(verse['reflection_loops']) == 0:
        return 0

    num_loops = len(verse['reflection_loops'])

    last_reflection_loop = verse['reflection_loops'][-1]

    if 'graded_verse' in last_reflection_loop:
        return num_loops

    return num_loops - 1


def compute_verse_grade( verse ):
    if 'reflection_loops' not in verse:
        return 0

    if len(verse['reflection_loops']) == 0:
        return 0

    #iterate backwords through the reflection_loops until we find
    #one that we can get a grade from.
    for reflection_loop in reversed(verse['reflection_loops']):
        if 'average_grade' in reflection_loop:
            return reflection_loop['average_grade']

        #if there is at least one grade, go ahead and average it.
        grade_count = 0
        grade_sum = 0
        for grade in reflection_loop['grades']:
            grade_count += 1
            grade_sum += grade['grade']

        if grade_count > 0:
            averaged_grade = grade_sum / grade_count

            #if this is the correct count, we can stash it.
            if grade_count >= config['grades_per_reflection_loop']:
                reflection_loop['average_grade'] = averaged_grade
            
            return averaged_grade

    return None
        

def compute_translation_grade( translation ):
    """
    Compute the average grade of the translation.
    """
    verse_count = 0
    verse_sum = 0

    for verse in translation:
        verse_grade = compute_verse_grade( verse )
        if verse_grade is not None:
            verse_count += 1
            verse_sum += verse_grade

    if verse_count == 0:
        return 0

    return verse_sum / verse_count

def build_common_context( selected_verse, reflection_output, config, over_ridden_references ):
    """
    There are different LLM operations but they have common context.  This builds it.
    """

    num_before_verses = config['num_before_verses']
    num_after_verses = config['num_after_verses']

    selected_verse_index = reflection_output.index( selected_verse )

    first_included_index = max(selected_verse_index - num_before_verses, 0)
    last_included_index = min(selected_verse_index + num_after_verses, len(reflection_output) - 1)

    source_and_translation = []

    for index in range( first_included_index, last_included_index + 1 ):
        verse_reference = utils.look_up_key( reflection_output[index], config['verse_reference_key'] )
        if verse_reference not in over_ridden_references:
            translation = utils.look_up_key( reflection_output[index], config['translation_key'] )
            source = utils.look_up_key( reflection_output[index], config['source_key'] )

            source_and_translation.append( {
                'reference': verse_reference,
                'source': source,
                'translation': translation
            })


    source_and_translation_json = json.dumps( source_and_translation, ensure_ascii=False, indent=2 )
    user_message_array = [
        "Translation Objective: ", config['translation_objective'], "\n\n",
        source_and_translation_json, "\n" ]

    return "\n".join( str(x) for x in user_message_array )


def grade_verse( selected_verse, common_context, client, config ):
    """
    Grade the translation of a verse.
    """

    vref = utils.look_up_key( selected_verse, config['reference_key'] )

    system_message = "You are a teacher grading a student's translation of the Bible from a " + \
        "conservitive Christian viewpoint."

    user_message_array = [
        common_context, "\n\n",
        "\nReview the students work translating ", vref, " from a conservative Christian perspective ",
        "and give it a grade comment and a grade from 0 to 100 where 0 is failing and 100 is ",
        "perfection.  Grade ", vref, " for clarity, accuracy, perspective, and redundancy with the previous ",
        "verse as well as other verses." 
    ]

    user_message = "".join(user_message_array)


    class GradeResponse(BaseModel):
        """A def for structured response from ChatGPT"""
        comment: str
        grade: int

    completion = client.beta.chat.completions.parse(
        model=config['model_name'],
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ],
        temperature=config['temperature'],
        top_p=config['top_p'],
        response_format=GradeResponse
    )

    result = completion.choices[0].message.parsed.model_dump()

    return result

def perform_reflection( selected_verse, common_context, client, config ):
    """
    Run the reflection step where the grade comments of a verse are utilize to revise a verse.
    """


    vref = utils.look_up_key( selected_verse, config['reference_key'] )

    system_message = "You are a gifted Bible student, who is implementing corrections from " + \
        "your teachers, on your Bible translation.  Both you and your teachers operate from " + \
        "a Conservative Christian perspective."

    user_message_array = [ common_context, "\n\n" ]

    user_message_array += [ "The reference being revised is ", vref, "\n" ]

    for i,grade in enumerate(selected_verse['reflection_loops'][-1]['grades']):
        user_message_array += [ "Correction #", i+1, ":\n```\n", grade['comment'], "\n```\n\n" ]

    user_message_array += ["Attempt to satisfy all provided instructions for ", vref, " to the best of your ",
        "ability. If the instructions are contradictory or mutually exclusive, use your own ",
        "logic to resolve the conflict while prioritizing consistency and alignment with the ",
        "overall goal.  Output your planning_thourhts, the reference ", vref, ", and the updated translation.\n" ]

    user_message = "".join(str(s) for s in user_message_array)


    class ReflectionResponse(BaseModel):
        """A def for structured response from ChatGPT"""
        planning_thoughts: str
        reference: str
        updated_translation: str

    completion = client.beta.chat.completions.parse(
        model=config['model_name'],
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ],
        temperature=config['temperature'],
        top_p=config['top_p'],
        response_format=ReflectionResponse
    )
    result = completion.choices[0].message.parsed.model_dump()

    return result


def main():
    """
    Run the reflection and grade loop as defined in the grade_reflect_loop.yaml file.
    """

    with open( 'key.yaml', encoding='utf-8' ) as keys_f:
        api_keys = yaml.load(keys_f, Loader=yaml.FullLoader)

    with open( 'grade_reflect_loop.yaml', encoding='utf-8' ) as f:
        grade_reflect_loop_yaml = yaml.load(f, Loader=yaml.FullLoader)

    save_timeout = grade_reflect_loop_yaml.get( 'global_configs', {} ).get( 'save_timeout', 20 )

    for config_name, config in grade_reflect_loop_yaml['configs'].items():
        print( f"Running config {config_name}" )
        if config['active']:
            client = OpenAI(api_key=utils.look_up_key( api_keys, config['api_key'] ))

            reflection_output_filename = config['reflection_output']

            translation_input = utils.load_jsonl( config['translation_input'] )

            output_dirty = False

            #load the result if we didn't finish last time.
            if os.path.exists(reflection_output_filename):
                reflection_output = utils.load_jsonl( reflection_output_filename )
            else:
                #otherwise load the existing translation and blank out all the translation keys.
                reflection_output = copy.deepcopy( translation_input )

            try:

                last_save = time.time()

                reference_key = config['reference_key']
                translation_key = config['translation_key']
                translation_comment_key = config.get('translation_comment_key', None)

                #figure out what the overridden verses are.  These are verses where
                #a following verse decided to incorperate the overriden verse into a verse range.
                over_ridden_references = utils.get_overridden_references( translation_input,
                    reference_key, config.get( 'override_key', None ) )

                action_done = "did nothing"

                done = False
                while not done:
                    #so each time we run through the loop we do one of the following:
                    #Figure out which verse has the fewest number of loops done on it.
                    #Then keep running a grade pass for that verse until it has the specified number
                    #of grades.  Once that happens, we add a reflection loop on it.
                    #Once all the verses have the number of reflection loops that the configuration
                    #calls for we are done.

                    #find the verse with the fewest number of reflection loops
                    verse_with_fewest_loops = None
                    fewest_loops = None
                    for verse in reflection_output:
                        vref = utils.look_up_key( verse, reference_key )
                        if vref is not None and not utils.look_up_key( verse, reference_key ) in over_ridden_references:
                            num_completed_loops = compute_completed_loops( verse )
                            if fewest_loops is None or num_completed_loops < fewest_loops:
                                verse_with_fewest_loops = verse
                                fewest_loops = num_completed_loops

                    #check if the verse with the fewest loops has the numer requested by the configuration
                    #if it does, we are done.
                    if verse_with_fewest_loops is not None and fewest_loops < config['reflection_loops_per_verse']:
                        selected_verse = verse_with_fewest_loops


                        common_context = build_common_context( selected_verse, reflection_output, config, over_ridden_references )


                        #add a new reflection loop if the current last one is None or is complete.
                        last_reflection_loop = selected_verse['reflection_loops'][-1] if len(selected_verse.get('reflection_loops', [])) > 0 else None
                        if last_reflection_loop is None or 'graded_verse' in last_reflection_loop:
                            if 'reflection_loops' not in selected_verse:
                                selected_verse['reflection_loops'] = []
                            last_reflection_loop = {}
                            selected_verse['reflection_loops'].append(last_reflection_loop)


                        #ok, so now we need to see if this verse has the requested number of grades for this verse
                        #otherwise we need to run another grade run on it.
                        if last_reflection_loop is None or len(last_reflection_loop.get('grades', [])) < config['grades_per_reflection_loop']:
                            #we need to run a grade pass on this verse.

                            new_grade = grade_verse( selected_verse, common_context, client, config )

                            #add the new grade to the reflection loop
                            if 'reflection_loops' not in selected_verse:
                                selected_verse['reflection_loops'] = []
                            if len( selected_verse['reflection_loops'] ) == 0:
                                selected_verse['reflection_loops'].append( {} )
                                last_reflection_loop = selected_verse['reflection_loops'][-1]
                            if 'grades' not in last_reflection_loop:
                                last_reflection_loop['grades'] = []
                            last_reflection_loop['grades'].append(new_grade)
                            output_dirty = True
                            action_done = f"added grade number {len(last_reflection_loop['grades'])} to verse {utils.look_up_key( selected_verse, reference_key )}"


                        else:
                            #we have enough grades, so we need to do the reflection loop
                            reflection_result = perform_reflection( selected_verse, common_context, client, config )

                            #the existing translation to the loop
                            if translation_comment_key:
                                last_reflection_loop['graded_verse_comment'] = utils.look_up_key( selected_verse, translation_comment_key )
                            last_reflection_loop['graded_verse'] = utils.look_up_key( selected_verse, translation_key )

                            #and replace it.
                            utils.set_key( selected_verse, translation_key, reflection_result['updated_translation'] )
                            if translation_comment_key:
                                utils.set_key( selected_verse, translation_comment_key, reflection_result['planning_thoughts'] )
                            output_dirty = True
                            action_done = f"reflected on verse {utils.look_up_key( selected_verse, reference_key )}"


                        #now save if we haven't saved in a while
                        if output_dirty and time.time() - last_save > save_timeout:
                            utils.save_jsonl( reflection_output, reflection_output_filename )
                            last_save = time.time()
                            output_dirty = False

                    else:
                        done = True

                    average_grade = compute_translation_grade( reflection_output )
                    #spit out the current time and the average_grade and action_done
                    print( f"{time.strftime('%Y-%m-%d %H:%M:%S')} - Average grade: {average_grade} - {action_done}" )

            finally:
                #save the reflection output
                if output_dirty:
                    utils.save_jsonl( reflection_output, reflection_output_filename )

if __name__ == "__main__":
    main()

    print( "Done!" )
