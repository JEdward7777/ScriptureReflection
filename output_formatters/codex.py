
from collections import defaultdict
import hashlib
import os, json
import utils
from format_utilities import get_config_for
from datetime import datetime, timezone

from . import usfm


def generate_cell_id_from_hash(original_id: str) -> str:
    """
    Generates a deterministic UUID from a cell ID using SHA-256 hashing.
    This ensures the same cell ID always produces the same UUID, preventing merge conflicts.

    Format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

    Args:
        original_id: The original cell ID (e.g., "GEN 1:1")

    Returns:
        A UUID-formatted string (e.g., "590e4641-0a20-4655-a7fd-c1eb116e757c")

    Raises:
        ValueError: If original_id is empty or None
    """
    if not original_id or not original_id.strip():
        raise ValueError("Original cell ID cannot be empty")

    # Compute SHA-256 hash
    hash_bytes = hashlib.sha256(original_id.encode('utf-8')).digest()

    # Convert to hex string
    hash_hex = hash_bytes.hex()

    # Take first 32 hex characters (128 bits) and format as UUID
    # Format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
    uuid = '-'.join([
        hash_hex[0:8],    # 8 hex chars
        hash_hex[8:12],   # 4 hex chars
        hash_hex[12:16],  # 4 hex chars
        hash_hex[16:20],  # 4 hex chars
        hash_hex[20:32],  # 12 hex chars
    ])

    return uuid


def _build_book_abbreviation_map():
    """
    Build a mapping from any book name variant to its standard 3-letter USFM code.
    Uses the USFM_NAME dict which maps name variants to filenames like "01-GEN.usfm".
    The 3-letter code is extracted from the filename.
    """
    # First, build reverse hash: filename -> 3-letter code (only from 3-letter keys)
    ref_reverse_hash = {}
    for key, value in usfm.USFM_NAME.items():
        if len(key) == 3:
            ref_reverse_hash[value] = key

    # Then, build normalization hash: any key -> 3-letter code
    normalization_hash = {}
    for key, value in usfm.USFM_NAME.items():
        if value in ref_reverse_hash:
            normalization_hash[key] = ref_reverse_hash[value]

    return normalization_hash


# Build the abbreviation map once at module load time
_BOOK_ABBREVIATION_MAP = _build_book_abbreviation_map()


def abbreviate_book_name(book_name, strict=True):
    """
    Convert a book name to its standard 3-letter USFM abbreviation.

    Args:
        book_name: The book name to abbreviate (e.g., "Genesis", "1 Chronicles", "GEN")
        strict: If True (default), raises KeyError when the book name is not found.
                If False, returns the original name unchanged (graceful fallback
                for non-Bible content).

    Returns:
        The 3-letter USFM abbreviation (e.g., "GEN", "1CH")

    Raises:
        KeyError: If strict=True and book_name is not found in the USFM mapping
    """
    if book_name in _BOOK_ABBREVIATION_MAP:
        return _BOOK_ABBREVIATION_MAP[book_name]
    if strict:
        raise KeyError(
            f"Book name '{book_name}' not found in USFM abbreviation mapping. "
            f"Use strict=False for non-Bible content."
        )
    return book_name

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

    # If strict_book_names is True (default), abbreviate_book_name will raise
    # an error for unrecognized book names.  Set to False in config for non-Bible content.
    strict_book_names = this_config.get( 'codex', {} ).get( 'strict_book_names', True )

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
        content_name = this_config.get( 'codex', {} ).get( 'content_name', 'content' )
        #go ahead and stuff everything in as one "book".
        new_book_to_verses = {content_name: [verse for book in book_to_verses for verse in book_to_verses[book]]}
        book_to_verses = new_book_to_verses


    #now going to scrub through and make sure all the IDs are "<book> <chapter>:<verse>" parsable.
    #doing this as a pre-step to make sure the IDs assigned are consistent betwean the source and target
    mapped_ids = {}
    for book in book_to_verses:
        last_chapter_number = 1
        last_verse_number = 0

        for verse in book_to_verses[book]:
            vref = utils.look_up_key(verse, reference_key)
            _,chapter_number,verse_start,verse_end = utils.split_ref2( vref )

            used_chapter_num = chapter_number if chapter_number is not None else last_chapter_number
            used_verse_start = verse_start if verse_start is not None else last_verse_number + 1
            used_verse_end = verse_end if verse_end is not None else used_verse_start

            if used_verse_start != used_verse_end:
                reconstructed_vref = f"{book} {used_chapter_num}:{used_verse_start}-{used_verse_end}"
            else:
                reconstructed_vref = f"{book} {used_chapter_num}:{used_verse_start}"

            mapped_ids[vref] = reconstructed_vref

            last_chapter_number = used_chapter_num
            last_verse_number = used_verse_end


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
                reconstructed_vref = mapped_ids[vref]

                content = utils.look_up_key(verse, side['content_key'], default="")

                _,chapter_num,verse_start,verse_end = utils.split_ref2( reconstructed_vref )

                abbreviated_book = abbreviate_book_name( book, strict=strict_book_names )
                global_ref = f"{abbreviated_book} {chapter_num}:{verse_start}"

                codex_cell = {}
                codex_cells.append( codex_cell )
                codex_cell['kind'] = 2
                codex_cell['languageId'] = 'html'
                codex_cell['value'] = content
                metadata = codex_cell.setdefault( 'metadata', {} )
                metadata['type'] = 'text'

                metadata['id'] = generate_cell_id_from_hash( global_ref )
                metadata['data'] = {
                    'globalReferences': [ global_ref ]
                }
                metadata['cellLabel'] = str(verse_start)

                in_range = verse_start != verse_end

                if not in_range:
                    if reconstructed_vref != vref:
                        metadata['originalId'] = vref

                if in_range:
                    for verse_num in range( verse_start+1, verse_end+1 ):
                        range_global_ref = f"{abbreviated_book} {chapter_num}:{verse_num}"
                        codex_cell = {}
                        codex_cells.append( codex_cell )
                        codex_cell['kind'] = 2
                        codex_cell['languageId'] = 'html'
                        codex_cell['value'] = '<range>' if content else ''
                        metadata = codex_cell.setdefault( 'metadata', {} )
                        metadata['type'] = 'text'
                        metadata['id'] = generate_cell_id_from_hash( range_global_ref )
                        metadata['data'] = {
                            'globalReferences': [ range_global_ref ]
                        }
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
