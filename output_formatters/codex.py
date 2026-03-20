
from collections import defaultdict
import hashlib
import os
import json
import re
import time
from datetime import datetime, timezone
import utils
from format_utilities import get_config_for

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

def _parse_ref_for_sort(ref_str):
    """
    Parse a reference string like "GEN 1:1" into a sortable tuple (book, chapter, verse).
    Returns (ref_str, 0, 0) if parsing fails.
    """
    if not ref_str or ' ' not in ref_str:
        return (ref_str or '', 0, 0)
    last_space = ref_str.rindex(' ')
    book = ref_str[:last_space]
    rest = ref_str[last_space+1:]
    if ':' not in rest:
        try:
            return (book, int(rest), 0)
        except ValueError:
            return (book, 0, 0)
    parts = rest.split(':')
    try:
        chapter = int(parts[0])
        verse_str = parts[1].split('-')[0]  # Take start of range
        verse = int(verse_str)
        return (book, chapter, verse)
    except ValueError:
        return (book, 0, 0)


def _find_cell_by_ref(cells, ref_str):
    """
    Find a cell in the cells list that matches the given reference string.
    Matches by:
      1. metadata.data.globalReferences containing the reference
      2. metadata.id matching the reference (for older format compatibility)

    Returns the index and cell, or (None, None) if not found.
    """
    for i, cell in enumerate(cells):
        metadata = cell.get('metadata', {})
        # Check globalReferences first
        global_refs = metadata.get('data', {}).get('globalReferences', [])
        if ref_str in global_refs:
            return i, cell
        # Fallback: check if id matches the reference directly (older format)
        if metadata.get('id') == ref_str:
            return i, cell
    return None, None


def _find_insert_position(cells, ref_str):
    """
    Find the correct position to insert a new cell based on verse order.
    Compares the reference against existing cells' globalReferences to find
    the right spot.  Skips non-text cells (e.g., milestones) when comparing.
    """
    new_sort_key = _parse_ref_for_sort(ref_str)

    for i, cell in enumerate(cells):
        metadata = cell.get('metadata', {})

        # Skip non-text cells (milestones, etc.) — don't insert before them
        if metadata.get('type') != 'text':
            continue

        global_refs = metadata.get('data', {}).get('globalReferences', [])
        cell_id = metadata.get('id', '')

        # Get the reference for this cell
        cell_ref = global_refs[0] if global_refs else cell_id
        cell_sort_key = _parse_ref_for_sort(cell_ref)

        if cell_sort_key > new_sort_key:
            return i

    # If no cell has a greater reference, append at end
    return len(cells)


def _should_overwrite(cell_value, overwrite_filter, new_content=None):
    """
    Determine if a cell's value should be overwritten based on the filter.

    Args:
        cell_value: The current value of the cell
        overwrite_filter: None (default: don't overwrite non-empty),
                         "all" (always overwrite),
                         or a regex pattern string (overwrite if value matches)
        new_content: The new content to write. If provided and identical to
                     cell_value, returns False (no-op: content isn't changing).

    Returns:
        True if the cell should be overwritten, False otherwise
    """
    # If the content isn't actually changing, no overwrite needed
    if new_content is not None and cell_value == new_content:
        return False

    # Empty cells are always overwritten
    if not cell_value or not cell_value.strip():
        return True

    # Default behavior: don't overwrite non-empty cells
    if overwrite_filter is None:
        return False

    # "all" means always overwrite
    if overwrite_filter == "all":
        return True

    # Otherwise treat as regex pattern
    return bool(re.search(overwrite_filter, cell_value))


def _strip_content(content, strip_chars):
    """
    Strip specified characters from content.

    Args:
        content: The text content to clean
        strip_chars: A string of characters to remove, or None to skip stripping

    Returns:
        The cleaned content string
    """
    if not strip_chars or not content:
        return content
    for ch in strip_chars:
        content = content.replace(ch, '')
    return content


