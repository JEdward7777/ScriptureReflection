"""
Converts the generated bible into different consumable formats.
"""
import os
import json
from collections import defaultdict, OrderedDict
from datetime import datetime
import yaml

import utils

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


            if not os.path.exists("output/ryder_format"):
                os.makedirs("output/ryder_format")
            with open( f"output/ryder_format/{file}", "w", encoding="utf-8") as f_out:
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
    "1Samuel"       : "09-1SA.usfm",  "1SA" : "09-1SA.usfm",
    "2Samuel"       : "10-2SA.usfm",  "2SA" : "10-2SA.usfm",
    "1Kings"        : "11-1KI.usfm",  "1KI" : "11-1KI.usfm",
    "2Kings"        : "12-2KI.usfm",  "2KI" : "12-2KI.usfm",
    "1Chronicles"   : "13-1CH.usfm",  "1CH" : "13-1CH.usfm",
    "2Chronicles"   : "14-2CH.usfm",  "2CH" : "14-2CH.usfm",
    "Ezra"          : "15-EZR.usfm",  "EZR" : "15-EZR.usfm",
    "Nehemiah"      : "16-NEH.usfm",  "NEH" : "16-NEH.usfm",
    "Esther"        : "17-EST.usfm",  "EST" : "17-EST.usfm",
    "Job"           : "18-JOB.usfm",  "JOB" : "18-JOB.usfm",
    "Psalms"        : "19-PSA.usfm",  "PSA" : "19-PSA.usfm",
    "Proverbs"      : "20-PRO.usfm",  "PRO" : "20-PRO.usfm",
    "Ecclesiastes"  : "21-ECC.usfm",  "ECC" : "21-ECC.usfm",
    "SongofSolomon" : "22-SNG.usfm",  "SNG" : "22-SNG.usfm",
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
    "1Corinthians"  : "47-1CO.usfm",  "1CO" : "47-1CO.usfm",
    "2Corinthians"  : "48-2CO.usfm",  "2CO" : "48-2CO.usfm",
    "Galatians"     : "49-GAL.usfm",  "GAL" : "49-GAL.usfm",
    "Ephesians"     : "50-EPH.usfm",  "EPH" : "50-EPH.usfm",
    "Philippians"   : "51-PHP.usfm",  "PHP" : "51-PHP.usfm",
    "Colossians"    : "52-COL.usfm",  "COL" : "52-COL.usfm",
    "1Thessalonians": "53-1TH.usfm",  "1TH" : "53-1TH.usfm",
    "2Thessalonians": "54-2TH.usfm",  "2TH" : "54-2TH.usfm",
    "1Timothy"      : "55-1TI.usfm",  "1TI" : "55-1TI.usfm",
    "2Timothy"      : "56-2TI.usfm",  "2TI" : "56-2TI.usfm",
    "Titus"         : "57-TIT.usfm",  "TIT" : "57-TIT.usfm",
    "Philemon"      : "58-PHM.usfm",  "PHM" : "58-PHM.usfm",
    "Hebrews"       : "59-HEB.usfm",  "HEB" : "59-HEB.usfm",
    "James"         : "60-JAS.usfm",  "JAS" : "60-JAS.usfm",
    "1Peter"        : "61-1PE.usfm",  "1PE" : "61-1PE.usfm",
    "2Peter"        : "62-2PE.usfm",  "2PE" : "62-2PE.usfm",
    "1John"         : "63-1JN.usfm",  "1JN" : "63-1JN.usfm",
    "2John"         : "64-2JN.usfm",  "2JN" : "64-2JN.usfm",
    "3John"         : "65-3JN.usfm",  "3JN" : "65-3JN.usfm",
    "Jude"          : "66-JUD.usfm",  "JUD" : "66-JUD.usfm",
    "Revelation"    : "67-REV.usfm",  "REV" : "67-REV.usfm"
}


class GetStub:
    """
    A stub class that has a get method that returns a default value.
    """
    def get( self, _, default ):
        """Returns the default value"""
        return default

def convert_to_usfm(file):
    """Converts the output of easy_draft to USFM format"""

    this_config = get_config_for( file )
    if this_config is None:
        this_config = GetStub()

    #so for USFM we have to have a separate file per book.  So I need to play some games to do
    #this correctly. It would be nice if I could have the correct book number codes.  I think I
    #will just generate them by hand as I need them.
    print( f"converting {file} to usfm format" )
    if not os.path.exists(f"output/usfm_format/{os.path.splitext(file)[0]}"):
        os.makedirs(f"output/usfm_format/{os.path.splitext(file)[0]}")

    translation_key = this_config.get( 'translation_key', ['fresh_translation','text'] )
    reference_key = this_config.get( 'reference_key', ['vref'] )

    original_content = utils.load_jsonl(f"output/{file}")


    #The first thing I need to do is run through the content and sort it out into books.
    book_to_verses = defaultdict( lambda: [] )
    for verse in original_content:
        if verse:
            #reference = verse["fresh_translation"]["reference"]
            reference = utils.look_up_key(verse, reference_key)
            if " " in reference:
                book, _, _ = utils.split_ref(reference)
                usfm_name = USFM_NAME[book]
                book_to_verses[usfm_name].append(verse)

    #now spin through the books and generate the USFM files.
    for usfm_name, verses in book_to_verses.items():
        with open(f"output/usfm_format/{os.path.splitext(file)[0]}/{usfm_name}",
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
        translation_notes_key = this_config.get( 'translation_notes_key', ['translation_notes'] )
        reference_key = this_config.get( 'reference_key', ['vref'] )
        override_key = this_config.get( 'override_key',
            ['forming_verse_range_with_previous_verse'] )


        #Mark which verse should be dropped because they are overwritten by ranges.
        verse_to_drop = utils.get_overridden_references( original_content, reference_key,
            override_key )

        #run through the content and sort it out into books.
        book_to_chapter_to_verses = defaultdict( lambda: defaultdict( lambda: [] ) )
        for verse in original_content:
            if verse:
                #reference = verse["fresh_translation"]["reference"]
                reference = utils.look_up_key(verse, reference_key)
                if " " in reference:
                    if reference not in verse_to_drop:
                        book, chapter_num, _ = utils.split_ref( reference )
                        book_to_chapter_to_verses[book][chapter_num].append(verse)
                    else:
                        print( "Dropping verse", utils.look_up_key(verse, reference_key) )


        output_folder = f"output/markdown_format/{os.path.splitext(file)[0]}"
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)

        with open(f"{output_folder}/README.md", "w", encoding='utf-8') as index:
            index.write( f"# {os.path.splitext(file)[0]}\n\n" )
            index.write( "| Key | Value |\n")
            index.write( "|:---:|:-----:|\n")
            for key,value in this_config['markdown_format']['outputs'].items():
                index.write( f"|{key}|{value}|\n")

            index.write( f"|translation date|{modified_date.strftime("%Y.%m.%d")}|\n")
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
                            chapter_out.write(
                                f"|{vref}|{utils.look_up_key(verse, translation_key)}|" +
                                f"{utils.look_up_key(verse, translation_notes_key)}|\n")


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



def main():
    """
    Main function.
    """
    #run through all the different jsonl files in the output folder and convert them to different
    #formats

    for file in os.listdir("output"):
        if file.endswith(".jsonl"):
            convert_to_ryder_jsonl_format(file)
            convert_to_usfm(file)
            convert_to_markdown(file)

if __name__ == "__main__":
    main()

    print( "Done!" )
