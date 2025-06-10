"""
Converts the generated bible into different consumable formats.
"""
import os
import re
import time
import json
import math
from collections import defaultdict, OrderedDict
from datetime import datetime
from typing import List
import yaml #pip install pyyaml
from pydantic import BaseModel
from openai import OpenAI
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Spacer, Paragraph, PageBreak, HRFlowable, Flowable # pylint: disable=E0401
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_LEFT,TA_CENTER
from reportlab.lib import colors

from reportlab.lib.colors import Color
from reportlab.platypus import Table, TableStyle
import colorsys

import utils
import grade_reflect_loop


def get_config_for( file ):
    """
    Returns the config for the given file for the output_formats tool.
    """
    with open( 'output_formats.yaml', encoding='utf-8' ) as f:
        output_formats_yaml = yaml.load(f, Loader=yaml.FullLoader)
    if os.path.splitext(file)[0] in output_formats_yaml['configs']:
        return output_formats_yaml['configs'][os.path.splitext(file)[0]]
    return None


def convert_to_ryder_jsonl_format(file):
    """
    Converts the format into a format used by Ryder in his repo
    https://github.com/ryderwishart/swarm
    """

    original_config = None
    with open( 'easy_draft.yaml', encoding='utf-8' ) as f:
        easy_draft_yaml = yaml.load(f, Loader=yaml.FullLoader)
    for config in easy_draft_yaml['configs'].values():
        if config['output'] == os.path.splitext(file)[0]:
            original_config = config

    ebible_dir = easy_draft_yaml['global_configs']['ebible_dir']

    #get modified date of os.path.splitext(file)[0]
    modified_date = datetime.fromtimestamp(os.path.getmtime(f"output/{file}"))

    if original_config:
        source = original_config['source']
        source_content = utils.load_file_to_list( os.path.join( ebible_dir, 'corpus',
            source + '.txt' ) )


        original_content = utils.load_jsonl(f"output/{file}")

        #load output_formats.yaml
        this_config = get_config_for( file )

        #check if the filename sans path and extension is in config.config
        if this_config:
            print( f"converting {file} to ryder format" )

            translation_key = this_config.get( 'translation_key', ['fresh_translation','text'] )
            reference_key = this_config.get( 'reference_key', ['vref'] )
            translation_time_key = this_config.get( 'translation_time_key', ['translation_time'] )


            output_file = this_config.get( 'output_file', os.path.splitext(file)[0] )


            if not os.path.exists("output/ryder_format"):
                os.makedirs("output/ryder_format")
            with open( f"output/ryder_format/{output_file}.jsonl", "w", encoding="utf-8") as f_out:
                for i, in_verse in enumerate(original_content):
                    if in_verse:
                        out_verse = OrderedDict()
                        for key,value in this_config['ryder_format']['outputs'].items():
                            out_verse[key] = value
                        out_verse["original"]      = source_content[i]
                        out_verse["translation"]   = utils.look_up_key( in_verse, translation_key )
                        #round to two digits.
                        out_verse['translation_time'] = \
                            round( utils.look_up_key( in_verse, translation_time_key ), 2)
                        out_verse['model']         = original_config['model']
                        out_verse['calver']        = modified_date.strftime("%Y.%m.%d")
                        out_verse['id']            = utils.look_up_key( in_verse, reference_key )

                        f_out.write(json.dumps(out_verse, ensure_ascii=False) + "\n")

