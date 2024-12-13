import os
import json
import easy_draft
from collections import defaultdict, OrderedDict
import yaml
from datetime import datetime



def convert_to_ryder_jsonl_format(file):

    original_config = None
    with open( 'easy_draft.yaml', encoding='utf-8' ) as f:
        easy_draft_yaml = yaml.load(f, Loader=yaml.FullLoader)
    for config in easy_draft_yaml['configs'].values():
        if config['output'] == os.path.splitext(file)[0]:
            original_config = config

    ebible_dir = easy_draft_yaml['global_configs']['ebible_dir']
    source = original_config['source']
    source_content = easy_draft.load_file_to_list( os.path.join( ebible_dir, 'corpus', source + '.txt' ) )

    #get modified date of os.path.splitext(file)[0]
    modified_date = datetime.fromtimestamp(os.path.getmtime(f"output/{file}"))

    if original_config:


        original_content = list(map(json.loads, easy_draft.load_file_to_list(f"output/{file}")))

        #load output_formats.yaml
        with open( 'output_formats.yaml', encoding='utf-8' ) as f:
            output_formats_yaml = yaml.load(f, Loader=yaml.FullLoader)

        #check if the filename sans path and extension is in config.config
        if os.path.splitext(file)[0] in output_formats_yaml['configs']:
            print( f"converting {file} to ryder format" )
            this_config = output_formats_yaml['configs'][os.path.splitext(file)[0]]

            if not os.path.exists("output/ryder_format"):
                os.makedirs("output/ryder_format")
            with open( f"output/ryder_format/{file}", "w", encoding="utf-8") as f_out:
                for i, in_verse in enumerate(original_content):
                    if in_verse:
                        out_verse = OrderedDict()
                        for key,value in this_config['ryder_format']['outputs'].items():
                            out_verse[key] = value
                        out_verse["original"]         = source_content[i]
                        out_verse["translation"]      = in_verse['fresh_translation']['text']
                        #round to two digits.
                        out_verse['translation_time'] = round(in_verse['translation_time'], 2)
                        out_verse['model']            = original_config['model']
                        out_verse['calver']           = modified_date.strftime("%Y.%m.%d")
                        out_verse['id']               = in_verse['fresh_translation']['reference']

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
def convert_to_usfm(file):
    #so for USFM we have to have a separate file per book.  So I need to play some games to do this correctly.
    #it would be nice if I could have the correct book number codes.  I think I will just generate them by hand as I need them.
    print( f"converting {file} to usfm format" )
    if not os.path.exists(f"output/usfm_format/{os.path.splitext(file)[0]}"):
        os.makedirs(f"output/usfm_format/{os.path.splitext(file)[0]}")


    original_content = list(map(json.loads, easy_draft.load_file_to_list(f"output/{file}")))

    with open( 'easy_draft.yaml', encoding='utf-8' ) as f:
        easy_draft_yaml = yaml.load(f, Loader=yaml.FullLoader)
    ebible_dir = easy_draft_yaml['global_configs']['ebible_dir']
    vrefs = easy_draft.load_file_to_list( os.path.join( ebible_dir, 'metadata', 'vref.txt' ) )

    #The first thing I need to do is run through the content and sort it out into books.
    book_to_verses = defaultdict( lambda: [] )
    for i,verse in enumerate(original_content):
        if verse:
            #reference = verse["fresh_translation"]["reference"]
            reference = vrefs[i]
            if " " in reference:
                #Index of last space.
                last_space_index = reference.rindex(" ")
                book = reference[:last_space_index]
                usfm_name = USFM_NAME[book]
                book_to_verses[usfm_name].append(verse)

    #now spin through the books and generate the USFM files.
    for usfm_name, verses in book_to_verses.items():
        with open(f"output/usfm_format/{os.path.splitext(file)[0]}/{usfm_name}", "w", encoding='utf-8') as f:

            current_chapter_num = -1
            for verse in verses:
                reference = verse["fresh_translation"]["reference"]
                if " " in reference:
                    #Index of last space.
                    last_space_index = reference.rindex(" ")
                    book = reference[:last_space_index]
                    chapter_verse = reference[last_space_index+1:]
                    chapter_num,verse_num = chapter_verse.split( ":" )

                    #if the chapter is different, change the chapter and put in a paragraph.
                    if chapter_num != current_chapter_num:
                        current_chapter_num = chapter_num
                        f.write( f"\\c {chapter_num}\n\\p\n" )

                    #now spit out the verse.
                    f.write( f"\\v {verse_num} {verse['fresh_translation']['text']}\n" )




def main():
    #run through all the different jsonl files in the output folder and convert them to different formats

    for file in os.listdir("output"):
        if file.endswith(".jsonl"):
            #convert_to_ryder_jsonl_format(file)
            convert_to_usfm(file)

    print( "Done!" )

if __name__ == "__main__":
    main()