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

def compute_number_unanswered_grades( verse ):
    """
    Determine the number of grades that have not been answered by a reflection.
    """
    if 'reflection_loops' not in verse:
        return 0

    last_reflection_loop = verse['reflection_loops'][-1]

    if 'graded_verse' in last_reflection_loop:
        return 0

    return len(last_reflection_loop['grades'])


def compute_verse_grade( verse, config ):
    """
    Compute the average grade of a verse.
    """
    vref = utils.look_up_key( verse, config['reference_key'] )

    if vref is None:
        return None

    if 'reflection_loops' not in verse:
        return None

    if len(verse['reflection_loops']) == 0:
        return None

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


def compute_translation_grade( translation, config ):
    """
    Compute the average grade of the translation.
    """
    verse_count = 0
    verse_sum = 0

    for verse in translation:
        verse_grade = compute_verse_grade( verse, config )
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

    num_context_verses_before = config['num_context_verses_before']
    num_context_verses_after = config['num_context_verses_after']

    selected_verse_index = reflection_output.index( selected_verse )

    first_included_index = max(selected_verse_index - num_context_verses_before, 0)
    last_included_index = min(selected_verse_index + num_context_verses_after,
        len(reflection_output) - 1)

    source_and_translation = []

    for index in range( first_included_index, last_included_index + 1 ):
        verse_reference = utils.look_up_key( reflection_output[index], config['reference_key'] )
        if verse_reference is not None and verse_reference not in over_ridden_references:
            translation = utils.look_up_key( reflection_output[index], config['translation_key'] )
            source = utils.look_up_key( reflection_output[index], config['source_key'] )

            source_and_translation.append( {
                'reference': verse_reference,
                'source': source,
                'translation': translation
            })

    selected_verse_vref = utils.look_up_key( selected_verse, config['reference_key'] )


    source_and_translation_json = json.dumps( source_and_translation, ensure_ascii=False, indent=2 )
    user_message_array = [
        "Translation Objective: ", config['translation_objective'], "\n\n",
        f"Source and target text of {selected_verse_vref} and its surrounding context:\n",
        source_and_translation_json, "\n" ]

    result = "".join( str(x) for x in user_message_array )

    return result