USFM_NAME = {
    "Genesis"       : "01-GEN.usfm",  "GEN" : "01-GEN.usfm",
    "Exodus"        : "02-EXO.usfm",  "EXO" : "02-EXO.usfm",
    "Leviticus"     : "03-LEV.usfm",  "LEV" : "03-LEV.usfm",
    "Numbers"       : "04-NUM.usfm",  "NUM" : "04-NUM.usfm",
    "Deuteronomy"   : "05-DEU.usfm",  "DEU" : "05-DEU.usfm",
    "Joshua"        : "06-JOS.usfm",  "JOS" : "06-JOS.usfm",
    "Judges"        : "07-JDG.usfm",  "JDG" : "07-JDG.usfm",
    "Ruth"          : "08-RUT.usfm",  "RUT" : "08-RUT.usfm",
    "1Samuel"       : "09-1SA.usfm",  "1SA" : "09-1SA.usfm", "1 Samuel"       : "09-1SA.usfm",
    "2Samuel"       : "10-2SA.usfm",  "2SA" : "10-2SA.usfm", "2 Samuel"       : "09-1SA.usfm",
    "1Kings"        : "11-1KI.usfm",  "1KI" : "11-1KI.usfm", "1 Kings"        : "11-1KI.usfm",
    "2Kings"        : "12-2KI.usfm",  "2KI" : "12-2KI.usfm", "2 Kings"        : "12-2KI.usfm",
    "1Chronicles"   : "13-1CH.usfm",  "1CH" : "13-1CH.usfm", "1 Chronicles"   : "13-1CH.usfm",
    "2Chronicles"   : "14-2CH.usfm",  "2CH" : "14-2CH.usfm", "2 Chronicles"   : "14-2CH.usfm",
    "Ezra"          : "15-EZR.usfm",  "EZR" : "15-EZR.usfm",
    "Nehemiah"      : "16-NEH.usfm",  "NEH" : "16-NEH.usfm",
    "Esther"        : "17-EST.usfm",  "EST" : "17-EST.usfm",
    "Job"           : "18-JOB.usfm",  "JOB" : "18-JOB.usfm",
    "Psalms"        : "19-PSA.usfm",  "PSA" : "19-PSA.usfm", "Psalm"        : "19-PSA.usfm",
    "Proverbs"      : "20-PRO.usfm",  "PRO" : "20-PRO.usfm",
    "Ecclesiastes"  : "21-ECC.usfm",  "ECC" : "21-ECC.usfm",
    "SongofSolomon" : "22-SNG.usfm",  "SNG" : "22-SNG.usfm", "Song of Solomon" : "22-SNG.usfm",
    "Isaiah"        : "23-ISA.usfm",  "ISA" : "23-ISA.usfm",
    "Jeremiah"      : "24-JER.usfm",  "JER" : "24-JER.usfm",
    "Lamentations"  : "25-LAM.usfm",  "LAM" : "25-LAM.usfm",
    "Ezekiel"       : "26-EZK.usfm",  "EZK" : "26-EZK.usfm",
    "Daniel"        : "27-DAN.usfm",  "DAN" : "27-DAN.usfm",
    "Hosea"         : "28-HOS.usfm",  "HOS" : "28-HOS.usfm",
    "Joel"          : "29-JOL.usfm",  "JOL" : "29-JOL.usfm",
    "Amos"          : "30-AMO.usfm",  "AMO" : "30-AMO.usfm",
    "Obadiah"       : "31-OBA.usfm",  "OBA" : "31-OBA.usfm",
    "Jonah"         : "32-JON.usfm",  "JON" : "32-JON.usfm",
    "Micah"         : "33-MIC.usfm",  "MIC" : "33-MIC.usfm",
    "Nahum"         : "34-NAM.usfm",  "NAM" : "34-NAM.usfm",
    "Habakkuk"      : "35-HAB.usfm",  "HAB" : "35-HAB.usfm",
    "Zephaniah"     : "36-ZEP.usfm",  "ZEP" : "36-ZEP.usfm",
    "Haggai"        : "37-HAG.usfm",  "HAG" : "37-HAG.usfm",
    "Zechariah"     : "38-ZEC.usfm",  "ZEC" : "38-ZEC.usfm",
    "Malachi"       : "39-MAL.usfm",  "MAL" : "39-MAL.usfm",
    "Matthew"       : "41-MAT.usfm",  "MAT" : "41-MAT.usfm", "Matt" : "41-MAT.usfm",
    "Mark"          : "42-MRK.usfm",  "MRK" : "42-MRK.usfm",
    "Luke"          : "43-LUK.usfm",  "LUK" : "43-LUK.usfm",
    "John"          : "44-JHN.usfm",  "JHN" : "44-JHN.usfm",
    "Acts"          : "45-ACT.usfm",  "ACT" : "45-ACT.usfm",
    "Romans"        : "46-ROM.usfm",  "ROM" : "46-ROM.usfm",
    "1Corinthians"  : "47-1CO.usfm",  "1CO" : "47-1CO.usfm", "1 Corinthians"  : "47-1CO.usfm", "1Cor" : "47-1CO.usfm",
    "2Corinthians"  : "48-2CO.usfm",  "2CO" : "48-2CO.usfm", "2 Corinthians"  : "48-2CO.usfm", "2Cor" : "48-2CO.usfm",
    "Galatians"     : "49-GAL.usfm",  "GAL" : "49-GAL.usfm",
    "Ephesians"     : "50-EPH.usfm",  "EPH" : "50-EPH.usfm",
    "Philippians"   : "51-PHP.usfm",  "PHP" : "51-PHP.usfm", "Phil"          : "51-PHP.usfm",
    "Colossians"    : "52-COL.usfm",  "COL" : "52-COL.usfm",
    "1Thessalonians": "53-1TH.usfm",  "1TH" : "53-1TH.usfm", "1 Thessalonians": "53-1TH.usfm", "1Thess": "53-1TH.usfm",
    "2Thessalonians": "54-2TH.usfm",  "2TH" : "54-2TH.usfm", "2 Thessalonians": "54-2TH.usfm", "2Thess": "54-2TH.usfm",
    "1Timothy"      : "55-1TI.usfm",  "1TI" : "55-1TI.usfm", "1 Timothy"      : "55-1TI.usfm", "1Tim"  : "55-1TI.usfm",
    "2Timothy"      : "56-2TI.usfm",  "2TI" : "56-2TI.usfm", "2 Timothy"      : "56-2TI.usfm", "2Tim"  : "56-2TI.usfm",
    "Titus"         : "57-TIT.usfm",  "TIT" : "57-TIT.usfm",
    "Philemon"      : "58-PHM.usfm",  "PHM" : "58-PHM.usfm", "Phlm"           : "58-PHM.usfm",
    "Hebrews"       : "59-HEB.usfm",  "HEB" : "59-HEB.usfm",
    "James"         : "60-JAS.usfm",  "JAS" : "60-JAS.usfm",
    "1Peter"        : "61-1PE.usfm",  "1PE" : "61-1PE.usfm", "1 Peter"        : "61-1PE.usfm", "1Pet"  : "61-1PE.usfm",
    "2Peter"        : "62-2PE.usfm",  "2PE" : "62-2PE.usfm", "2 Peter"        : "62-2PE.usfm", "2Pet"  : "62-2PE.usfm",
    "1John"         : "63-1JN.usfm",  "1JN" : "63-1JN.usfm", "1 John"         : "63-1JN.usfm", 
    "2John"         : "64-2JN.usfm",  "2JN" : "64-2JN.usfm", "2 John"         : "64-2JN.usfm",
    "3John"         : "65-3JN.usfm",  "3JN" : "65-3JN.usfm", "3 John"         : "65-3JN.usfm",
    "Jude"          : "66-JUD.usfm",  "JUD" : "66-JUD.usfm",
    "Revelation"    : "67-REV.usfm",  "REV" : "67-REV.usfm"
}


def convert_to_usfm(file):
    """Converts the output of easy_draft to USFM format"""

    this_config = get_config_for( file )
    if this_config is None:
        this_config = {}

    #so for USFM we have to have a separate file per book.  So I need to play some games to do
    #this correctly. It would be nice if I could have the correct book number codes.  I think I
    #will just generate them by hand as I need them.
    print( f"converting {file} to usfm format" )
    output_file = this_config.get( 'output_file', os.path.splitext(file)[0] )
    if not os.path.exists(f"output/usfm_format/{output_file}"):
        os.makedirs(f"output/usfm_format/{output_file}")

    translation_key = this_config.get( 'translation_key', ['fresh_translation','text'] )
    reference_key = this_config.get( 'reference_key', ['vref'] )

    original_content = utils.load_jsonl(f"output/{file}")


    #The first thing I need to do is run through the content and sort it out into books.
    book_to_verses = defaultdict( lambda: [] )
    for verse_index,verse in enumerate(original_content):

        if this_config.get( 'start_line', None ) is not None:
            if verse_index < this_config.get( 'start_line', None )-1:
                continue

        if this_config.get( 'end_line', None ) is not None:
            if verse_index > this_config.get( 'end_line', None )-1:
                break

        if verse:
            #reference = verse["fresh_translation"]["reference"]
            reference = utils.look_up_key(verse, reference_key)
            if reference is None:
                continue
            if " " in reference:
                book, _, _ = utils.split_ref(reference)
                usfm_name = USFM_NAME[book]
                book_to_verses[usfm_name].append(verse)

    #now spin through the books and generate the USFM files.
    for usfm_name, verses in book_to_verses.items():
        with open(f"output/usfm_format/{output_file}/{usfm_name}",
                "w", encoding='utf-8') as f:

            current_chapter_num = -1
            for verse in verses:
                reference = utils.look_up_key(verse, reference_key)
                if " " in reference:
                    book, chapter_num, verse_num = utils.split_ref( reference )

                    #if the chapter is different, change the chapter and put in a paragraph.
                    if chapter_num != current_chapter_num:
                        current_chapter_num = chapter_num
                        f.write( f"\\c {chapter_num}\n\\p\n" )

                    #now spit out the verse.
                    f.write( f"\\v {verse_num} {utils.look_up_key(verse, translation_key)}\n" )


