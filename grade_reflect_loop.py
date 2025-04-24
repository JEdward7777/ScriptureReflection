"""
This builds on the lessons learned from do_reflection.py and do_chapter_reflection.py as well as
grade_output.py .  It incorperates the full loop into one file so the stages do not need to be 
manualy iterated with the configuration files.  It uses about a chapter's worth of context but
only updates one verse at a time.  It outputs the current average grade of the translation while
it is running.  The intermediate output is saved in new entries in the output translation jsonl 
file.
"""

# pylint: disable=C0302

import os
import time
import copy
import json
import sys
from collections import defaultdict

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

ITERATIONS_PASS_COMMENT_DEFAULT = 3
def compute_reflection_loops_needed( verse, config ):
    """
    Compute the number of loops that are needed for a given verse.
    """
    #The default count is from reflection_loops_per_verse, but if the verse has had
    #comments touch it, then that gets recorded in comment_mod_loop_count and we want to
    #go past that amount by iterations_pass_comment
    return max( verse.get( 'comment_mod_loop_count', -ITERATIONS_PASS_COMMENT_DEFAULT ) + \
                    config.get( 'iterations_pass_comment', ITERATIONS_PASS_COMMENT_DEFAULT),
                    config.get( 'reflection_loops_per_verse', 0 ) )

def compute_number_unanswered_grades( verse, config ):
    """
    Determine the number of grades that have not been answered by a reflection.
    """
    if 'reflection_loops' not in verse:
        return 0

    last_reflection_loop = verse['reflection_loops'][-1]

    #if the current reflection loop has had reflection
    #then we say we haven't graded yet unless it is the final loop.
    if 'graded_verse' in last_reflection_loop:
        if compute_reflection_loops_needed( verse, config ) > len(verse['reflection_loops']):
            return 0

    return len(last_reflection_loop['grades'])

def verse_needs_finialization( verse, config ):
    """
    A verse needs finilized if there has been the correct number
    of loops and the last set of grades have been reflected on.
    """
    if len(verse.get('reflection_loops',[])) < max(1,compute_reflection_loops_needed( verse,
            config )):
        return False

    #This isn't true.  We will just set graded_verse ourselves when we do the finalization.
    #if 'graded_verse' not in verse['reflection_loops'][-1]:
    #    return False

    #don't really need this because the code shouldn't get this far if there is anything to
    #grade, but adding it to be complete.
    if len(verse['reflection_loops'][-1]['grades']) < config['grades_per_reflection_loop']:
        return False

    return True

def verse_is_finalized( verse ):
    """
    When running verses from lowest score to highest,
    a verse is finalized if the versersion with the best grade it got
    is brought to the front.
    """
    if 'reflection_is_finalized' not in verse:
        return False

    return verse['reflection_is_finalized']


def finalize_verse( verse, config ):
    """
    When running verses from lowest score to highest,
    a verse is finalized if the versersion with the best grade it got
    is brought to the front.
    """
    if 'reflection_loops' not in verse:
        return

    if verse_is_finalized( verse ):
        return

    if not verse_needs_finialization( verse, config ):
        return

    #compute_verse_grade has a side effect of making all
    #the average grades cached.
    compute_verse_grade( verse, config )


    first_index_considered = verse.get( 'comment_mod_loop_count', 0 )

    best_loop = None
    best_grade = None
    for reflection_loop in verse['reflection_loops'][first_index_considered:]:
        if 'average_grade' in reflection_loop:
            if best_loop is None or best_grade <= reflection_loop['average_grade']:
                best_loop = reflection_loop
                best_grade = reflection_loop['average_grade']

    if best_loop is not None:
        #make sure the last thing graded has its verse marked.
        if not 'graded_verse' in verse['reflection_loops'][-1]:
            verse['reflection_loops'][-1]['graded_verse'] = \
                utils.look_up_key( verse, config['translation_key'] )
            if 'translation_comment_key' in config:
                verse['reflection_loops'][-1]['graded_verse_comment'] = \
                    utils.look_up_key( verse, config['translation_comment_key'] )

        #now overwrite the official verse with verse with the best grade.
        utils.set_key( verse, config['translation_key'],
            best_loop['graded_verse'] )
        if 'translation_comment_key' in config:
            utils.set_key( verse, config['translation_comment_key'],
                best_loop['graded_verse_comment'] )

        #now mark it as finalized.
        verse['reflection_is_finalized'] = True
        verse['reflection_finalized_grade'] = best_grade