def _create_edit_history_entry(value, timestamp_ms, edit_type="user-edit",
                                author="easy_draft"):
    """
    Create an edit history entry compatible with the Codex editor's EditHistory type.

    The Codex editor's merge resolution system (resolveCodexCustomMerge) uses edit
    history entries to determine which content is authoritative during merges.
    Specifically, getCellValueData() in sharedUtils finds the latest edit where
    editMap is ["value"] and the value matches the current cell content. Without a
    matching edit entry with a current timestamp, injected content gets dropped
    during merge because it appears to be from an older state.

    Args:
        value: The cell value (content string) associated with this edit
        timestamp_ms: Unix timestamp in milliseconds (matching JS Date.now())
        edit_type: One of the EditType enum values from the codex-editor:
                   "user-edit", "llm-edit", "llm-generation",
                   "initial-import", "merge", "migration"
        author: The author/username string for this edit

    Returns:
        A dict matching the codex-editor EditHistory structure:
        {
            editMap: ["value"],
            value: <content>,
            timestamp: <ms timestamp>,
            type: <edit_type>,
            author: <author>,
            validatedBy: []
        }
    """
    return {
        'editMap': ['value'],
        'value': value,
        'timestamp': timestamp_ms,
        'type': edit_type,
        'author': author,
        'validatedBy': [],
    }


def _add_edit_history_to_cell(cell, value, timestamp_ms, edit_type="user-edit",
                               author="easy_draft"):
    """
    Add an edit history entry to a cell's metadata.edits array.

    If the cell has an existing value but no edit history, an initial-import entry
    is first created (backdated by 1 second) to preserve the original value in
    history, matching the pattern used by codexDocument.updateCellContent().

    Args:
        cell: The cell dict to modify (must have 'metadata' key)
        value: The new value being set on the cell
        timestamp_ms: Unix timestamp in milliseconds
        edit_type: The edit type string (default: "user-edit")
        author: The author string (default: "easy_draft")
    """
    metadata = cell.get('metadata', {})
    if 'edits' not in metadata:
        metadata['edits'] = []
    cell['metadata'] = metadata

    edits = metadata['edits']

    # If this is the first edit and the cell had a previous value, record an
    # initial-import entry for the old value (backdated by 1 second) so the
    # merge resolver can see the full history. This matches the pattern in
    # codexDocument.ts updateCellContent() lines 365-375.
    previous_value = cell.get('value', '')
    if len(edits) == 0 and previous_value and previous_value.strip():
        edits.append(_create_edit_history_entry(
            value=previous_value,
            timestamp_ms=timestamp_ms - 1000,
            edit_type='initial-import',
            author=author,
        ))

    # Add the new edit entry
    edits.append(_create_edit_history_entry(
        value=value,
        timestamp_ms=timestamp_ms,
        edit_type=edit_type,
        author=author,
    ))