def convert_to_markdown(file):
    """
    Converts the format to be readable as MarkDown.
    """
    print( f"converting {file} to markdown format" )


    original_content = utils.load_jsonl(f"output/{file}")

    modified_date = datetime.fromtimestamp(os.path.getmtime(f"output/{file}"))

    this_config = get_config_for( file )

    if this_config:
        translation_key = this_config.get( 'translation_key', ['fresh_translation','text'] )
        translation_comment_key = this_config.get( 'translation_comment_key', ['translation_notes'] )
        reference_key = this_config.get( 'reference_key', ['vref'] )
        override_key = this_config.get( 'override_key',
            ['forming_verse_range_with_previous_verse'] )
        output_file = this_config.get( 'output_file', os.path.splitext(file)[0] )


        #Mark which verse should be dropped because they are overwritten by ranges.
        verse_to_drop = utils.get_overridden_references( original_content, reference_key,
            override_key )

        #run through the content and sort it out into books.
        book_to_chapter_to_verses = defaultdict( lambda: defaultdict( lambda: [] ) )
        for verse_index,verse in enumerate(original_content):
            if 'start_line' in this_config['markdown_format']:
                if verse_index < this_config['markdown_format']['start_line']-1:
                    continue

            if 'start_line' in this_config:
                if verse_index < this_config['start_line']-1:
                    continue

            if 'end_line' in this_config['markdown_format']:
                if verse_index > this_config['markdown_format']['end_line']-1:
                    break

            if 'end_line' in this_config:
                if verse_index > this_config['end_line']-1:
                    break

            if verse:
                #reference = verse["fresh_translation"]["reference"]
                reference = utils.look_up_key(verse, reference_key)
                if " " in reference:
                    if reference not in verse_to_drop:
                        book, chapter_num, _ = utils.split_ref( reference )
                        book_to_chapter_to_verses[book][chapter_num].append(verse)
                    else:
                        print( "Dropping verse", utils.look_up_key(verse, reference_key) )

        output_folder = f"output/markdown_format/{output_file}"
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)

        with open(f"{output_folder}/README.md", "w", encoding='utf-8') as index:
            index.write( f"# {output_file}\n\n" )
            index.write( "| Key | Value |\n")
            index.write( "|:---:|:-----:|\n")
            for key,value in this_config['markdown_format']['outputs'].items():
                index.write( f"|{key}|{value}|\n")

            index.write( f"|translation date|{modified_date.strftime('%Y.%m.%d')}|\n")
            index.write( "\n")

            index.write( "# Books\n" )
            for book in book_to_chapter_to_verses.keys():
                index.write( f"- [{book}]({book}/README.md)\n" )

        for book,chapter_to_verses in book_to_chapter_to_verses.items():
            if not os.path.exists(f"{output_folder}/{book}/README.md"):
                os.makedirs(f"{output_folder}/{book}", exist_ok=True)
            with open(f"{output_folder}/{book}/README.md", "w", encoding='utf-8') as book_index:
                book_index.write( f"# {book}\n\n" )
                book_index.write( "[Book List](../README.md)\n\n" )
                book_index.write( "# Chapters\n" )
                for chapter_num,verses in chapter_to_verses.items():
                    book_index.write( f"- [{book} {chapter_num}](./chapter_{chapter_num}.md)\n" )


                    with open( f"{output_folder}/{book}/chapter_{chapter_num}.md",
                                "w", encoding='utf-8') as chapter_out:
                        chapter_out.write( f"# {book} {chapter_num}\n" )

                        chapter_out.write( "[Book List](../README.md)\n\n" )

                        if int(chapter_num)-1 in chapter_to_verses:
                            chapter_out.write(f"[<-](./chapter_{str(int(chapter_num)-1)}.md) ")
                        for other_chapter_num in chapter_to_verses.keys():
                            if other_chapter_num != chapter_num:
                                chapter_out.write(
                                    f"[{other_chapter_num}](./chapter_{other_chapter_num}.md) ")
                            else:
                                chapter_out.write(f"{other_chapter_num} ")
                        if int(chapter_num)+1 in chapter_to_verses:
                            chapter_out.write(f"[->](./chapter_{str(int(chapter_num)+1)}.md)")

                        chapter_out.write( "\n\n" )


                        chapter_out.write( "| Reference | Verse | Translation Notes |\n")
                        chapter_out.write( "|:---------:|-------|-------------------|\n")

                        for verse in verses:
                            vref = utils.look_up_key(verse, reference_key)
                            translation = utils.look_up_key(verse, translation_key).\
                                    replace('\n', '<br>')
                            comment = utils.look_up_key(verse, translation_comment_key,"",none_is_valid=False).\
                                    replace('\n', '<br>')
                            chapter_out.write(
                                f"|{vref}|{translation}|" +
                                f"{comment}|\n")


                        chapter_out.write( "\n\n")
                        if int(chapter_num)-1 in chapter_to_verses:
                            chapter_out.write(f"[<-](./chapter_{str(int(chapter_num)-1)}.md) ")
                        for other_chapter_num in chapter_to_verses.keys():
                            if other_chapter_num != chapter_num:
                                chapter_out.write(
                                    f"[{other_chapter_num}](./chapter_{other_chapter_num}.md) ")
                            else:
                                chapter_out.write(f"{other_chapter_num} ")
                        if int(chapter_num)+1 in chapter_to_verses:
                            chapter_out.write(f"[->](./chapter_{str(int(chapter_num)+1)}.md)")


def get_sorted_verses( translation_data, reference_key, sort_on_first = False ):
    """Returns the next verse as sorted by grades"""
    fake_config_for_grade_reflect_loop = {
        'reference_key': reference_key,
        'grades_per_reflection_loop': float('inf'),
    }

    def get_grade( verse ):
        if sort_on_first:
            reflection_loops = verse.get('reflection_loops', [])
            if reflection_loops:
                first_loop = reflection_loops[0]
                grades = first_loop.get('grades', [])
                if grades:
                    grade = sum( [grade['grade'] for grade in grades] ) / len(grades)
                    return grade
        else:
            grade = grade_reflect_loop.compute_verse_grade( verse, fake_config_for_grade_reflect_loop )
            if grade is not None:
                return grade
        return float('inf')

    sorted_verses = sorted( translation_data, key=get_grade )

    return sorted_verses, get_grade


def summarize_verse_report( client, raw_report, config, just_summarize=False, no_label=False, output_in_markdown=True, to_language=None ):
    system_message = "You are translation consultant, who is compiling correction for review from " + \
        "a Conservative Christian perspective."

    if not to_language:
        to_language = config.get("report language", "English")

    user_message_array = []

    if not just_summarize:
        user_message_array += [ "The following report was generated for a translated verse of the Bible.\n",
        "Please modify the report so that it is easier to review by the translators who speak ", to_language, ".\n",
        "Provide a reference translation in ", to_language, 
        " for every string which is in another language.  Add it in parrenthesis after the content being translated.\n",
        "Combine the multiple reviewed into a single review in ", to_language, " combining the essence of the individual reviews.\n"
        "Don't add any new content to the report, except for translations and summerizations.  Make sure not to change any of the **Source** or **Translation** text. ",]
    else:
        user_message_array += [ "The following report was generated for a translated verse of the Bible.\n" ]
        if not no_label:
            user_message_array += ["Copy through the Source and Translation sections without modification.\n" ]
        user_message_array += [
            "Combine the multiple reviewed into a single review in ", to_language, " combining the essence of the individual reviews.\n",
            "Don't add any new content to the report, except for the summerization. ",
        ]

    if no_label:
        user_message_array += [ "Don't put a heading on the summarized report.\n" ]

    if output_in_markdown:
        user_message_array += [ "Output in Markdown.\n" ]

    user_message_array += [
        "\n\n**raw report**:\n"
        "```\n", raw_report, "\n```\n"
    ]

    class SummaryResponse(BaseModel):
        updated_report: str

    completion = utils.use_model( client,
        model=config.get('model', "gpt-4o-mini" ),
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": "".join(str(s) for s in user_message_array)}
        ],
        temperature=config.get('temperature', 1.2),
        top_p=config.get('top_p', 0.9),
        response_format=SummaryResponse
    )

    model_dump = completion.choices[0].message.parsed.model_dump()
    result = model_dump['updated_report']

    return result



