
import os
import time
from datetime import datetime
import json
import re

from openai import OpenAI
from pydantic import BaseModel
from typing import List

from format_utilities import get_config_for

import utils
from format_utilities import get_sorted_verses
from output_formatters.pdf_report import summarize_verse_report, translate_verse_report

import yaml


def normalize_review_header( report, report_language, translate_label ):
    #we want to go with "**Combined Review**:\n" and all other versions should be replaced with it.

    if translate_label("**Combined Review**") + ":" in report.split('\n'):
        return report

    #here we only have things to fix.
    swaps_before_translated = [
        "**Combined Review**",
        "**Review Summary**:",
        "**Combined Review Summary**:",
        "**Overall Review Summary**:",
        "**Overall Review**:",
        "### Combined Review",
    ]
    swaps = []
    for swap in swaps_before_translated:
        swaps += translate_label( swap, include_synonyms=True )

    if report_language == "Spanish":
        swaps += [ "**Reseña General**:",
         "**Revisión Resumida**", 
         "**Revisión combinada**:", 
         "**Revisión Consolidada**:",
         "**Resumen de Revisiones**:",
         "### Resumen de Revisiónes:",
           "**Resumen de Revisiónes**: ",
           "**Resumen de Revisión**: ",
         "### Revisión Consolidada:",
         "**Revisión**: ",
          ]

    reg_swaps = ["\\*\\*Combined Review\\*\\*:?(?!\n)", "\\*\\*Combined Review\\*\\*:?[ \n:]*(_\\((Overall|Average)? ?Grade [^)]*\\)_[ \n:]*)?"]
    #reg_swaps = [ translate_label(x) for x in reg_swaps ]

    if report_language == "Spanish":
        reg_swaps += [
            "\\*\\*(((R|r)eseña)|((R|r)evisión)) (((G|g)eneral)|((R|r)esumida)|((C|c)ombinada)|((C|c)onsolidada))\\*\\*[ \n:]*",
            #"\\*\\*Revisión\\*\\*( _\\(Calificación \\d+\\)_)[ \n:]*",
        ]

    for swap in swaps:
        if swap in report:
            report = report.replace(swap, translate_label("**Combined Review**") + ":\n")
            break
    for reg_swap in reg_swaps:
        report = re.sub(reg_swap, translate_label("**Combined Review**") + ":\n", report)

    if translate_label("**Combined Review**") + ":" in report.split('\n'):
        return report

    return report



def copy_over_summary( raw_report, summarized_report, target_language, translate_label ):
    """
    We are having trouble having the source and translation getting modified by ChatGPT,
    so here we try to just snip off the summarized portion of the report and use
    it on the raw report.
    """
    summarized_report = normalize_review_header( summarized_report, target_language, translate_label )

    spliced_report = []

    for line in raw_report.split('\n'):
        if not line.startswith( "**" + translate_label("Review") + " 1**" ):
            spliced_report.append( line )
        else:
            break

    found_review_line = False
    for line in summarized_report.split('\n'):
        if line.startswith( translate_label("**Combined Review**") ):
            found_review_line = True

        if found_review_line:
            spliced_report.append( line )

    if not found_review_line:
        print( "Couldn't find review line in summarized report" )

    return '\n'.join(spliced_report)





def run_report_checks( report, source, translation, suggested_translation, report_language, translate_label ):
    #So the report has to have the source and the translation still in it.
    #It also needs to have a review in it.

    chars_to_ignore = [ ';', '.', ',', '―','¿', '?', '»', '«', '“', '¡', '!', ')', '(', '”', '·', '—', '1','2','3','4','5','6','7','8','9','0']

    for char in chars_to_ignore:
        source = source.replace(char, '')
        translation = translation.replace(char, '')
        if suggested_translation:
            suggested_translation = suggested_translation.replace(char, '')
        report = report.replace(char, '')

    review_finding_options = []
    review_finding_options += translate_label( 'Review', include_synonyms=True )
    review_finding_options += translate_label( '**Combined Review**', include_synonyms=True )
    review_finding_options += translate_label( '**Consolidated Review**', include_synonyms=True )
    review_finding_options += translate_label( '**Overall Review**', include_synonyms=True )
    review_finding_options += translate_label( '**Overall Review Summary**', include_synonyms=True )

    if report_language == "Spanish":
        review_finding_options += [ 'Reseña', 'Revisiones Combinadas', 'Resumen de Revisiones' ]

    for option in review_finding_options:
        if option.lower() in report.lower():
            index_of_review = report.lower().find( option.lower() )
            portion_before_review = report[:index_of_review]
            break
    else:
        print( "Missed review" )
        return False

    if source not in portion_before_review:
        #see if each word of the source is in the report because ChatGPT might have
        #put the translations inline.
        for word in source.split():
            if word not in portion_before_review:
                print( f"Missed source word: {word}" )
                return False

    if translation not in portion_before_review:
        #see if each word of the translation is in the report because ChatGPT might have
        #put the translations inline.
        for word in translation.split():
            if word not in portion_before_review:
                print( f"Missed translation word: {word}" )
                return False

    if suggested_translation:
        if suggested_translation not in portion_before_review:
            for word in suggested_translation.split():
                if word not in portion_before_review:
                    print( f"Missed suggested translation word: {word}" )
                    return False

    return True