def _inject_into_codex(existing_file, book, book_verses, side, mapped_ids,
                        reference_key, strict_book_names, overwrite_filter, vrefs_to_ids,
                        strip_chars=None):
    """
    Inject verse content into an existing codex file.

    - Matches cells by globalReferences or id
    - Only updates value field on existing cells
    - Creates new cells in correct verse order if not found
    - Respects overwrite_filter for non-empty cells
    - Adds edit history entries so the Codex editor's merge resolution
      recognizes the injected content as authoritative (latest timestamp wins)
    """
    with open(existing_file, 'r', encoding='utf-8') as f:
        codex_structure = json.load(f)

    codex_cells = codex_structure.get('cells', [])

    # Use a millisecond timestamp matching JavaScript's Date.now() for
    # compatibility with the Codex editor's edit history system.
    timestamp_ms = int(time.time() * 1000)

    for verse in book_verses:
        vref = utils.look_up_key(verse, reference_key)
        reconstructed_vref = mapped_ids[vref]
        content = _strip_content(
            utils.look_up_key(verse, side['content_key'], default=""),
            strip_chars
        )

        _, chapter_num, verse_start, verse_end = utils.split_ref2(reconstructed_vref)
        abbreviated_book = abbreviate_book_name(book, strict=strict_book_names)
        global_ref = f"{abbreviated_book} {chapter_num}:{verse_start}"

        # Try to find existing cell
        _idx, existing_cell = _find_cell_by_ref(codex_cells, global_ref)

        #see if perhaps the verse range is one cell.
        single_cell_range = False
        if not existing_cell and verse_start != verse_end:
            _idx, existing_cell = _find_cell_by_ref(codex_cells, reconstructed_vref)
            if existing_cell is not None:
                single_cell_range = True


        if existing_cell is not None:
            # Cell exists — only update value if overwrite conditions are met
            if _should_overwrite(existing_cell.get('value', ''), overwrite_filter, new_content=content):
                existing_cell['value'] = content
                # Add edit history so the merge resolver sees this as the latest edit
                _add_edit_history_to_cell(
                    existing_cell, content, timestamp_ms,
                    edit_type='user-edit', author='easy_draft'
                )
        else:
            # Cell doesn't exist — create and insert in correct position
            reference_to_add = global_ref
            if verse_start != verse_end and reconstructed_vref in vrefs_to_ids:
                new_id = vrefs_to_ids[reconstructed_vref]
                single_cell_range = True
                reference_to_add = reconstructed_vref
            elif global_ref in vrefs_to_ids:
                new_id = vrefs_to_ids[global_ref]

            else:
                new_id = generate_cell_id_from_hash(global_ref)

            new_cell = {
                'kind': 2,
                'languageId': 'html',
                'value': content,
                'metadata': {
                    'type': 'text',
                    'id': new_id,
                    'edits': [_create_edit_history_entry(
                        value=content,
                        timestamp_ms=timestamp_ms,
                        edit_type='initial-import',
                        author='easy_draft',
                    )],
                    'data': {
                        'globalReferences': [reference_to_add]
                    },
                    'cellLabel': str(verse_start) if not single_cell_range else f"{verse_start}-{verse_end}"
                }
            }
            if reconstructed_vref != vref:
                new_cell['metadata']['originalId'] = vref

            insert_pos = _find_insert_position(codex_cells, global_ref)
            codex_cells.insert(insert_pos, new_cell)

        # Handle range continuation cells
        in_range = verse_start != verse_end
        if in_range and not single_cell_range:
            for verse_num in range(verse_start + 1, verse_end + 1):
                range_global_ref = f"{abbreviated_book} {chapter_num}:{verse_num}"
                _range_idx, range_cell = _find_cell_by_ref(codex_cells, range_global_ref)

                range_content = '<range>' if content else ''

                if range_cell is not None:
                    if _should_overwrite(range_cell.get('value', ''), overwrite_filter, new_content=range_content):
                        range_cell['value'] = range_content
                        # Add edit history for range continuation cells too
                        _add_edit_history_to_cell(
                            range_cell, range_content, timestamp_ms,
                            edit_type='user-edit', author='easy_draft'
                        )
                else:
                    if range_global_ref in vrefs_to_ids:
                        range_id = vrefs_to_ids[range_global_ref]
                    else:
                        range_id = generate_cell_id_from_hash(range_global_ref)

                    new_range_cell = {
                        'kind': 2,
                        'languageId': 'html',
                        'value': range_content,
                        'metadata': {
                            'type': 'text',
                            'id': range_id,
                            'edits': [_create_edit_history_entry(
                                value=range_content,
                                timestamp_ms=timestamp_ms,
                                edit_type='initial-import',
                                author='easy_draft',
                            )],
                            'data': {
                                'globalReferences': [range_global_ref]
                            },
                            'cellLabel': str(verse_num)
                        }
                    }
                    insert_pos = _find_insert_position(codex_cells, range_global_ref)
                    codex_cells.insert(insert_pos, new_range_cell)

    codex_structure['cells'] = codex_cells

    with open(existing_file, 'w', encoding='utf-8') as f:
        json.dump(codex_structure, f, ensure_ascii=False, indent=2)
        f.write('\n')


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

    # Mode: "create" to generate new files, "inject" to update existing files.
    # If not specified and target files exist, an exception is raised.
    codex_mode = this_config.get( 'codex', {} ).get( 'mode', None )

    # Overwrite filter for injection mode:
    #   None (default) = don't overwrite non-empty cells
    #   "all" = overwrite everything
    #   "<regex>" = overwrite cells whose value matches the regex
    overwrite_filter = this_config.get( 'codex', {} ).get( 'overwrite_filter', None )

    # strip_chars: a string of characters to strip from content before injecting/creating.
    # e.g., strip_chars: "\n\r" would remove all newlines and carriage returns.
    strip_chars = this_config.get( 'codex', {} ).get( 'strip_chars', None )

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



    #need to collect as much verse to id mapping that we can so that we are most likely to create a valid
    #target or source file which maps across.
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
    vrefs_to_ids = {}
    for side in source_and_target:
        folder = side['folder']
        #now iterate all the files here:
        for filename in os.listdir(folder):
            if filename.endswith( f".{side['extension']}" ):
                filepath = os.path.join( folder, filename )
                content = utils.load_json( filepath )
                for cell in content.get( 'cells', [] ):
                    metadata = cell.get( 'metadata', {} )
                    data = metadata.get( 'data', {} )
                    global_references = data.get( 'globalReferences', [] )
                    for global_reference in global_references:
                        vrefs_to_ids[global_reference] = metadata.get( 'id' )



    #make it so that we can operate only on source or target or both.
    which_part = this_config.get( 'codex', {} ).get( 'which_part', 'both' )


    source_and_target = []
    if which_part in ['both', 'source']:
        source_and_target.append({
            'folder': os.path.join( project_folder, '.project/sourceTexts' ),
            'extension': "source",
            'content_key': source_key,
        })

    if which_part in ['both', 'target']:
        source_and_target.append({
            'folder': os.path.join( project_folder, 'files/target' ),
            'extension': "codex",
            'content_key': translation_key,
        })

    timestamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

    for side in source_and_target:
        os.makedirs( side['folder'], exist_ok=True )
        for book in book_to_verses:
            output_filename = os.path.join( side['folder'], f"{book}.{side['extension']}" )
            file_exists = os.path.exists( output_filename )

            # Determine effective mode for this file
            effective_mode = codex_mode
            if effective_mode is None:
                if file_exists:
                    raise RuntimeError(
                        f"Target file '{output_filename}' already exists and codex.mode is not set. "
                        f"Set codex.mode to 'create' to overwrite or 'inject' to update existing files."
                    )
                effective_mode = 'create'

            if effective_mode == 'inject' and file_exists:
                # Injection mode: update existing file
                _inject_into_codex(
                    existing_file=output_filename,
                    book=book,
                    book_verses=book_to_verses[book],
                    side=side,
                    mapped_ids=mapped_ids,
                    reference_key=reference_key,
                    strict_book_names=strict_book_names,
                    overwrite_filter=overwrite_filter,
                    vrefs_to_ids=vrefs_to_ids,
                    strip_chars=strip_chars,
                )
            else:
                # Create mode: generate new file from scratch
                if effective_mode == 'inject' and not file_exists:
                    print( f"  Warning: inject mode but '{output_filename}' does not exist. Creating new file." )

                codex_structure = {}
                codex_cells = codex_structure.setdefault( 'cells', [] )
                for verse in book_to_verses[book]:

                    vref = utils.look_up_key(verse, reference_key)
                    reconstructed_vref = mapped_ids[vref]

                    content = _strip_content(
                        utils.look_up_key(verse, side['content_key'], default=""),
                        strip_chars
                    )

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


                    in_range = verse_start != verse_end

                    single_cell_range = False
                    globalReference_to_use = global_ref
                    if in_range and reconstructed_vref in vrefs_to_ids[reconstructed_vref]:
                        cell_id = vrefs_to_ids[reconstructed_vref]
                        single_cell_range = True
                        globalReference_to_use = reconstructed_vref
                    elif global_ref in vrefs_to_ids:
                        cell_id = vrefs_to_ids[global_ref]
                    else:
                        cell_id = generate_cell_id_from_hash( global_ref )

                    metadata['id'] = cell_id
                    metadata['data'] = {
                        'globalReferences': [ globalReference_to_use ]
                    }
                    if not single_cell_range:
                        metadata['cellLabel'] = str(verse_start)
                    else:
                        metadata['cellLabel'] = f"{verse_start}-{verse_end}"

                    if not in_range:
                        if reconstructed_vref != vref:
                            metadata['originalId'] = vref

                    if in_range and not single_cell_range:
                        for verse_num in range( verse_start+1, verse_end+1 ):
                            range_global_ref = f"{abbreviated_book} {chapter_num}:{verse_num}"
                            codex_cell = {}
                            codex_cells.append( codex_cell )
                            codex_cell['kind'] = 2
                            codex_cell['languageId'] = 'html'
                            codex_cell['value'] = '<range>' if content else ''
                            metadata = codex_cell.setdefault( 'metadata', {} )
                            metadata['type'] = 'text'

                            if range_global_ref in vrefs_to_ids:
                                range_id = vrefs_to_ids[range_global_ref]
                            else:
                                range_id = generate_cell_id_from_hash( range_global_ref )

                            metadata['id'] = range_id
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

                with open( output_filename, 'w', encoding='utf-8' ) as f:
                    json.dump( codex_structure, f, ensure_ascii=False, indent=4 )