def translate_verse_report( client, raw_report, config, to_language=None ):

    saw_increase_in_parenthesis = True
    loop_count = 0

    while saw_increase_in_parenthesis:
        print( ".", end='' )


        if to_language is None:
            to_language = config.get("report language", "English")

        system_message = f"You are a translator working in a Conservative Christian context. Your task is to add translations into {to_language} after any text that is not in {to_language}. Only add translations into {to_language}, and do not change anything else. Do not translate into any language other than {to_language}."

        user_message_array = [
            f"Please review the following content. Wherever you find text in a language other than {to_language}, add a translation into {to_language} in parentheses **immediately after the non-{to_language} text**, only if a {to_language} translation is not already present. ",
            f"Make sure to also translate any short quotes in the summary that are not in {to_language}. ",
            f"Only add translations into {to_language}. Do not add or include translations into any other language. ",
            "\n\n**content**:\n```\n",
            raw_report,
            "\n```\n"
        ]

        class TranslationResponse(BaseModel):
            updated_content: str

        completion = utils.use_model( client,
            model=config.get('model', "gpt-4o-mini" ),
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": "".join(str(s) for s in user_message_array)}
            ],
            temperature=config.get('temperature', 1.2),
            top_p=config.get('top_p', 0.9),
            response_format=TranslationResponse
        )

        model_dump = completion.choices[0].message.parsed.model_dump()
        result = model_dump['updated_content']

        old_num_parentheses = raw_report.count('(')
        new_num_parentheses = result.count('(')

        if new_num_parentheses > old_num_parentheses:
            raw_report = result
            saw_increase_in_parenthesis = True
            loop_count += 1
        else:
            saw_increase_in_parenthesis = False

        if loop_count > 7:
            print( f"Stopping adding translations after {loop_count} loops." )
            break
    print()
    return result

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


def convert_to_sorted_report(file):
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

def create_before_and_after_output( file ):
    """Converts the output to a before and after markdown format which
    shows the first history version next to the final history version for
    revivew of what was done"""

    this_config = get_config_for( file )
    if this_config is None:
        this_config = {}

    if not this_config.get( "generate_before_and_after", False ):
        return

    print( f"converting {file} to before and after output" )

    output_file = this_config.get( 'output_file', os.path.splitext(file)[0] )
    if not os.path.exists( "output/before_after" ):
        os.makedirs( "output/before_after")

    translation_key = this_config.get( 'translation_key', ['fresh_translation','text'] )
    reference_key = this_config.get( 'reference_key', ['vref'] )

    content = utils.load_jsonl( f"output/{file}" )

    start_time = time.time()

    with open( f"output/before_after/{output_file}.md", "wt", encoding='utf-8' ) as fout:
        #write table header.
        fout.write( "| Reference | Before | After |\n" )
        fout.write( "| --- | --- | --- |\n" )


        for verse_i, verse_object in enumerate(content):

            if this_config.get( 'start_line', None ) is not None:
                if verse_i < this_config.get( 'start_line', None )-1:
                    continue

            if this_config.get( 'end_line', None ) is not None:
                if verse_i > this_config.get( 'end_line', None )-1:
                    break


            current_time = time.time()
            elapsed_time = current_time - start_time
            #estimated_end_time = len(content)/(verse_i+1) * elapsed_time + current_time

            # Calculate estimated total time needed
            estimated_total_time = len(content)/(verse_i + 1) * elapsed_time
            # Estimated end time is start time + total estimated duration
            estimated_end_time = start_time + estimated_total_time
            print( f"Processing verse {verse_i+1} of {len(content)} - {elapsed_time:.2f} seconds elapsed - estimated {estimated_end_time - current_time:.2f} seconds left, estimated end time {datetime.fromtimestamp(estimated_end_time).strftime('%Y-%m-%d %I:%M:%S %p')}" )

            vref = utils.look_up_key(verse_object, reference_key)
            translation = utils.look_up_key(verse_object, translation_key)
            #now need to see what the oldest verse in the history is.
            translation_0 = utils.look_up_key( verse_object, ['reflection_loops',0,'graded_verse'])

            # book, chapter, verse = utils.split_ref( vref )
            # if book != current_book or chapter != current_chapter:
            #     fout.write( f"# {book} {chapter}\n\n")
            #     current_book = book
            #     current_chapter = chapter

            # fout.write( "===\n")
            # fout.write( f"**{book} {chapter}:{verse}**\n\n" )
            # fout.write( "---\n")
            # fout.write( f"** old: ** {translation_0}\n\n" )
            # fout.write( "---\n")
            # fout.write( f"** new: ** {translation}\n\n" )

            #Let's try this as a table instead.
            fout.write( f"| {vref} | {translation_0} | {translation} |\n" )

def compute_std_devs(values, num_standard_dev):
    """
    Compute the lower and upper bounds of a list of values, given a number of standard deviations from the mean.

    The lower bound is the minimum value, plus the specified number of standard deviations.
    The upper bound is the maximum value, minus the specified number of standard deviations.

    Parameters
    ----------
    values : list
        A list of numeric values.
    num_standard_dev : float
        The number of standard deviations to calculate the bounds from.

    Returns
    -------
    lower_bound : float
        The lower bound.
    upper_bound : float
        The upper bound.

    Raises
    ------
    ValueError
        If the list of values is empty.
    """

    if not values:
        raise ValueError("No values provided")

    # Calculate mean
    n = len(values)
    mean = sum(values) / n

    # Calculate sample standard deviation (ddof=1)
    variance = sum((x - mean) ** 2 for x in values) / (n - 1)
    std_dev = math.sqrt(variance)

    # Calculate the value at num_standard_dev from the minimum
    min_value = min(values)
    max_value = max(values)
    lower_bound = min_value + num_standard_dev * std_dev
    upper_bound = max_value - num_standard_dev * std_dev

    return lower_bound, upper_bound