def run(file):
    """Converts the output of easy_draft to a sorted report"""

    print( f"converting {file} to sorted report" )

    this_config = get_config_for( file )
    if this_config is None:
        this_config = {}

    output_file = this_config.get( 'output_file', os.path.splitext(file)[0] )
    if not os.path.exists("output/reports/"):
        os.makedirs("output/reports/")

    translation_key = this_config.get( 'translation_key', ['fresh_translation','text'] )
    reference_key = this_config.get( 'reference_key', ['vref'] )
    source_key = this_config.get( 'source_key', ['source'] )

    report_first_iteration = this_config.get('reports',{}).get('report first iteration', False )

    original_content = utils.load_jsonl(f"output/{file}")

    if "end_line" in this_config:
        end_line = this_config["end_line"]-1
        original_content = original_content[:end_line+1]
    if "start_line" in this_config:
        start_line = this_config["start_line"]-1
        original_content = original_content[start_line:]

    if "suggested_translation" in this_config.get( "reports", {} ):
        suggested_translation_filename = this_config["reports"]["suggested_translation"]
        if not suggested_translation_filename.endswith( ".jsonl" ):
            suggested_translation_filename += ".jsonl"
        suggested_translation = utils.load_jsonl( os.path.join( "output", suggested_translation_filename ) )
        hashed_suggested_translation = { utils.look_up_key( x, reference_key ): x for x in suggested_translation }
    else:
        hashed_suggested_translation = None


    summary_cache = utils.load_json(f"output/summary_cache/{output_file}.json",{})
    summary_cache_modified = False
    summary_cache_save_time = time.time()

    translation_cache = utils.load_json(f"output/translation_cache/{output_file}.json",{})
    translation_cache_modified = False
    translation_cache_save_time = time.time()

    #now sort it by the grade.
    sorted_content, get_grade = get_sorted_verses( original_content, reference_key, sort_on_first=report_first_iteration )

    sorted_content = [x for x in sorted_content if get_grade(x) != float('inf')]

    client = None
    if 'api_key' in this_config and this_config.get( 'reports', {} ).get( 'summarized sorted report enabled', False ):
        with open( 'key.yaml', encoding='utf-8' ) as keys_f:
            api_keys = yaml.load(keys_f, Loader=yaml.FullLoader)
            client = OpenAI(api_key=utils.look_up_key( api_keys, this_config['api_key'] ))

    report_language = this_config.get( 'reports', {} ).get( "report language", "English" )

    def translate_label( label, instruction = '', include_synonyms = False ):
        if report_language == "English":
            if include_synonyms:
                return [label]
            return label

        system_message = "You are a translation consultant, creating labels in a target language"
        user_message_array = []
        if instruction:
            user_message_array += [ "Translate the following label which ", instruction, " into " + report_language + " preserving the markdown formating:" ]
        else:
            user_message_array += [ "Translate the following label into " + report_language + " preserving the markdown formating:" ]

        user_message_array += [ "\n{\"label\": \"", label, "\"}" ]
        user_message = "".join(user_message_array)

        if user_message in translation_cache:
            result = json.loads(translation_cache[user_message])
            if include_synonyms:
                return [result['translated_label']] + result['synonyms']
            else:
                return result['translated_label']

        if not client:
            if include_synonyms:
                return [label]
            return label

        class LabelResponse(BaseModel):
            translated_label: str
            synonyms: List[str]

        completion = utils.use_model( client,
            model=this_config.get( 'model', 'gpt-4o-mini' ),
            messages=[
                { "role": "system", "content": system_message },
                { "role": "user", "content": user_message }
            ],
            temperature=this_config.get('temperature', 1.2),
            top_p=this_config.get('top_p', 0.9),
            response_format=LabelResponse
        )

        model_dump = completion.choices[0].message.parsed.model_dump()
        translated_label = model_dump['translated_label']

        #don't let the model add markdown markers.
        if "*" not in label and "*" in translated_label:
            translated_label = translated_label.replace("*", "")

        if label.startswith( "**" ):
            for i in range( len( model_dump['synonyms'] ) ):
                if not model_dump['synonyms'][i].startswith( "**" ):
                    model_dump['synonyms'][i] = "**" + model_dump['synonyms'][i]

        if label.startswith( "### " ):
            for i in range( len( model_dump['synonyms'] ) ):
                if not model_dump['synonyms'][i].startswith( "### " ):
                    model_dump['synonyms'][i] = "### " + model_dump['synonyms'][i]

        if label.endswith( "**" ):
            for i in range( len( model_dump['synonyms'] ) ):
                if not model_dump['synonyms'][i].endswith( "**" ):
                    model_dump['synonyms'][i] = model_dump['synonyms'][i] + "**"

        if label.endswith( "**:" ):
            for i in range( len( model_dump['synonyms'] ) ):
                if not model_dump['synonyms'][i].endswith( "**:" ):
                    model_dump['synonyms'][i] = model_dump['synonyms'][i] + "**:"


        translation_cache[user_message] = json.dumps(model_dump,ensure_ascii=False)
        nonlocal translation_cache_modified
        translation_cache_modified = True


        if include_synonyms:
            return [translated_label] + model_dump['synonyms']
        else:
            return translated_label




    if sorted_content:

        is_first_raw = True
        is_first_summarized = True

        start_time = time.time()

        #first output a header for the report
        for verse_i, verse in enumerate(sorted_content):

            current_time = time.time()
            elapsed_time = current_time - start_time
            #estimated_end_time = len(sorted_content)/(verse_i+1) * elapsed_time + current_time

            # Calculate estimated total time needed
            estimated_total_time = len(sorted_content)/(verse_i+1) * elapsed_time
            # Estimated end time is start time + total estimated duration
            estimated_end_time = start_time + estimated_total_time
            print( f"Processing verse {verse_i+1} of {len(sorted_content)} - {elapsed_time:.2f} seconds elapsed - estimated {estimated_end_time - current_time:.2f} seconds left, estimated end time {datetime.fromtimestamp(estimated_end_time).strftime('%Y-%m-%d %I:%M:%S %p')}" )

            vref = utils.look_up_key(verse, reference_key)
            translation = utils.look_up_key(verse, translation_key)
            grade = get_grade(verse)
            source = utils.look_up_key(verse, source_key, translate_label("*Source missing*"))

            #if we are doing a first iteration report,
            #then let the translation be what the first reflection loop was grading.
            #also the grade is that.
            if report_first_iteration:
                reflection_loop = verse.get( 'reflection_loops', [] )
                if reflection_loop:
                    first_loop = reflection_loop[0]
                    graded_verse = first_loop.get( 'graded_verse', '' )
                    if graded_verse:
                        if graded_verse != translation:
                            translation = graded_verse


            raw_report_array = [
                f"**{vref}**: _(", translate_label( "Grade", "Specifies the reviewers grade." ), f" {grade:.1f})_\n\n",
                translate_label( "**Source**", "Specifies the source text." ), ":\n",
                "\n".join( f"> {line}" for line in source.split('\n') ),
                "\n\n",
                translate_label( "**Translation**", "Specifies the translated text." ), ":\n",
                "\n".join( f"> {line}" for line in translation.split('\n') ),
                "\n\n", ]

            suggested_translation = None
            if hashed_suggested_translation:
                suggested_verse = hashed_suggested_translation.get( vref, None )
                suggested_translation = utils.look_up_key( suggested_verse, translation_key )
                if not suggested_translation or suggested_translation == translation:
                    suggested_translation = None
            elif report_first_iteration:
                #if we are doing a report on the verse which was graded first,
                #then if there was iteration, then that can be the suggested translation.
                current_translation = utils.look_up_key( verse, translation_key )
                if current_translation and current_translation != translation:
                    suggested_translation = current_translation


            if suggested_translation:
                raw_report_array.append( translate_label( "**Suggested Translation**", "Specifies the suggested translation for this verse." ) + ":\n" )
                raw_report_array.append( "\n".join( f"> {line}" for line in suggested_translation.split('\n') ) )
                raw_report_array.append( "\n\n" )

            reflection_loops = verse.get( 'reflection_loops', [] )
            if reflection_loops:
                if not report_first_iteration:
                    reflection_loop = None
                    if verse.get( 'reflection_is_finalized', False ):
                        #if the verse is finalized, the comments need to be found from the verse which got nominated.
                        for loop in reflection_loops:
                            if loop.get( 'graded_verse', '' ) == translation:
                                reflection_loop = loop
                                break
                    else:
                        last_reflection_loop = reflection_loops[-1]
                        graded_verse = last_reflection_loop.get( 'graded_verse', '' )
                        if graded_verse == '' or graded_verse == translation:
                            reflection_loop = reflection_loops[-1]
                else:
                    #if we want just the first iteration, then just use the first loop
                    reflection_loop = reflection_loops[0]

                #if we were able to find a loop that is the official loop.
                if reflection_loop:
                    for grade_i,grade in enumerate(reflection_loop.get("grades",[])):
                        raw_report_array.append( "**" + translate_label("Review", "Labels text as from a reviewer." ) + f" {grade_i+1}** " )
                        raw_report_array.append( "_(" + translate_label("Grade", "Labels a grade from a reviewer." ) + f" {grade['grade']})_: {grade['comment']}\n\n" )


            raw_report = "".join( raw_report_array )

            if client is not None:

                JUST_SUMMARIZE_THRESHOLD = 3
                COPY_OVER_SUMMARY_THRESHOLD = 5
                GIVE_UP_SUMMARIZATION_THRESHOLD = 10

                failed_count = 0
                passed_checks = False
                while not passed_checks:
                    passed_checks = True
                    if raw_report not in summary_cache:
                        print( "Summarizing..." )
                        if failed_count < JUST_SUMMARIZE_THRESHOLD:
                            summarized_report = summarize_verse_report( client, raw_report, this_config.get( "reports", {} ) )
                        else:
                            summarized_report = summarize_verse_report( client, raw_report, this_config.get( "reports", {} ), just_summarize=True )

                        if failed_count >= COPY_OVER_SUMMARY_THRESHOLD:
                            print( "Copying over summary" )
                            summarized_report = copy_over_summary( raw_report, summarized_report, report_language, translate_label )

                        summary_cache[raw_report] = summarized_report
                        summary_cache_modified = True
                    else:
                        summarized_report = summary_cache[raw_report]

                    if not run_report_checks( summarized_report, source, translation, suggested_translation, report_language, translate_label ):
                        del summary_cache[raw_report]
                        print( f"Failed checks 1 fail count {failed_count+1}" )
                        passed_checks = False
                        time.sleep( 5 )
                        failed_count += 1

                    if failed_count >= GIVE_UP_SUMMARIZATION_THRESHOLD:
                        print( "Skipping summarization" )
                        summarized_report = raw_report
                        passed_checks = True

                failed_count = 0
                passed_checks = False
                while not passed_checks:
                    passed_checks = True
                    if summarized_report not in translation_cache:
                        print( "Translating..." )
                        translated_report = translate_verse_report( client, summarized_report, this_config.get( "reports", {} ) )
                        translation_cache[summarized_report] = translated_report
                        translation_cache_modified = True
                    else:
                        translated_report = translation_cache[summarized_report]

                    if not run_report_checks( translated_report, source, translation, suggested_translation, report_language, translate_label ):
                        del translation_cache[summarized_report]
                        print( f"Failed checks 2 fail count {failed_count+1}" )
                        passed_checks = False
                        time.sleep( 5 )
                        failed_count += 1

                    if failed_count > 10:
                        print( "Skipping translation" )
                        translated_report = summarized_report
                        passed_checks = True

                translated_report = normalize_review_header( translated_report, report_language, translate_label )

            else:
                translated_report = None


            if summary_cache_modified and time.time() - summary_cache_save_time > 60:
                utils.save_json( f"output/summary_cache/{output_file}.json", summary_cache )
                summary_cache_modified = False
                summary_cache_save_time = time.time()
                print( "Saved summary cache" )

            if translation_cache_modified and time.time() - translation_cache_save_time > 60:
                utils.save_json( f"output/translation_cache/{output_file}.json", translation_cache )
                translation_cache_modified = False
                translation_cache_save_time = time.time()
                print( "Saved translation cache" )

            if raw_report:
                if is_first_raw:
                    mode = "w"
                    is_first_raw = False
                else:
                    mode = "a"
                with open( f"output/reports/{output_file}.md", mode, encoding='utf-8' ) as f_raw:
                    f_raw.write( "---\n" )
                    f_raw.write( raw_report.strip() + "\n\n" )


            if translated_report:
                if is_first_summarized:
                    mode = "w"
                    is_first_summarized = False
                else:
                    mode = "a"
                with open( f"output/reports/{output_file}_summarized.md", mode, encoding='utf-8' ) as f_summarized:
                    f_summarized.write( "---\n" )
                    f_summarized.write( translated_report.strip() + "\n\n" )


    if summary_cache_modified:
        utils.save_json( f"output/summary_cache/{output_file}.json", summary_cache )

    if translation_cache_modified:
        utils.save_json( f"output/translation_cache/{output_file}.json", translation_cache )