def grade_verse( selected_verse, common_context, client, config ):
    """
    Grade the translation of a verse.
    """

    vref = utils.look_up_key( selected_verse, config['reference_key'] )

    system_message = "You are a teacher grading a student's translation of the Bible from a " + \
        "conservitive Christian viewpoint."

    user_message_array = [
        common_context, "\n",
        "Instructions: Review the students work translating ", vref, " from a conservative ",
        "Christian perspective and give it a grade comment and a grade from 0 to 100 where 0 is ",
        "failing and 100 is perfection.\n"
    ]

    if 'grading_prompt' in config:
        user_message_array += [config.get( 'grading_prompt').format( vref=vref ), "\n"]

    user_message = "".join(user_message_array)


    class GradeResponse(BaseModel):
        """A def for structured response from ChatGPT"""
        comment: str
        grade: int

    completion = client.beta.chat.completions.parse(
        model=config['model'],
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

def summarize_corrections( selected_verse, client, config ):
    """
    Summarize the corrections of a verse.
    """

    vref = utils.look_up_key( selected_verse, config['reference_key'] )

    system_message = "You are a teacher compiling a summary of corrections from a peer review " + \
        "of the Bible from a conservitive Christian viewpoint."

    user_message_array = []

    #put the translation history in
    had_history = False
    if 'reflection_loops' in selected_verse and len( selected_verse['reflection_loops'] ) > 1:
        user_message_array += ['##Edit History:\n']
        for i,reflection_loop in enumerate(selected_verse['reflection_loops'][:-1]):
            had_history = True
            user_message_array += [ vref, " version ", (i+1), ":\n```\n",
                 reflection_loop['graded_verse'], "\n```\n" ]

            if 'correction_summarization' in reflection_loop and \
                    'summary' in reflection_loop['correction_summarization']:
                user_message_array += [ "Past Fix: ", (i+1), ":\n```\n",
                    reflection_loop['correction_summarization']['summary'], "\n```\n\n" ]

    #show the current version of the verse.
    user_message_array += ["Source: ",
        utils.look_up_key( selected_verse, config['source_key'] ), "\n",
        "Current Translation: ", utils.look_up_key( selected_verse, config['translation_key'] ),
        "\n\n" ]


    #now add the current corrections requests under the persona of a peer review.
    user_message_array += ["##Peer review comments for ", vref, ":\n"]
    selected_reflection_loop = selected_verse['reflection_loops'][-1]
    for i,grade in enumerate(selected_reflection_loop['grades']):
        user_message_array += [ "Correction #", i+1, ":\n```\n", grade['comment'], "\n```\n\n" ]


    if "summarize_instructions" in config:
        user_message_array += [ config['summarize_instructions'], "\n" ]
    else:
        #Now add the final instructions.
        user_message_array += [ "Instructions: Review the peer review comments, prioritize and ",
            "summarize the most important corrections.",
            "Comments which request removing content are highest priority. ",
            "Comments which request fixing content are the second highest priority. ",
            "Comments which request adding new content are the lowest priority. " ]

    if had_history:
        user_message_array += [
        "Review the edit history to prevent repeating history, for example requesting adding ",
        "content which was intentionally removed."]

    user_message = "".join(str(x) for x in user_message_array)


    class SummarizeResponse(BaseModel):
        """A def for structured response from ChatGPT"""
        planning_thoughts: str
        summary: str

    completion = client.beta.chat.completions.parse(
        model=config['model'],
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ],
        temperature=config['temperature'],
        top_p=config['top_p'],
        response_format=SummarizeResponse
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

    user_message_array += [ "The the current verse is ", vref, "\n" ]


    #check if the config has the boolean summarize_corrections
    correction_summarization_result = None
    if 'summarize_corrections' in config and config['summarize_corrections']:
        correction_summarization_result = summarize_corrections( selected_verse, client, config )
        user_message_array += [ "Correction:\n```\n", correction_summarization_result["summary"],
            "\n```\n\n" ]
    else:
        selected_reflection_loop = selected_verse['reflection_loops'][-1]
        for i,grade in enumerate(selected_reflection_loop['grades']):
            user_message_array += [ "Correction #", i+1, ":\n```\n", grade['comment'], "\n```\n\n" ]

    user_message_array += ["Instructions: Attempt to satisfy all provided instructions for ",
        vref, " to the best of your ",
        "ability. If the instructions are contradictory or mutually exclusive, use your own ",
        "logic to resolve the conflict while prioritizing consistency and alignment with the ",
        "overall goal.  Output your planning_thoughts, the reference ", vref, ", and the updated ",
        "translation for ", vref, ".\n" ]

    user_message = "".join(str(s) for s in user_message_array)


    class ReflectionResponse(BaseModel):
        """A def for structured response from ChatGPT"""
        planning_thoughts: str
        reference: str
        updated_translation: str

    completion = client.beta.chat.completions.parse(
        model=config['model'],
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ],
        temperature=config['temperature'],
        top_p=config['top_p'],
        response_format=ReflectionResponse
    )
    result = completion.choices[0].message.parsed.model_dump()

    if correction_summarization_result:
        result['correction_summarization'] = correction_summarization_result

    return result


