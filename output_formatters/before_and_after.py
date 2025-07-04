import os
import time
from datetime import datetime

from format_utilities import get_config_for

import utils

def run( file ):
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
