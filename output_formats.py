"""
Converts the generated bible into different consumable formats.
"""
import os
import re
import time
import json
from collections import defaultdict, OrderedDict
from datetime import datetime
import yaml #pip install pyyaml
from pydantic import BaseModel
from openai import OpenAI

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
    "Matthew"       : "41-MAT.usfm",  "MAT" : "41-MAT.usfm",
    "Mark"          : "42-MRK.usfm",  "MRK" : "42-MRK.usfm",
    "Luke"          : "43-LUK.usfm",  "LUK" : "43-LUK.usfm",
    "John"          : "44-JHN.usfm",  "JHN" : "44-JHN.usfm",
    "Acts"          : "45-ACT.usfm",  "ACT" : "45-ACT.usfm",
    "Romans"        : "46-ROM.usfm",  "ROM" : "46-ROM.usfm",
    "1Corinthians"  : "47-1CO.usfm",  "1CO" : "47-1CO.usfm", "1 Corinthians"  : "47-1CO.usfm",
    "2Corinthians"  : "48-2CO.usfm",  "2CO" : "48-2CO.usfm", "2 Corinthians"  : "48-2CO.usfm",
    "Galatians"     : "49-GAL.usfm",  "GAL" : "49-GAL.usfm",
    "Ephesians"     : "50-EPH.usfm",  "EPH" : "50-EPH.usfm",
    "Philippians"   : "51-PHP.usfm",  "PHP" : "51-PHP.usfm",
    "Colossians"    : "52-COL.usfm",  "COL" : "52-COL.usfm",
    "1Thessalonians": "53-1TH.usfm",  "1TH" : "53-1TH.usfm", "1 Thessalonians": "53-1TH.usfm",
    "2Thessalonians": "54-2TH.usfm",  "2TH" : "54-2TH.usfm", "2 Thessalonians": "54-2TH.usfm",
    "1Timothy"      : "55-1TI.usfm",  "1TI" : "55-1TI.usfm", "1 Timothy"      : "55-1TI.usfm",
    "2Timothy"      : "56-2TI.usfm",  "2TI" : "56-2TI.usfm", "2 Timothy"      : "56-2TI.usfm",
    "Titus"         : "57-TIT.usfm",  "TIT" : "57-TIT.usfm",
    "Philemon"      : "58-PHM.usfm",  "PHM" : "58-PHM.usfm",
    "Hebrews"       : "59-HEB.usfm",  "HEB" : "59-HEB.usfm",
    "James"         : "60-JAS.usfm",  "JAS" : "60-JAS.usfm",
    "1Peter"        : "61-1PE.usfm",  "1PE" : "61-1PE.usfm", "1 Peter"        : "61-1PE.usfm",
    "2Peter"        : "62-2PE.usfm",  "2PE" : "62-2PE.usfm", "2 Peter"        : "62-2PE.usfm",
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


def get_sorted_verses( translation_data, reference_key ):
    """Returns the next verse as sorted by grades"""
    fake_config_for_grade_reflect_loop = {
        'reference_key': reference_key,
        'grades_per_reflection_loop': float('inf'),
    }

    def get_grade( verse ):
        grade = grade_reflect_loop.compute_verse_grade( verse, fake_config_for_grade_reflect_loop )
        if grade is not None:
            return grade
        return float('inf')

    sorted_verses = sorted( translation_data, key=get_grade )

    return sorted_verses, get_grade


def summarize_verse_report( client, raw_report, config, just_summarize=False ):
    system_message = "You are translation consultant, who is compiling correction for review from " + \
        "a Conservative Christian perspective."

    target_language = config.get("language", "English")

    if not just_summarize:
        user_message_array = [ "The following report was generated for a translated verse of the Bible.\n",
        "Please modify the report so that it is easier to review by the translators.\n",
        "Provide a reference translation in ", target_language, 
        " for every string which is in another language.  Add it in parrenthesis after the content being translated.\n",
        "Combine the multiple reviewed into a single review in ", target_language, " combining the essence of the individual reviews.\n"
        "Don't add any new content to the report, except for translations and summerizations.  Make sure not to any of the **Source** or **Translation** text. Output in Markdown.",]
    else:
        user_message_array = [ "The following report was generated for a translated verse of the Bible.\n",
        "Copy through the Source and Translation sections without modification.\n",
        "Combine the multiple reviewed into a single review in ", target_language, " combining the essence of the individual reviews.\n"
        "Don't add any new content to the report, except for translations and summerizations. Output in Markdown.",]

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