def compute_grade_for_reflection_loop( reflection_loop, config ):
    """
    Compute the average grade of a reflection loop.
    """
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

    #if the verse has been finalized, just return the finalized grade
    #This is where the best graded translation was swapped out
    #so the grade on the last reflection loop is not nescessary
    #selected.
    if verse_is_finalized(verse):
        return verse['reflection_finalized_grade']

    #iterate backwords through the reflection_loops until we find
    #one that we can get a grade from.
    for reflection_loop in reversed(verse['reflection_loops']):
        loop_grade = compute_grade_for_reflection_loop( reflection_loop, config )
        if loop_grade is not None:
            return loop_grade

    return None


def compute_translation_grade( translation, config ):
    """
    Compute the average grade of the translation.
    """
    verse_count = 0
    verse_sum = 0

    for verse_line_number,verse in enumerate(translation):
        if 'start_line' in config and verse_line_number < config['start_line']-1:
            continue
        if 'end_line' in config and verse_line_number > config['end_line']-1:
            break

        verse_grade = compute_verse_grade( verse, config )
        if verse_grade is not None:
            verse_count += 1
            verse_sum += verse_grade

    if verse_count == 0:
        return 0

    return verse_sum / verse_count

def construct_translation_objective( verse, config, indexed_comments ):
    """
    This returns the translation objective from the config, but also
    Adds in the comments which have been left for this verse.
    """
    vref = utils.look_up_key( verse, config['reference_key'] )
    comments = [x['comment'] for x in indexed_comments.get( vref, [] )]
    result = "\n".join( [config.get( 'translation_objective', '' )] + comments )
    return result