def run_config__n_loops( config, api_keys, save_timeout ):
    """
    Run the reflection and grade loop as defined in the grade_reflect_loop.yaml file.

    Each verse is iterated through a specified number of times.
    """
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


        done = False
        while not done:
            action_done = "did nothing"
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
                if vref is not None and not utils.look_up_key( verse, reference_key ) in \
                        over_ridden_references:
                    num_completed_loops = compute_completed_loops( verse )
                    if fewest_loops is None or num_completed_loops < fewest_loops:
                        verse_with_fewest_loops = verse
                        fewest_loops = num_completed_loops

            #check if the verse with the fewest loops has the numer requested by the configuration
            #if it does, we are done.
            if verse_with_fewest_loops is not None and fewest_loops < \
                    config['reflection_loops_per_verse']:
                selected_verse = verse_with_fewest_loops


                common_context = build_common_context( selected_verse, reflection_output, config,
                    over_ridden_references )


                #add a new reflection loop if the current last one is None or is complete.
                last_reflection_loop = selected_verse['reflection_loops'][-1] if len(
                    selected_verse.get('reflection_loops', [])) > 0 else None
                if last_reflection_loop is None or 'graded_verse' in last_reflection_loop:
                    if 'reflection_loops' not in selected_verse:
                        selected_verse['reflection_loops'] = []
                    last_reflection_loop = {}
                    selected_verse['reflection_loops'].append(last_reflection_loop)


                #ok, so now we need to see if this verse has the requested number of grades for this
                #verse otherwise we need to run another grade run on it.
                if last_reflection_loop is None or len(last_reflection_loop.get('grades', [])) < \
                        config['grades_per_reflection_loop']:
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
                    action_done = f"added grade number {len(last_reflection_loop['grades'])} to " \
                        f"verse {utils.look_up_key( selected_verse, reference_key )}"


                else:
                    #we have enough grades, so we need to do the reflection loop
                    reflection_result = perform_reflection( selected_verse, common_context, client,
                        config )

                    #the existing translation to the loop
                    if translation_comment_key:
                        last_reflection_loop['graded_verse_comment'] = \
                            utils.look_up_key( selected_verse, translation_comment_key )
                    last_reflection_loop['graded_verse'] = \
                        utils.look_up_key( selected_verse, translation_key )

                    #and replace it.
                    utils.set_key( selected_verse, translation_key,
                        reflection_result['updated_translation'] )
                    if translation_comment_key:
                        utils.set_key( selected_verse, translation_comment_key,
                            reflection_result['planning_thoughts'] )
                    output_dirty = True
                    action_done = f"reflected on verse {utils.look_up_key( selected_verse,
                        reference_key )}"

                    #keep the correction_summarization if it was produced.
                    if 'correction_summarization' in reflection_result:
                        last_reflection_loop['correction_summarization'] = \
                            reflection_result['correction_summarization']


                #now save if we haven't saved in a while
                if output_dirty and time.time() - last_save > save_timeout:
                    utils.save_jsonl( reflection_output_filename, reflection_output )
                    last_save = time.time()
                    output_dirty = False

            else:
                done = True
                action_done = "done"

            average_grade = compute_translation_grade( reflection_output, config )

            #figure out if we are done because we have not had a grade increase.




            #spit out the current time and the average_grade and action_done
            print( f"{time.strftime('%Y-%m-%d %H:%M:%S')} - Average grade: {average_grade:05.2f} "
                f"- {action_done} - completed loops: {compute_completed_loops(
                verse_with_fewest_loops )}" )

            if "average_grade_csv_log" in config:
                #create the dir if it doesn't exist
                average_grade_csv_log = config['average_grade_csv_log']
                log_dir = os.path.dirname( average_grade_csv_log )
                if not os.path.exists(log_dir):
                    os.makedirs(log_dir)
                with open( average_grade_csv_log, 'a', encoding='utf-8' ) as f:
                    if os.path.getsize(average_grade_csv_log) == 0:
                        f.write( "time,average_grade,action_done,completed_loops\n" )
                    f.write( f"{time.strftime('%Y-%m-%d %H:%M:%S')},{average_grade},{action_done}"
                        f",{compute_completed_loops( verse_with_fewest_loops )}\n" )

    finally:
        #save the reflection output
        if output_dirty:
            utils.save_jsonl( reflection_output_filename, reflection_output )