def get_literal_translation( client, config, text, from_language, to_language ):
    if from_language == to_language: return text

    if not to_language: raise ValueError("to_language is required")
    if not client: raise ValueError("client is required")

    system_message = "You are a translation consultant, drafting literal translations for a Conservative Christian perspective."
    user_message_array = []
    user_message_array += [ "Translate the following text " ]
    if from_language:
        user_message_array += [ "from ", from_language, " " ]
    user_message_array += [ "into ", to_language, "\n" ]

    user_message_array += [ json.dumps({
        "text": text,
    }, ensure_ascii=False) ]

    user_message = "".join(str(x) for x in user_message_array)


    class TranslateResponse(BaseModel):
        literal_translation: str

    completion = utils.use_model( client,
        model=config.get( 'model', 'gpt-4o-mini' ),
        messages=[
            { "role": "system", "content": system_message },
            { "role": "user", "content": user_message }
        ],
        temperature=config.get('temperature', 1.2),
        top_p=config.get('top_p', 0.9),
        response_format=TranslateResponse
    )

    model_dump = completion.choices[0].message.parsed.model_dump()
    literal_translation = model_dump['literal_translation']

    return literal_translation

# --- Font Registration (Improved with better fallback handling) ---
def register_fonts(config_font_name):
    """Register fonts with proper fallback handling"""
    font_paths = [
        (f"/usr/share/fonts/truetype/dejavu/{config_font_name}.ttf", config_font_name),
        (f"/usr/share/fonts/truetype/dejavu/{config_font_name}-Bold.ttf", f"{config_font_name}-Bold"),
        (f"/usr/share/fonts/truetype/dejavu/{config_font_name}-Oblique.ttf", f"{config_font_name}-Italic"),
        # Alternative paths for different systems
        ("/System/Library/Fonts/Helvetica.ttc", "Helvetica"),  # macOS
        ("C:/Windows/Fonts/arial.ttf", "Arial"),  # Windows
    ]

    registered_fonts = {}

    for font_path, font_name in font_paths:
        if os.path.exists(font_path):
            try:
                pdfmetrics.registerFont(TTFont(font_name, font_path))
                registered_fonts[font_name] = True
                print(f"Successfully registered font: {font_name}")
            except Exception as e:
                print(f"Error registering {font_name}: {e}")

    # Register font family if we have the base font
    if "DejaVuSans" in registered_fonts:
        try:
            pdfmetrics.registerFontFamily(
                'DejaVuSans',
                normal='DejaVuSans',
                bold='DejaVuSans-Bold' if 'DejaVuSans-Bold' in registered_fonts else 'DejaVuSans',
                italic='DejaVuSans-Italic' if 'DejaVuSans-Italic' in registered_fonts else 'DejaVuSans',
                boldItalic='DejaVuSans-Bold' if 'DejaVuSans-Bold' in registered_fonts else 'DejaVuSans'
            )
            return 'DejaVuSans', True
        except Exception as e:
            print(f"Error registering font family: {e}")

    print("Using built-in Helvetica font (Greek characters may not render correctly)")
    return 'Helvetica', False

class BookmarkFlowable(Flowable):
    """A flowable that adds a bookmark at its position"""
    def __init__(self, title, key, level=0):
        self.title = title
        self.key = key
        self.level = level
        Flowable.__init__(self)
    
    def draw(self):
        # This gets called when the flowable is drawn
        canvas = self.canv
        canvas.bookmarkPage(self.key)
        canvas.addOutlineEntry(self.title, self.key, self.level)
    
    def wrap(self, availWidth, availHeight):
        # This flowable takes no space
        return (0, 0)



def create_heat_map_table(verses, config, r_get_grade, r_get_ref, r_get_href, cell_text_style):
    """
    Create a heat map table for verses organized by book and chapter.
    
    Args:
        verses: List of verse objects
        config: Configuration dict that may contain 'low_grade', 'high_grade', and 'wrap_number'
    
    Returns:
        Table object for the PDF
    """
    
    # Get wrap number from config
    wrap_number = config.get('wrap_number', 25)
    
    # Get all grades to determine min/max
    all_grades = [r_get_grade(verse) for verse in verses]
    
    # Determine grade range
    if config and 'low_grade' in config and 'high_grade' in config:
        min_grade = config['low_grade']
        max_grade = config['high_grade']
    else:
        min_grade = min(all_grades)
        max_grade = max(all_grades)
    
    # Organize verses by book and chapter
    book_chapter_verses = {}
    for verse in verses:
        ref = r_get_ref(verse)
        book, chapter, verse_start, verse_end = utils.split_ref2(ref)
        
        if book not in book_chapter_verses:
            book_chapter_verses[book] = {}
        if chapter not in book_chapter_verses[book]:
            book_chapter_verses[book][chapter] = []
        
        book_chapter_verses[book][chapter].append(verse)
    
    # Initialize style commands
    style_commands = [
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),  # Right align book/chapter labels
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),  # Center align verse squares
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        # Make squares smaller by reducing cell width and height
        ('COLWIDTH', (1, 0), (-1, -1), 12),  # Reduce column width for verse squares
        ('ROWHEIGHT', (0, 0), (-1, -1), 12),  # Reduce row height for all rows

        ('LEFTPADDING', (1, 0), (-1, -1), 1),   # Minimal left padding for verse cells
        ('RIGHTPADDING', (1, 0), (-1, -1), 1),  # Minimal right padding for verse cells
        ('TOPPADDING', (0, 0), (-1, -1), 1),    # Minimal top padding
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1), # Minimal bottom padding
    ]

    
    # Create table data
    table_data = []
    
    for book in sorted(book_chapter_verses.keys()):
        for chapter in sorted(book_chapter_verses[book].keys()):
            # Sort verses by verse number
            chapter_verses = book_chapter_verses[book][chapter]
            chapter_verses.sort(key=lambda v: utils.split_ref2(r_get_ref(v))[2])  # Sort by verse_start
            
            # Split verses into chunks based on wrap_number
            verse_chunks = []
            for i in range(0, len(chapter_verses), wrap_number):
                verse_chunks.append(chapter_verses[i:i + wrap_number])
            
            # Create a row for each chunk
            for chunk_idx, verse_chunk in enumerate(verse_chunks):
                row_idx = len(table_data)  # Current row index
                
                # For first chunk, use "Book Chapter", for subsequent use empty or continuation indicator
                if chunk_idx == 0:
                    row_label = f"{book} {chapter}"
                else:
                    row_label = f"  ↳"  # Continuation indicator
                
                row = [row_label]
                
                # Create colored squares for each verse and add color styling
                for col_idx, verse in enumerate(verse_chunk, 1):
                    ref = r_get_ref(verse)
                    book_name, chapter_num, verse_start, verse_end = utils.split_ref2(ref)
                    
                    grade = r_get_grade(verse)
                    color = grade_to_color(grade, min_grade, max_grade)
                    
                    # Use verse number as cell content
                    cell_content = Paragraph(f"<link href='#{r_get_href(verse)}' color='#000000'>{str(verse_start)}</link>", cell_text_style)
                    row.append(cell_content)
                    
                    # Add color styling for this cell
                    style_commands.append(
                        ('BACKGROUND', (col_idx, row_idx), (col_idx, row_idx), color)
                    )
                
                table_data.append(row)
    
    # Determine maximum number of verses in any chapter for consistent table width
    max_verses = max(len(row) - 1 for row in table_data) if table_data else 0
    
    # Pad shorter rows with empty cells
    for row in table_data:
        while len(row) <= max_verses:
            row.append("")
    
    # Create table
    if table_data:
        table = Table(table_data)
        
        table.setStyle(TableStyle(style_commands))
        return table
    
    return None