def build_common_context( selected_verse, reflection_output, config, over_ridden_references,
        indexed_comments ):
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
        "Translation Objective: ",
        construct_translation_objective( selected_verse, config, indexed_comments ), "\n\n",
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

    completion = utils.use_model( client,
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
    relevant_loops = selected_verse.get('reflection_loops',[])[selected_verse.get('comment_mod_loop_count',0):-1]
    if relevant_loops:
        user_message_array += ['##Edit History:\n']
        #relevant_loops exclude the current loop as well as ones before a comment was added.
        for i,reflection_loop in enumerate(relevant_loops):
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

    completion = utils.use_model( client,
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

    if 'dictionary' in config:
        if 'dictionary_description' in config:
            user_message_array += ["\n" + config['dictionary_description'] + "\n" ]
        user_message_array.append( json.dumps( config['dictionary'], ensure_ascii=False ) + "\n\n" )


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

    completion = utils.use_model( client,
        model=config.get( 'reflection-model', config['model'] ),
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

    indexed_comments = load_and_index_comments( config )

    output_dirty = False

    #load the result if we didn't finish last time.
    if os.path.exists(reflection_output_filename):
        reflection_output = utils.load_jsonl( reflection_output_filename )
    else:
        #otherwise load the existing translation and blank out all the translation keys.
        reflection_output = copy.deepcopy( translation_input )
    reflection_output_unmodified = copy.deepcopy( reflection_output )

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

                        #only select this verse if it isn't completed.
                        if num_completed_loops < compute_reflection_loops_needed( verse, config ):

                            #also only select this verse if it isn't frozen from ai.
                            if not verse.get( "ai_halted", False ):
                                verse_with_fewest_loops = verse
                                fewest_loops = num_completed_loops

            #check if we found the verse with the fewest loops that has the number requested by the
            #configuration if it does, we are done.
            if verse_with_fewest_loops is not None:
                selected_verse = verse_with_fewest_loops


                common_context = build_common_context( selected_verse, reflection_output, config,
                    over_ridden_references, indexed_comments )


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
                    action_done = f"reflected on verse {utils.look_up_key( selected_verse, reference_key )}"

                    #keep the correction_summarization if it was produced.
                    if 'correction_summarization' in reflection_result:
                        last_reflection_loop['correction_summarization'] = \
                            reflection_result['correction_summarization']


                #now save if we haven't saved in a while
                if output_dirty and time.time() - last_save > save_timeout:
                    #utils.save_jsonl( reflection_output_filename, reflection_output )
                    reflection_output = utils.save_jsonl_updates( reflection_output_filename, reflection_output,
                        reflection_output_unmodified, reference_key )
                    reflection_output_unmodified = copy.deepcopy( reflection_output )
                    last_save = time.time()
                    output_dirty = False

            else:
                done = True
                action_done = "done"

            average_grade = compute_translation_grade( reflection_output, config )

            #figure out if we are done because we have not had a grade increase.




            #spit out the current time and the average_grade and action_done
            print( f"{time.strftime('%Y-%m-%d %H:%M:%S')} - Average grade: {average_grade:05.2f} "
                f"- {action_done} - completed loops: {compute_completed_loops( verse_with_fewest_loops )}" )

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
            #utils.save_jsonl( reflection_output_filename, reflection_output )
            reflection_output = utils.save_jsonl_updates( reflection_output_filename, reflection_output,
                reflection_output_unmodified, reference_key )
            reflection_output_unmodified = copy.deepcopy( reflection_output )

def load_and_index_comments( config ):
    """Loads the comments left by the streamlit app and returns them indexed by
    The verse they apply to"""
    collected_comments_file = config.get( 'collected_comments_file', os.path.join(
        'output','comments', os.path.basename(config['reflection_output'] )) )
    if os.path.exists(collected_comments_file):
        collected_comments = utils.load_jsonl(collected_comments_file)
    else:
        collected_comments = []

    indexed_comments = defaultdict( lambda: [] )
    for comment in collected_comments:
        for vref in comment['ids']:
            indexed_comments[vref].append( comment )
    return indexed_comments

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
    iterations_without_improvement_max = config.get('iterations_without_improvement_max', float('inf') )


    indexed_comments = load_and_index_comments( config )


    if 'start_line' in config:
        print( "Focusing on and after start_line", config['start_line'] )

    if 'end_line' in config:
        print( "Focusing on and before end_line", config['end_line'] )

    print( f"Using the model {config['model']}" )
    if 'reflection-model' in config:
        print( f"Using the model {config['reflection-model']} for reflection.")

    #load the result if we didn't finish last time.
    if os.path.exists(reflection_output_filename):
        reflection_output = utils.load_jsonl( reflection_output_filename )
    else:
        #otherwise load the existing translation and blank out all the translation keys.
        reflection_output = copy.deepcopy( translation_input )
    reflection_output_unmodified = copy.deepcopy( reflection_output )

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
            for verse_line_number,verse in enumerate(reflection_output):
                if 'start_line' in config and verse_line_number < config['start_line']-1:
                    continue
                if 'end_line' in config and verse_line_number > config['end_line']-1:
                    continue #not break because we have a for else which will get skiped.

                #if a verse is marked that the ai is not supposed to touch it, then skip it.
                if verse.get( 'ai_halted', False ):
                    continue

                vref = utils.look_up_key( verse, reference_key )
                if vref is not None and not vref in over_ridden_references:
                    #check to see if this verse actually needs a reflection skip.
                    #This happens if a comment was applied to the verse, then the latest
                    #grades are not valid anymore so we need a new grading round before
                    #we do reflection.
                    reflection_loops = verse.get('reflection_loops', [] )
                    if reflection_loops:
                        last_reflection_loop = verse['reflection_loops'][-1]

                        if len(reflection_loops) <= verse.get( 'comment_mod_loop_count', -1 ):

                            graded_verse_inserted = 'graded_verse' in last_reflection_loop
                            if not graded_verse_inserted or verse_is_finalized( verse ):
                                if not graded_verse_inserted:
                                    #just copy the verse up and then this loop is "closed" and new
                                    #grades based on the new comments will begin.
                                    if translation_comment_key:
                                        last_reflection_loop['graded_verse_comment'] = utils.\
                                            look_up_key( verse, translation_comment_key )
                                    last_reflection_loop['graded_verse'] = utils.look_up_key(
                                        verse, translation_key )

                                #Revert finilization
                                if verse.get( 'reflection_is_finalized', False ):
                                    verse['reflection_is_finalized'] = False

                                output_dirty = True
                                if not graded_verse_inserted:
                                    action_done = "Skipped reflection " \
                                        f"on loop {len(verse['reflection_loops'])} " \
                                        f"for verse {utils.look_up_key( verse, reference_key )}"
                                else:
                                    action_done = "Reverted finalization " \
                                        f"on loop {len(verse['reflection_loops'])} " \
                                        f"for verse {utils.look_up_key( verse, reference_key )}"
                                break #get to the save section.

                    #now need to determine if this verse needs another grade.
                    #It needs another grade if the current number of grades is less then the
                    #requirement or if the graded verse reference is set which means the grade was
                    #already used.
                    if compute_number_unanswered_grades( verse, config ) < \
                            config['grades_per_reflection_loop']:
                        selected_verse = verse

                        common_context = build_common_context( selected_verse, reflection_output,
                            config, over_ridden_references, indexed_comments )
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
                        #Revert finilization
                        if verse.get( 'reflection_is_finalized', False ):
                            verse['reflection_is_finalized'] = False
                        if verse.get( 'human_reviewed', False ):
                            verse['human_reviewed'] = False
                        output_dirty = True
                        action_done = f"added grade number {len(last_reflection_loop['grades'])} " \
                            f"on loop {len(selected_verse['reflection_loops'])} " \
                            f"of grade {new_grade['grade']} " \
                            f"to verse {utils.look_up_key( selected_verse, reference_key )}"

                        #now break so we can get to the save section.
                        break
            else:
                #if we got here then all the verses are fully graded.
                average_grade = compute_translation_grade( reflection_output, config )


                #see if this config is set to manual mode, in which case we do not loop.
                if config.get( 'manual_edit_mode', False ):
                    done = True
                    action_done = "done because grading is complete and configuration is in manual_edit_mode."
                else:

                    #this is the moment to test if the grade is improving or not.
                    iterations_without_improvement += 1
                    if average_grade > best_grade_found:
                        print( f"New best grade: {average_grade} after "
                            f"{iterations_without_improvement} iterations.  Improvement of "
                            f"{average_grade - best_grade_found}" )
                        best_grade_found = average_grade
                        iterations_without_improvement = 0


                    if iterations_without_improvement > iterations_without_improvement_max:
                        done = True
                        action_done = "done because of iterations without improvement"


                #If we are not done pick out what verse has the lowest average grade.
                if not done:
                    lowest_grade_found = None
                    lowest_graded_verse = None
                    if not "debug_force_vref" in config:

                        for verse_line_number,verse in enumerate(reflection_output):
                            if 'start_line' in config and verse_line_number < \
                                    config['start_line']-1:
                                continue
                            if 'end_line' in config and verse_line_number > config['end_line']-1:
                                break

                            if verse.get( "ai_halted", False ):
                                continue

                            #if a verse is marked for grading only, then it will get graded, 
                            #but we don't want to select it for reflection
                            if verse.get( 'grade_only', False ):
                                continue

                            vref = utils.look_up_key( verse, reference_key )
                            if vref is not None and not vref in over_ridden_references and \
                                    not verse_is_finalized( verse ):
                                verse_grade = compute_verse_grade( verse, config )
                                if lowest_grade_found is None or lowest_grade_found > verse_grade:
                                    lowest_grade_found = verse_grade
                                    lowest_graded_verse = verse
                    else:
                        for verse in reflection_output:
                            vref = utils.look_up_key( verse, reference_key )
                            if vref == config['debug_force_vref']:
                                lowest_graded_verse = verse

                    #have a check to make sure the lowest grade found is below the finish limit.
                    if lowest_grade_found is not None and \
                            lowest_grade_found > config.get('highest_grade_to_reflect', float('inf')):
                        action_done = f"lowest unfinalized grade {lowest_grade_found} is above highest grade to reflect {config['highest_grade_to_reflect']}"
                        done = True

                    elif lowest_graded_verse is not None:
                        selected_verse = lowest_graded_verse


                        #If the verse has enough loops on it, then it needs to be finalized
                        #where we just pick the version which had the highest grade, make it
                        #the active translation and then mark the verse as finalized.
                        if verse_needs_finialization( selected_verse, config ):
                            finalize_verse( selected_verse, config )
                            action_done = f"finalized verse {utils.look_up_key( selected_verse, reference_key )}"
                            output_dirty = True

                            print( f"Finilizing {utils.look_up_key( selected_verse, reference_key )}\n" )
                            print( f"old: {selected_verse['reflection_loops'][-1]['graded_verse']}" )
                            print( f"new: {utils.look_up_key( selected_verse, translation_key )}\n" )
                            print( f"old grade: {selected_verse['reflection_loops'][-1]['average_grade']}" )
                            print( f"new grade: {compute_verse_grade( selected_verse, config )}\n" )
                        else:

                            #otherwise we go ahead and run a reflection run on it.

                            common_context = build_common_context( selected_verse,
                                reflection_output, config, over_ridden_references,
                                indexed_comments )
                            reflection_result = perform_reflection( selected_verse, common_context,
                                client, config )

                            print( f"Working on verse {utils.look_up_key( selected_verse, reference_key )} which has grade {compute_verse_grade(selected_verse, config )}\n" )

                            if 'correction_summarization' in reflection_result:
                                print( reflection_result['correction_summarization']['summary'] + \
                                     "\n" )

                            print( f"source: {utils.look_up_key( selected_verse, config['source_key'] )}" )
                            print( f"old: {utils.look_up_key( selected_verse, translation_key )}" )
                            print( f"new: {reflection_result['updated_translation']}\n" )


                            #add the new reflection to the reflection loop
                            #the existing translation to the loop
                            last_reflection_loop = selected_verse['reflection_loops'][-1]
                            if translation_comment_key:
                                last_reflection_loop['graded_verse_comment'] = utils.look_up_key(
                                    selected_verse, translation_comment_key )
                            last_reflection_loop['graded_verse'] = utils.look_up_key(
                                selected_verse, translation_key )

                            #and replace it.
                            utils.set_key( selected_verse, translation_key,
                                reflection_result['updated_translation'] )
                            if translation_comment_key:
                                utils.set_key( selected_verse, translation_comment_key,
                                    reflection_result['planning_thoughts'] )
                            output_dirty = True
                            action_done = f"reflected on verse {utils.look_up_key( selected_verse,reference_key )}"


                            if verse.get( 'human_reviewed', False ):
                                verse['human_reviewed'] = False

                            #keep the correction_summarization if it was produced.
                            if 'correction_summarization' in reflection_result:
                                last_reflection_loop['correction_summarization'] = \
                                    reflection_result['correction_summarization']
                    else:
                        action_done = "Didn't find a verse to reflect on.  So done."
                        done = True



            #now save if we haven't saved in a while
            if output_dirty and time.time() - last_save > save_timeout:
                #utils.save_jsonl( reflection_output_filename, reflection_output )
                reflection_output = utils.save_jsonl_updates( reflection_output_filename, reflection_output,
                    reflection_output_unmodified, reference_key )
                reflection_output_unmodified = copy.deepcopy( reflection_output )
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

            sys.stdout.flush()

    finally:
        #save the reflection output
        if output_dirty:
            #utils.save_jsonl( reflection_output_filename, reflection_output )
            reflection_output = utils.save_jsonl_updates( reflection_output_filename, reflection_output,
                reflection_output_unmodified, reference_key )
            reflection_output_unmodified = copy.deepcopy( reflection_output )


def main():
    """
    Run the reflection and grade loop as defined in the grade_reflect_loop.yaml file.
    """

    def run_mode(config_name, config):
        print( f"Running config {config_name}" )
        if config.get( "mode", "lowest_grade_priority" ) == "lowest_grade_priority":
            run_config__lowest_grade_priority( config, api_keys, save_timeout )
        else:
            run_config__n_loops( config, api_keys, save_timeout )

    with open( 'key.yaml', encoding='utf-8' ) as keys_f:
        api_keys = yaml.load(keys_f, Loader=yaml.FullLoader)

    with open( 'grade_reflect_loop.yaml', encoding='utf-8' ) as f:
        grade_reflect_loop_yaml = yaml.load(f, Loader=yaml.FullLoader)

    save_timeout = grade_reflect_loop_yaml.get( 'global_configs', {} ).get( 'save_timeout', 20 )

    for config_name, config in grade_reflect_loop_yaml['configs'].items():
        if config['active']:




            if 'tee_output_filename' in config:
                tee_output_filename = config['tee_output_filename']

                with open( tee_output_filename, 'a', encoding='utf-8' ) as tee_f:

                    std_out_save = sys.stdout
                    std_err_save = sys.stderr

                    try:
                        sys.stdout = utils.Tee(sys.stdout, tee_f)
                        sys.stderr = utils.Tee(sys.stderr, tee_f)

                        run_mode(config_name, config)
                    finally:
                        sys.stdout = std_out_save
                        sys.stderr = std_err_save
            else:
                run_mode(config_name, config)





if __name__ == "__main__":
    main()

    print( "Done!" )