def run_config__lowest_grade_priority( config, api_keys, save_timeout ):
    """
    Run the reflection loop but with the priority of which verse to process next
    determined by the lowest average grade of the verses.
    """

    client = OpenAI(api_key=utils.look_up_key( api_keys, config['api_key'] ))

    reflection_output_filename = config['reflection_output']

    translation_input = utils.load_jsonl( config['translation_input'] )

    output_dirty = False


    best_grade_found = 0
    iterations_without_improvement = 0
    iterations_without_improvement_max = config['iterations_without_improvement_max']

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


        done = False
        while not done:

            #so each time we run through the loop we do one of the following:
            #make sure all the verses are fully graded.
            #Figure out which verse has the lowest average grade.
            #Run the reflection on that verse which then makes it not have its full verses.
            #The way we know the difference between a reflected verse and a fully graded verse
            #is that a reflected verse has the verse graded as part of the grade structure and
            #then therefore should be considered as having no unanswered grades.

            #We only do one thing at a time to make it so that the content can be saved.
            #so once we do something we skip the rest of the things we could do and go to the end.

            #Loop through all the verses to find one that is not fully graded.
            action_done = "did nothing"
            for verse in reflection_output:
                vref = utils.look_up_key( verse, reference_key )
                if vref is not None and not vref in over_ridden_references:
                    #now need to determine if this verse needs another grade.
                    #It needs another grade if the current number of grades is less then the
                    #requirement or if the graded verse reference is set which means the grade was
                    #already used.
                    if compute_number_unanswered_grades( verse ) < \
                            config['grades_per_reflection_loop']:
                        selected_verse = verse

                        common_context = build_common_context( selected_verse, reflection_output,
                            config, over_ridden_references )
                        new_grade = grade_verse( selected_verse, common_context, client, config )

                        #add the new grade to the reflection loop
                        if 'reflection_loops' not in selected_verse:
                            selected_verse['reflection_loops'] = []
                        if len( selected_verse['reflection_loops'] ) == 0:
                            selected_verse['reflection_loops'].append( {} )
                        if 'graded_verse' in selected_verse['reflection_loops'][-1]:
                            selected_verse['reflection_loops'].append( {} )
                        last_reflection_loop = selected_verse['reflection_loops'][-1]
                        if 'grades' not in last_reflection_loop:
                            last_reflection_loop['grades'] = []
                        last_reflection_loop['grades'].append(new_grade)
                        output_dirty = True
                        action_done = f"added grade number {len(last_reflection_loop['grades'])} " \
                            f"of grade {new_grade['grade']} " \
                            f"to verse {utils.look_up_key( selected_verse, reference_key )}"

                        #now break so we can get to the save section.
                        break
            else:
                #if we got here then all the verses are fully graded.
                #this is the moment to test if the grade is improving or not.
                average_grade = compute_translation_grade( reflection_output, config )
                if average_grade > best_grade_found:
                    best_grade_found = average_grade
                    iterations_without_improvement = 0
                    print( f"New best grade: {best_grade_found}" )
                else:
                    iterations_without_improvement += 1

                if iterations_without_improvement > iterations_without_improvement_max:
                    done = True
                    action_done = "done because of iterations without improvement"


                #If we are not done pick out what verse has the lowest average grade.
                if not done:
                    lowest_grade_found = None
                    lowest_graded_verse = None
                    if not "debug_force_vref" in config:
                        for verse in reflection_output:
                            vref = utils.look_up_key( verse, reference_key )
                            if vref is not None and not vref in over_ridden_references:
                                verse_grade = compute_verse_grade( verse, config )
                                if lowest_grade_found is None or lowest_grade_found > verse_grade:
                                    lowest_grade_found = verse_grade
                                    lowest_graded_verse = verse
                    else:
                        for verse in reflection_output:
                            vref = utils.look_up_key( verse, reference_key )
                            if vref == config['debug_force_vref']:
                                lowest_graded_verse = verse


                    if lowest_graded_verse is not None:
                        selected_verse = lowest_graded_verse

                        common_context = build_common_context( selected_verse, reflection_output,
                            config, over_ridden_references )
                        reflection_result = perform_reflection( selected_verse, common_context,
                            client, config )

                        #add the new reflection to the reflection loop
                        #the existing translation to the loop
                        last_reflection_loop = selected_verse['reflection_loops'][-1]
                        if translation_comment_key:
                            last_reflection_loop['graded_verse_comment'] = utils.look_up_key(
                                selected_verse, translation_comment_key )
                        last_reflection_loop['graded_verse'] = utils.look_up_key( selected_verse,
                            translation_key )

                        #and replace it.
                        utils.set_key( selected_verse, translation_key,
                            reflection_result['updated_translation'] )
                        if translation_comment_key:
                            utils.set_key( selected_verse, translation_comment_key,
                                reflection_result['planning_thoughts'] )
                        output_dirty = True
                        action_done = f"reflected on verse {utils.look_up_key( selected_verse,
                            reference_key )}"

                        #keep the correction_summarization if it was produced.
                        if 'correction_summarization' in reflection_result:
                            last_reflection_loop['correction_summarization'] = \
                                reflection_result['correction_summarization']
                    else:
                        action_done = "Didn't find a verse to reflect on.  So done."
                        done = True



            #now save if we haven't saved in a while
            if output_dirty and time.time() - last_save > save_timeout:
                utils.save_jsonl( reflection_output_filename, reflection_output )
                last_save = time.time()
                output_dirty = False

            #output the current status
            average_grade = compute_translation_grade( reflection_output, config )
            #spit out the current time and the average_grade and action_done

            #output
            #best_grade_found
            #iterations_without_improvement

            print( f"{time.strftime('%Y-%m-%d %H:%M:%S')} - Average grade: {average_grade:05.2f} "
                f"- {action_done} - Best grade: {best_grade_found:05.2f} - Iterations without "
                f"improvement: {iterations_without_improvement}" )


            #run the log
            if "average_grade_csv_log" in config:
                #create the dir if it doesn't exist
                average_grade_csv_log = config['average_grade_csv_log']
                log_dir = os.path.dirname( average_grade_csv_log )
                if not os.path.exists(log_dir):
                    os.makedirs(log_dir)
                with open( average_grade_csv_log, 'a', encoding='utf-8' ) as f:
                    if os.path.getsize(average_grade_csv_log) == 0:
                        f.write( "time,average_grade,action_done,best_grade_found,"
                            "iterations_without_improvement\n" )
                    f.write( f"{time.strftime('%Y-%m-%d %H:%M:%S')},{average_grade},{action_done},"
                        f"{best_grade_found},{iterations_without_improvement}\n" )

    finally:
        #save the reflection output
        if output_dirty:
            utils.save_jsonl( reflection_output_filename, reflection_output )


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
        if config['active']:
            print( f"Running config {config_name}" )
            if config.get( "mode", "" ) == "lowest_grade_priority":
                run_config__lowest_grade_priority( config, api_keys, save_timeout )
            else:
                run_config__n_loops( config, api_keys, save_timeout )

if __name__ == "__main__":
    main()

    print( "Done!" )