def grade_to_color(grade, min_grade, max_grade):
    """
    Convert a grade to a color between blue (low) and red (high).
    
    Args:
        grade: The grade value
        min_grade: Minimum grade (will be blue)
        max_grade: Maximum grade (will be red)
    
    Returns:
        Color object
    """
    if max_grade == min_grade:
        # All grades are the same, use neutral color
        return Color(0.5, 0.5, 0.5)
    
    # Normalize grade to 0-1 range
    normalized = (grade - min_grade) / (max_grade - min_grade)
    
    # Create color gradient from blue to red
    # Blue: hue=240°, Red: hue=0°
    # We'll interpolate in HSV space for better color transition
    hue = (1 - normalized) * 240 / 360  # 240° to 0° (blue to red)
    saturation = 0.8
    value = 0.9
    
    # Convert HSV to RGB
    r, g, b = colorsys.hsv_to_rgb(hue, saturation, value)
    
    return Color(r, g, b)

# Add this to your existing PDF generation code, after the title page and before the verses:

def add_heat_map_to_story(story, verses, config, r_get_label, r_get_grade, r_get_ref, r_get_href, header_style, body_text_style, cell_text_style):
    """
    Add heat map section to the PDF story.
    
    Args:
        story: The PDF story list to append to
        verses: List of all verses
        config: Configuration dictionary
    """
    # Add heat map title
    story.append(Paragraph(f"{r_get_label('Grade Heat Map')}", header_style))
    story.append(Spacer(1, 0.2*inch))
    
    # Add legend
    story.append(Paragraph(f"{r_get_label('Blue: Low grades, Red: High grades')}", body_text_style))
    story.append(Spacer(1, 0.1*inch))
    
    # Create and add heat map table
    heat_map_table = create_heat_map_table(verses, config, r_get_grade=r_get_grade, r_get_ref=r_get_ref, r_get_href=r_get_href, cell_text_style=cell_text_style)
    if heat_map_table:
        story.append(heat_map_table)
        story.append(Spacer(1, 0.3*inch))
        story.append(PageBreak())

