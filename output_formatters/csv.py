import os
import time
from datetime import datetime

from format_utilities import get_config_for
import csv

import utils

def run( file ):
    """Converts the output to a csv format with columns for the output"""

    this_config = get_config_for( file )
    if this_config is None:
        this_config = {}

    csv_config = this_config.get( 'csv', {} )
    if not csv_config:
        return

    # Ensure csv_config is a dict
    if not isinstance(csv_config, dict):
        csv_config = {}

    print( f"converting {file} to csv" )

    if( "output_file" in csv_config ):
        output_file = csv_config['output_file']
    else:
        if 'output_file' in this_config:
            base = this_config['output_file']
        else:
            base = os.path.join( 'output', 'csv', os.path.basename( os.path.splitext(file)[0] ) )
        if not base.endswith('.csv'):
            base = base + '.csv'
        output_file = base

    # Create path up to file if it doesn't exist
    output_dir = os.path.dirname(output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    translation_key = this_config.get( 'translation_key', ['fresh_translation','text'] )
    reference_key = this_config.get( 'reference_key', ['vref'] )
    source_key = this_config.get( 'source_key', ['source'] )

    content = utils.load_jsonl( f"output/{file}" )

    start_time = time.time()

    rows = []

    verse_id = csv_config.get( "vref_label", "verse_id" )
    source_label = csv_config.get( "source_label", "source_text" )
    target_label = csv_config.get( "target_label", "transcription" )

    rows.append([verse_id,source_label, target_label])

    for verse_i, verse_object in enumerate(content):
        start_line = this_config.get( 'start_line', None )
        if start_line is not None:
            if verse_i < start_line - 1:
                continue

        end_line = this_config.get( 'end_line', None )
        if end_line is not None:
            if verse_i > end_line - 1:
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
        source = utils.look_up_key(verse_object, source_key)
        translation = utils.look_up_key(verse_object, translation_key)

        if csv_config.get( "strip_enters", False ):
            if isinstance(source, str):
                source = source.replace("\n", " ").replace("\r", " ").replace( "  ", " " )
            if isinstance(translation, str):
                translation = translation.replace("\n", " ").replace("\r", " ").replace( "  ", " " )

        if not csv_config.get( "require_target", True ) or translation:
            rows.append([vref, source, translation])


    with open( output_file, "wt", encoding='utf-8', newline='' ) as fout:
        csv_writer = csv.writer(fout)
        csv_writer.writerows(rows)