def translate_verse_report( client, raw_report, config ):

    saw_increase_in_parenthesis = True
    loop_count = 0

    while saw_increase_in_parenthesis:
        print( ".", end='' )

        system_message = "You are a translator adding translations to reviews in a Conservative Christian context."

        target_language = config.get("language", "English")

        user_message_array = [ "Please review the following content and everywhere there is text ",
            f"in a language other than {target_language}, add in a translation after it in parenthesis in ",
            f"{target_language} if it is missing. Make sure the short quotes in the summary are translated in parenthesis as well." ]

        user_message_array += [
            "\n\n**content**:\n"
            "```\n", raw_report, "\n```\n"
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

def run_report_checks( report, source, translation, suggested_translation ):
    #So the report has to have the source and the translation still in it.
    #It also needs to have a review in it.

    chars_to_ignore = [ ';', '.', ',', '―','¿', '?', '»', '«', '“', '¡', '!', ')', '(', '”', '·', '—', '1','2','3','4','5','6','7','8','9','0']

    for char in chars_to_ignore:
        source = source.replace(char, '')
        translation = translation.replace(char, '')
        if suggested_translation:
            suggested_translation = suggested_translation.replace(char, '')
        report = report.replace(char, '')
    
    if source not in report:
        #see if each word of the source is in the report because ChatGPT might have
        #put the translations inline.
        for word in source.split():
            if word not in report:
                print( f"Missed source word: {word}" )
                return False

    if translation not in report:
        #see if each word of the translation is in the report because ChatGPT might have
        #put the translations inline.
        for word in translation.split():
            if word not in report:
                print( f"Missed translation word: {word}" )
                return False

    if suggested_translation:
        if suggested_translation not in report:
            for word in suggested_translation.split():
                if word not in report:
                    print( f"Missed suggested translation word: {word}" )
                    return False

    if 'review' not in report.lower():
        print( "Missed review" )
        return False

    return True

def normalize_review_header( report ):
    #we want to go with "**Combined Review**:\n" and all other versions should be replaced with it.

    if "**Combined Review**:" in report.split('\n'):
        return report

    #here we only have things to fix.
    swaps = [
        "**Review Summary**:", 
        "**Combined Review Summary**:",
        "**Overall Review Summary**:",
        "**Overall Review**:",
        "### Combined Review",
    ]
    reg_swaps = ["\\*\\*Combined Review\\*\\*:?(?!\n)", "\\*\\*Combined Review\\*\\*:?[ \n:]*(_\\((Overall|Average)? ?Grade [^)]*\\)_[ \n:]*)?"]

    for swap in swaps:
        report = report.replace(swap, "**Combined Review**:\n")
        
    for reg_swap in reg_swaps:
        report = re.sub(reg_swap, "**Combined Review**:\n", report)

    if "**Combined Review**:" in report.split('\n'):
        return report

    return report

def copy_over_summary( raw_report, summarized_report ):
    """
    We are having trouble having the source and translation getting modified by ChatGPT,
    so here we try to just snip off the summarized oprtion of the report and use
    it on the raw report.
    """
    summarized_report = normalize_review_header( summarized_report )

    spliced_report = []

    for line in raw_report.split('\n'):
        if not line.startswith( "**Review 1**"):
            spliced_report.append( line )
        else:
            break

    found_review_line = False
    for line in summarized_report.split('\n'):
        if line.startswith( "**Combined Review**" ):
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

    original_content = utils.load_jsonl(f"output/{file}")

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
    sorted_content, get_grade = get_sorted_verses( original_content, reference_key )

    sorted_content = [x for x in sorted_content if get_grade(x) != float('inf')]

    client = None
    if 'api_key' in this_config:
        with open( 'key.yaml', encoding='utf-8' ) as keys_f:
            api_keys = yaml.load(keys_f, Loader=yaml.FullLoader)
            client = OpenAI(api_key=utils.look_up_key( api_keys, this_config['api_key'] ))
        

    if sorted_content:

        is_first_raw = True
        is_first_summarized = True

        start_time = time.time()

        #first output a header for the report
        for verse_i, verse in enumerate(sorted_content):

            current_time = time.time()
            elapsed_time = current_time - start_time
            estimated_end_time = len(sorted_content)/(verse_i+1) * elapsed_time + current_time
            print( f"Processing verse {verse_i+1} of {len(sorted_content)} - {elapsed_time:.2f} seconds elapsed - estimated {estimated_end_time - current_time:.2f} seconds left, estimated end time {datetime.fromtimestamp(estimated_end_time).strftime('%Y-%m-%d %I:%M:%S %p')}" )
            
            vref = utils.look_up_key(verse, reference_key)
            translation = utils.look_up_key(verse, translation_key)
            source = utils.look_up_key(verse, source_key)
            grade = get_grade(verse)

            raw_report_array = [
                f"**{vref}**: _(Grade {grade:.1f})_\n\n",
                "**Source**:\n",
                "\n".join( f"> {line}" for line in source.split('\n') ),
                "\n\n",
                "**Translation**:\n",
                "\n".join( f"> {line}" for line in translation.split('\n') ),
                "\n\n", ]

            if hashed_suggested_translation:
                suggested_verse = hashed_suggested_translation.get( vref, None )
                suggested_translation = utils.look_up_key( suggested_verse, translation_key )
                if suggested_translation and suggested_translation != translation:
                    raw_report_array.append( "**Suggested Translation**:\n" )
                    raw_report_array.append( "\n".join( f"> {line}" for line in suggested_translation.split('\n') ) )
                    raw_report_array.append( "\n\n" )
                else:
                    suggested_translation = None
            else:
                suggested_translation = None

            reflection_loops = verse.get( 'reflection_loops', [] )
            if reflection_loops:
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

                #if we were able to find a loop that is the official loop.
                if reflection_loop:
                    for grade_i,grade in enumerate(reflection_loop.get("grades",[])):
                        raw_report_array.append( f"**Review {grade_i+1}** "
                            f"_(Grade {grade['grade']})_: {grade['comment']}\n\n" )


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
                            summarized_report = copy_over_summary( raw_report, summarized_report )

                        summary_cache[raw_report] = summarized_report
                        summary_cache_modified = True
                    else:
                        summarized_report = summary_cache[raw_report]

                    if not run_report_checks( summarized_report, source, translation, suggested_translation ):
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

                    if not run_report_checks( summarized_report, source, translation, suggested_translation ):
                        del translation_cache[summarized_report]
                        print( f"Failed checks 2 fail count {failed_count+1}" )
                        passed_checks = False
                        time.sleep( 5 )
                        failed_count += 1

                    if failed_count > 10:
                        print( "Skipping translation" )
                        translated_report = summarized_report
                        passed_checks = True

                translated_report = normalize_review_header( translated_report )
                
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

if __name__ == "__main__":
    #main()

    convert_to_sorted_report( "open_bible_nueva_Biblia.jsonl" )

    print( "Done!" )