def convert_to_report( file ):
    """
    This export creates a single file markdown export
    of the file with the worse verses at the top,
    and the rest in order further down.
    """
    this_config = get_config_for( file ) or {}

    if not this_config.get( 'reports', {} ).get( 'pdf report enabled', False ):
        print( f"{file} does not have pdf report enabled" )
        return


    config_font_name = this_config.get( 'font_name', 'DejaVuSans' )

    
    original_content = utils.load_jsonl(f"output/{file}")

    #now strip original_content by start_line end_line    
    if "end_line" in this_config:
        end_line = this_config["end_line"]-1
        original_content = original_content[:end_line+1]
    if "start_line" in this_config:
        start_line = this_config["start_line"]-1
        original_content = original_content[start_line:]

    #get the keys
    translation_key = this_config.get( 'translation_key', ['fresh_translation','text'] )
    reference_key = this_config.get( 'reference_key', ['vref'] )
    source_key = this_config.get( 'source_key', ['source'] )

    report_first_iteration = this_config.get('reports',{}).get('report first iteration', False )
    report_language = this_config.get( 'reports', {} ).get( "report language", "English" )
    target_language = this_config.get( 'markdown_format', {} ).get( "outputs", {} ).get( "target language", "English" )


    #now split it into books if the config requests it.
    if this_config.get( 'split_by_book', True ):
        book_to_verses = defaultdict( lambda: [] )
        for verse in original_content:
            vref = utils.look_up_key(verse, reference_key)
            book = utils.split_ref2( vref )[0]
            book_to_verses[book].append( verse )
    else:
        book_to_verses = { "": original_content }

    #now sort stuffs.
    book_to_sorted_verses = { 
        book: get_sorted_verses( verses, reference_key, sort_on_first=report_first_iteration )[0]
        for book, verses in book_to_verses.items()
    }



    #Get the output folder ready.
    base_filename = this_config.get( 'output_file', os.path.splitext(file)[0] )
    output_folder = this_config.get( 'output_folder', f"output/pdf_reports/{base_filename}" )
    os.makedirs( output_folder, exist_ok=True )


    num_sd_to_report = this_config.get( "pdf_reports", {} ).get( 'num_sd_to_report', 2 )
    percentage_sorted = this_config.get( "pdf_reports", {} ).get( 'percentage sorted', None )


    client = None
    if 'api_key' in this_config:
        with open( 'key.yaml', encoding='utf-8' ) as keys_f:
            api_keys = yaml.load(keys_f, Loader=yaml.FullLoader)
            client = OpenAI(api_key=utils.look_up_key( api_keys, this_config['api_key'] ))

    #what we report from the verse object can change based on settings so we break out all the logic
    #for that here with the r_ functions and the reporting below doesn't have to know about it.
    r_get_ref = lambda verse: utils.look_up_key(verse, reference_key)
    r_get_source = lambda verse: utils.look_up_key(verse, source_key)
    r_get_grade = get_sorted_verses( [], reference_key, sort_on_first=report_first_iteration )[1]

    def r_get_href(verse):
        ref = r_get_ref(verse)
        result = ''.join(c if c.isalnum() else '_' for c in ref)
        return result


    def r_get_translation( verse ):
        translation = utils.look_up_key(verse, translation_key)

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

        return translation

    def r_get_grades( verse ):
        translation = r_get_translation( verse )
        reflection_loops = verse.get('reflection_loops', [])

        #iterate through the loops backwards and if we find a matching
        #verse that is what we want, otherwise return the last one and
        #other wise just return an empty list.
        if not reflection_loops: return []
        for loop in reversed( reflection_loops ):
            if loop.get( 'graded_verse', '' ) == translation:
                return loop.get( 'grades', [] )

        return reflection_loops[-1].get( 'grades', [] )

    r_translation_is_report_language = report_language == target_language

    def r_get_label( label ):
        if report_language == "English": return label
        return r_get_label_wrapped( label, report_language )

    @utils.cache_decorator( f"{output_folder}_cache/labels", enabled=client is not None )
    def r_get_label_wrapped( label, to_language ):
        if to_language == "English": return label

        system_message = "You are a translation consultant, creating labels in a target language"
        user_message_array = []
        user_message_array += [ "Translate the following label into " + to_language + " preserving the markdown formating:" ]

        user_message_array += [ "\n", json.dumps( {"label": label}, ensure_ascii=False ) ]
        user_message = "".join(user_message_array)

        if not client: return label

        class LabelResponse(BaseModel):
            translated_label: str

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
            if not translated_label.startswith( "**" ):
                translated_label = "**" + translated_label

        if label.startswith( "### " ):
            if not translated_label.startswith( "### " ):
                translated_label = "### " + translated_label

        if label.endswith( "**" ):
            if not translated_label.endswith( "**" ):
                translated_label = translated_label + "**"

        if label.endswith( "**:" ):
            if not translated_label.endswith( "**:" ):
                translated_label = translated_label + "**:"

        return translated_label

    def r_get_literal_translation( text, from_language=None, to_language=None ):
        if not client: return text

        if to_language is None:
            to_language = this_config.get( 'reports', {} ).get("report language", "English" )

        return r_get_literal_translation_wrapped( text, from_language, to_language )

    @utils.cache_decorator( f"{output_folder}_cache/literal_translation", enabled=client is not None )
    def r_get_literal_translation_wrapped( text, from_language, to_language ):
        return get_literal_translation( client, this_config, text, from_language, to_language )

    @utils.cache_decorator( f"{output_folder}_cache/summerization", enabled=client is not None )
    def r_run_summary( raw_report, to_language ):
        return summarize_verse_report( client, raw_report, this_config.get( "reports", {} ), just_summarize=True, no_label=True, output_in_markdown=False, to_language=to_language )


    @utils.cache_decorator( f"{output_folder}_cache/parenthesis_translation", enabled=client is not None )
    def r_add_parenthesis_translation( text, to_language ):
        return translate_verse_report( client, text, this_config.get( "reports", {} ), to_language=to_language )

    def r_get_review( verse ):
        grades = r_get_grades( verse )

        raw_report_array = []
        for grade_i,grade in enumerate(grades):
            raw_report_array.append( "**" + r_get_label("Review" ) + f" {grade_i+1}** " )
            raw_report_array.append( "_(" + r_get_label("Grade" ) + f" {grade['grade']})_: {grade['comment']}\n\n" )
        raw_report = "".join(raw_report_array)

        summarized_report = r_run_summary( raw_report, to_language=report_language )

        #also add in translations
        translated_report = r_add_parenthesis_translation( summarized_report, to_language=report_language )

        return translated_report

    if "suggested_translation" in this_config.get( "reports", {} ):
        suggested_translation_filename = this_config["reports"]["suggested_translation"]
        if not suggested_translation_filename.endswith( ".jsonl" ):
            suggested_translation_filename += ".jsonl"
        suggested_translation = utils.load_jsonl( os.path.join( "output", suggested_translation_filename ) )
        hashed_suggested_translation = { utils.look_up_key( x, reference_key ): x for x in suggested_translation }
    else:
        hashed_suggested_translation = None
    def r_get_suggested_translation( verse ):
        if hashed_suggested_translation:
            return hashed_suggested_translation.get( r_get_ref(verse) )

        if report_first_iteration:
            last_translation = utils.look_up_key(verse, translation_key)
            if last_translation and last_translation != r_get_translation(verse):
                return last_translation

        return None

    font_name, font_registered = register_fonts(config_font_name)


    styles = getSampleStyleSheet()
    # --- Define Custom Styles ---
    header_style = ParagraphStyle(
        'Header',
        parent=styles['h1'],
        fontName=font_name + '-Bold' if font_registered else font_name,
        fontSize=18,
        spaceAfter=0.2 * inch,
        alignment=TA_CENTER
    )

    sub_header_style = ParagraphStyle(
        'SubHeader',
        parent=styles['h2'],
        fontName=font_name + '-Bold' if font_registered else font_name,
        fontSize=14,  # Smaller than header_style
        spaceAfter=0.2 * inch,
        alignment=TA_CENTER  # Centered alignment
    )


    section_title_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['h2'],
        fontName=font_name + '-Bold' if font_registered else font_name,
        fontSize=14,
        spaceBefore=0.3 * inch,
        spaceAfter=0.1 * inch
    )

    toc_link_style = ParagraphStyle(
        'TOCLink',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=12,
        leading=16,
        leftIndent=0.5 * inch,
        textColor='blue'  # Make links visually distinct
    )

    body_text_style = ParagraphStyle(
        'BodyText',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=11,
        leading=14,
        alignment=TA_LEFT
    )

    # cell_text_style = ParagraphStyle(
    #     'BodyText',
    #     parent=styles['Normal'],
    #     fontName=font_name,
    #     fontSize=8,
    #     leading=14,
    #     alignment=TA_LEFT
    # )
    cell_text_style = ParagraphStyle(
        'TableCell',
        parent=body_text_style,
        fontSize=8,
        leading=8,  # Line height same as font size
        leftIndent=0,
        rightIndent=0,
        spaceAfter=0,
        spaceBefore=0,
        alignment=1,  # Center alignment
    )

    greek_source_style = ParagraphStyle(
        'GreekSourceText',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=10,
        leading=12,
        leftIndent=0.5 * inch,
        rightIndent=0.5 * inch
    )

    #now we will loop through the book names.
    for book, verses in book_to_sorted_verses.items():

        pdf_name = book if book else base_filename

        pdf_prefix = this_config.get( "pdf_reports", {} ).get( "output_prefix", "")
        if pdf_prefix:
            pdf_name = f"{pdf_prefix}{pdf_name}"

        output_filename = f"{output_folder}/{pdf_name}.pdf"
        doc = SimpleDocTemplate(output_filename, pagesize=letter)

        story = []

        # --- Title Page ---
        title = this_config.get( "pdf_reports", {} ).get( "title", f"{base_filename} {book} Report").format( book=book )
        story.append(Paragraph(title, header_style))
        story.append(Spacer(1, 1 * inch))
        story.append(Paragraph(r_get_label(f"Generated on: {datetime.today().strftime('%B %d, %Y')}"), sub_header_style))
        story.append(Spacer(1, 2 * inch))
        story.append(PageBreak())


        # Add heat map
        heat_map_config = this_config.get( "pdf_reports", {} ).get( "heat_map", {} )
        add_heat_map_to_story(story, verses, config=heat_map_config, r_get_label=r_get_label, r_get_grade=r_get_grade, r_get_ref=r_get_ref, r_get_href=r_get_href, header_style=header_style, body_text_style=body_text_style, cell_text_style=cell_text_style)

        #first thing we do is output a configured number of sd verses which are on the low end.
        if percentage_sorted is not None:
            low_end_verses = []
            sorted_verses = sorted( verses, key=r_get_grade )
            for verse in sorted_verses:
                if len(low_end_verses) < percentage_sorted*len(verses)/100:
                    low_end_verses.append(verse)
                else:
                    break

        else:
            grade_cut_off = compute_std_devs( [ r_get_grade(verse) for verse in verses ], num_sd_to_report )[0]
            low_end_verses = [ verse for verse in verses if r_get_grade(verse) <= grade_cut_off ]


        story.append(Paragraph(f"<b>{r_get_label('Lowest sorted by grade')}</b>", header_style))
        story.append(Spacer(1, 0.2*inch))


        #now iterate through these veses.
        for verse in low_end_verses:
            story.append(Paragraph(f"<u><link href='#{r_get_href(verse)}' color='#FF5500'>{r_get_ref(verse)}</link></u>: <font name=\"{config_font_name}\">({r_get_label('Grade')} {r_get_grade(verse):.1f})</font>", section_title_style))
            story.append(Spacer(1, 0.1*inch))

            story.append(Paragraph(f"<b>{r_get_label('Source')}</b>:", body_text_style))
            if r_get_source(verse):
                story.append(Paragraph(r_get_source(verse), greek_source_style))
                story.append(Paragraph(f"({r_get_literal_translation(r_get_source(verse))})", greek_source_style))
            else:
                story.append(Paragraph(f"<i>{r_get_label('No source')}</i>", greek_source_style))
            story.append(Spacer(1, 0.1*inch))

            story.append(Paragraph(f"<b>{r_get_label('Translation')}</b>:", body_text_style))
            story.append(Paragraph(r_get_translation(verse), greek_source_style))
            if not r_translation_is_report_language:
                story.append(Paragraph(f"({r_get_literal_translation(r_get_translation(verse), to_language=target_language)})", greek_source_style))
            story.append(Spacer(1, 0.1*inch))

            if r_get_suggested_translation(verse):
                story.append(Paragraph(f"<b>{r_get_label('Suggested Translation')}</b>:", body_text_style))
                story.append(Paragraph(r_get_suggested_translation(verse), greek_source_style))
                if not r_translation_is_report_language:
                    story.append(Paragraph(f"({r_get_literal_translation(r_get_suggested_translation(verse), to_language=target_language)})", greek_source_style))

            story.append(Paragraph(f"<b>{r_get_label('Review')}</b>:", body_text_style))
            story.append(Paragraph(r_get_review(verse), greek_source_style))
            story.append(Spacer(1, 0.1*inch))

            story.append(HRFlowable(width="100%", thickness=1, lineCap='round', color="black", spaceBefore=12, spaceAfter=12, hAlign='CENTER', vAlign='BOTTOM', dash=None))

        #add a header to indicate we are now going through everything in natural order.
        # Add a header indicating the transition to all verses in natural order
        story.append(Paragraph(f"<b>{r_get_label('All Verses in Natural Order')}</b>", header_style))
        story.append(Spacer(1, 0.2*inch))


        chapter_bookmarks = {}

        start_time = time.time()
        #now iterate through all the verses in natural order.
        for verse_i,verse in enumerate(book_to_verses[book]):

            current_time = time.time()
            elapsed_time = current_time - start_time
            # estimated_end_time = len(book_to_verses[book])/(verse_i+1) * elapsed_time + current_time
            
            # Calculate estimated total time needed
            estimated_total_time = len(book_to_verses[book]) / (verse_i + 1) * elapsed_time
            # Estimated end time is start time + total estimated duration
            estimated_end_time = start_time + estimated_total_time

            print( f"Processing verse {verse_i+1} of {len(book_to_verses[book])} - {elapsed_time:.2f} seconds elapsed - estimated {estimated_end_time - current_time:.2f} seconds left, estimated end time {datetime.fromtimestamp(estimated_end_time).strftime('%Y-%m-%d %I:%M:%S %p')}" )

            
            book_name,chapter_number = utils.split_ref2( r_get_ref( verse ) )[:2]
            book_chapter = f"{book_name} {chapter_number}"
            if book_chapter not in chapter_bookmarks:
                story.append(BookmarkFlowable(title=book_chapter, key=book_chapter, level=0))
                chapter_bookmarks[book_chapter] = True


            story.append(Paragraph(f"<a name='{r_get_href(verse)}'/><b>{r_get_ref(verse)}</b>: <font name=\"{config_font_name}\">({r_get_label('Grade')} {r_get_grade(verse):.1f})</font>", section_title_style))
            story.append(Spacer(1, 0.1*inch))

            story.append(Paragraph(f"<b>{r_get_label('Source')}</b>:", body_text_style))
            if r_get_source(verse):
                story.append(Paragraph(r_get_source(verse), greek_source_style))
                story.append(Paragraph(f"({r_get_literal_translation(r_get_source(verse))})", greek_source_style))
            else:
                story.append(Paragraph(f"<i>{r_get_label('No source')}</i>", greek_source_style))
            story.append(Spacer(1, 0.1*inch))

            story.append(Paragraph(f"<b>{r_get_label('Translation')}</b>:", body_text_style))
            story.append(Paragraph(r_get_translation(verse), greek_source_style))
            if not r_translation_is_report_language:
                story.append(Paragraph(f"({r_get_literal_translation(r_get_translation(verse), to_language=target_language)})", greek_source_style))
            story.append(Spacer(1, 0.1*inch))

            if r_get_suggested_translation(verse):
                story.append(Paragraph(f"<b>{r_get_label('Suggested Translation')}</b>:", body_text_style))
                story.append(Paragraph(r_get_suggested_translation(verse), greek_source_style))
                if not r_translation_is_report_language:
                    story.append(Paragraph(f"({r_get_literal_translation(r_get_suggested_translation(verse), to_language=target_language)})", greek_source_style))

            story.append(Paragraph(f"<b>{r_get_label('Review')}</b>:", body_text_style))
            story.append(Paragraph(r_get_review(verse), greek_source_style))
            story.append(Spacer(1, 0.1*inch))

            story.append(HRFlowable(width="100%", thickness=1, lineCap='round', color="black", spaceBefore=12, spaceAfter=12, hAlign='CENTER', vAlign='BOTTOM', dash=None))

        #now output the story.
        doc.build(story)



