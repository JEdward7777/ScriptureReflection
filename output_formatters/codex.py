
from collections import defaultdict
import os, json
import utils
from format_utilities import get_config_for
from datetime import datetime, timezone

from . import usfm

def get_ot_nt_designator( book ):
    book_names = list( usfm.USFM_NAME.keys() )

    if book not in book_names:
        book = book.upper()
        if book not in book_names:
            return ""
    mat_index = book_names.index( "Matthew" )
    book_index = book_names.index( book )
    if book_index < mat_index:
        return "OT"
    else:
        return "NT"


def run(file):

    print( f"Exporting {file} to codex format" )

    original_content = utils.load_jsonl(f"output/{file}")

    this_config = get_config_for( file )


    translation_key = this_config.get( 'translation_key', ['fresh_translation','text'] )
    source_key = this_config.get( 'source_key', ['source'] )
    #translation_comment_key = this_config.get( 'translation_comment_key', ['translation_notes'] )
    reference_key = this_config.get( 'reference_key', ['vref'] )
    override_key = this_config.get( 'override_key',
        ['forming_verse_range_with_previous_verse'] )

    #Mark which verse should be dropped because they are overwritten by ranges.
    verse_to_drop = utils.get_overridden_references( original_content, reference_key,
        override_key )

    #The first thing I need to do is run through the content and sort it out into books.
    book_to_verses = defaultdict( lambda: [] )
    for verse_index,verse in enumerate(original_content):
        if this_config.get( 'start_line', None ) is not None:
            if verse_index < this_config.get( 'start_line', None )-1:
                continue
        if this_config.get( 'end_line', None ) is not None:
            if verse_index > this_config.get( 'end_line', None )-1:
                continue

        reference = utils.look_up_key(verse, reference_key)
        if reference in verse_to_drop:
            continue

        book = utils.split_ref2( reference )[0]
        book_to_verses[book].append(verse)


    #see if there is only one item per book, we will make everything just one file.
    num_more_than_ones = sum(1 for book in book_to_verses if len(book_to_verses[book]) > 1)
    if num_more_than_ones == 0:
        #go ahead and stuff everything in as one "book".
        new_book_to_verses = {'content': [verse for book in book_to_verses for verse in book_to_verses[book]]}
        book_to_verses = new_book_to_verses

    
    project_folder = this_config.get( 'codex', {} )['folder']

    source_and_target = [
        {
            'folder': os.path.join( project_folder, '.project/sourceTexts' ),
            'extension': "source",
            'content_key': source_key,
        },{
            'folder': os.path.join( project_folder, 'files/target' ),
            'extension': "codex",
            'content_key': translation_key,
        }
    ]

    timestamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

    for side in source_and_target:
        os.makedirs( side['folder'], exist_ok=True )
        for book in book_to_verses:
            codex_structure = {}
            codex_cells = codex_structure.setdefault( 'cells', [] )
            for verse in book_to_verses[book]:

                vref = utils.look_up_key(verse, reference_key)
                content = utils.look_up_key(verse, side['content_key'], default="")

                _,chapter_num,verse_start,verse_end = utils.split_ref2( vref )
                in_range = verse_start != verse_end
                codex_cell = {}
                codex_cells.append( codex_cell )
                codex_cell['kind'] = 2
                codex_cell['languageId'] = 'html'
                codex_cell['value'] = content
                metadata = codex_cell.setdefault( 'metadata', {} )
                metadata['type'] = 'text'
                if in_range:
                    metadata['id'] = f"{book} {chapter_num}:{verse_start}"
                else:
                    metadata['id'] = vref
                metadata['data'] = {}
                metadata['cellLabel'] = str(verse_start)

                if in_range:
                    for verse_num in range( verse_start+1, verse_end+1 ):
                        codex_cell = {}
                        codex_cells.append( codex_cell )
                        codex_cell['kind'] = 2
                        codex_cell['languageId'] = 'html'
                        codex_cell['value'] = '<range>' if content else ''
                        metadata = codex_cell.setdefault( 'metadata', {} )
                        metadata['type'] = 'text'
                        metadata['id'] = f"{book} {chapter_num}:{verse_num}"
                        metadata['data'] = {}
                        metadata['cellLabel'] = str(verse_num)

            book_metadata = codex_structure.setdefault( 'metadata', {} )
            book_metadata['id'] = book
            book_metadata['originalName'] = book
            book_metadata['sourceFsPath'] = os.path.join( side['folder'], f".project/sourceTexts/{book}.source" )
            if side['extension'] == 'codex':
                book_metadata['codexFsPath'] = os.path.join( side['folder'], f"files/target/{book}.codex" )
            book_metadata['navigation'] = []
            #2025-06-19T21:29:54.808Z
            book_metadata['sourceCreatedAt'] = timestamp
            book_metadata['codexLastModified'] = timestamp
            book_metadata['gitStatus'] = 'untracked'
            book_metadata['corpusMarker'] = get_ot_nt_designator( book )
            
            output_filename = os.path.join( side['folder'], f"{book}.{side['extension']}" )
            with open( output_filename, 'w', encoding='utf-8' ) as f:
                json.dump( codex_structure, f, ensure_ascii=False, indent=4 )
                