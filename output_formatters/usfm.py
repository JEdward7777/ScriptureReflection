import os
import utils
from collections import defaultdict
from format_utilities import get_config_for

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

def run(file):
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