def main():
    """
    Main function.
    """
    #Disable warning about Exception being too broad.
    # pylint: disable=W0718

    #run through all the different jsonl files in the output folder and convert them to different
    #formats

    for file in os.listdir("output"):
        if file.endswith(".jsonl"):

            try:
                convert_to_sorted_report(file)
            except Exception as ex:
                print( f"Problem running convert_to_sorted_report for {file}: {ex}")
                time.sleep( 5 )

            try:
                convert_to_ryder_jsonl_format(file)
            except Exception as ex:
                print( f"Problem running convert_to_ryder_jsonl_format for {file}: {ex}")
                time.sleep( 5 )

            try:
                convert_to_usfm(file)
            except Exception as ex:
                print( f"Problem running convert_to_usfm for {file}: {ex}")
                time.sleep( 5 )

            try:
                convert_to_markdown(file)
            except Exception as ex:
                print( f"Problem running convert_to_markdown for {file}: {ex}")
                time.sleep( 5 )

            try:
                create_before_and_after_output(file)
            except Exception as ex:
                print( f"Problem running create_before_and_after_output for {file}: {ex}")
                time.sleep( 5 )

            #try:
            if True:
                convert_to_report(file)
            #except Exception as ex:
            #    print( f"Problem running convert_to_report for {file}: {ex}")
            #    time.sleep( 5 )

if __name__ == "__main__":
    main()

    #convert_to_sorted_report( "open_bible_nueva_Biblia.jsonl" )

    print( "Done!" )
